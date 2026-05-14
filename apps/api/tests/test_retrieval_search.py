"""Integration tests for retrieval search, filters, rerank, and cache."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from llm.client import LLMClient
from retrieval.cache import DictRetrievalCache, reset_shared_redis_client_for_tests
from retrieval.models import SourceDocument, SourceFamily, SourcePassage
from retrieval.passage_search import search
from retrieval.rerank import RerankOutput
from retrieval.schemas import RetrievedPassage


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _ortho_vec(dim_index: int) -> list[float]:
    v = [0.0] * 3072
    v[dim_index % 3072] = 1.0
    return v


async def _insert_doc(
    session: AsyncSession,
    *,
    country_codes: list[str],
    publication_date: date,
    title: str,
    passage_text: str,
    embedding: list[float],
    url_suffix: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    doc = SourceDocument(
        source_family=SourceFamily.state_dept_human_rights,
        title=title,
        publication_date=publication_date,
        country_codes=country_codes,
        url=f"https://example.test/reports/{url_suffix}",
        last_verified_at=_utcnow(),
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
    )
    session.add(doc)
    await session.flush()
    passage = SourcePassage(
        source_document_id=doc.id,
        section_anchor="Section A",
        text=passage_text,
        embedding=embedding,
        token_count=max(1, len(passage_text) // 4),
    )
    session.add(passage)
    await session.flush()
    return doc.id, passage.id


@pytest.fixture(autouse=True)
def _clear_redis_singleton() -> Iterator[None]:
    reset_shared_redis_client_for_tests()
    yield
    reset_shared_redis_client_for_tests()


@pytest.mark.asyncio(loop_scope="session")
async def test_search_country_filter_excludes_other_countries(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_doc(
        db_session,
        country_codes=["ER"],
        publication_date=date(2024, 1, 1),
        title="ER report",
        passage_text="Eritrea conditions",
        embedding=_ortho_vec(0),
        url_suffix="er",
    )
    await _insert_doc(
        db_session,
        country_codes=["ET"],
        publication_date=date(2024, 1, 1),
        title="ET report",
        passage_text="Ethiopia conditions",
        embedding=_ortho_vec(1),
        url_suffix="et",
    )
    await _insert_doc(
        db_session,
        country_codes=["SO"],
        publication_date=date(2024, 1, 1),
        title="SO report",
        passage_text="Somalia conditions",
        embedding=_ortho_vec(2),
        url_suffix="so",
    )
    await db_session.commit()

    async def _fake_embed(self: LLMClient, texts: list[str]) -> list[list[float]]:
        _ = texts
        return [_ortho_vec(0)]

    async def _identity_rerank(
        query: str,
        passages: list[RetrievedPassage],
        session: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        backend: str | None = None,
        settings: Settings | None = None,
    ) -> list[RetrievedPassage]:
        _ = query, session, organization_id, user_id, backend, settings
        return list(passages)

    monkeypatch.setattr(LLMClient, "embed", _fake_embed)
    monkeypatch.setattr("retrieval.passage_search.rerank_passages", _identity_rerank)

    out = await search(
        db_session,
        "human rights",
        organization_id=None,
        user_id=None,
        country_codes=["ER"],
        top_k=10,
        cache=DictRetrievalCache({}),
        settings=Settings().model_copy(update={"retrieval_cache_enabled": True}),
    )
    assert len(out) == 1
    assert "Eritrea" in out[0].text


@pytest.mark.asyncio(loop_scope="session")
async def test_search_date_after_excludes_older_publication(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_doc(
        db_session,
        country_codes=["ER"],
        publication_date=date(2020, 6, 1),
        title="Old",
        passage_text="old era",
        embedding=_ortho_vec(10),
        url_suffix="old",
    )
    await _insert_doc(
        db_session,
        country_codes=["ER"],
        publication_date=date(2024, 6, 1),
        title="New",
        passage_text="recent era",
        embedding=_ortho_vec(11),
        url_suffix="new",
    )
    await db_session.commit()

    async def _fake_embed(self: LLMClient, texts: list[str]) -> list[list[float]]:
        _ = texts
        return [_ortho_vec(10)]

    async def _identity_rerank(
        query: str,
        passages: list[RetrievedPassage],
        session: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        backend: str | None = None,
        settings: Settings | None = None,
    ) -> list[RetrievedPassage]:
        _ = query, session, organization_id, user_id, backend, settings
        return list(passages)

    monkeypatch.setattr(LLMClient, "embed", _fake_embed)
    monkeypatch.setattr("retrieval.passage_search.rerank_passages", _identity_rerank)

    out = await search(
        db_session,
        "conditions",
        organization_id=None,
        user_id=None,
        country_codes=["ER"],
        date_after=date(2023, 1, 1),
        top_k=10,
        cache=DictRetrievalCache({}),
        settings=Settings().model_copy(update={"retrieval_cache_enabled": True}),
    )
    assert len(out) == 1
    assert "recent" in out[0].text


@pytest.mark.asyncio(loop_scope="session")
async def test_rerank_changes_order_vs_vector_similarity(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, pid_a = await _insert_doc(
        db_session,
        country_codes=["ER"],
        publication_date=date(2024, 1, 1),
        title="A",
        passage_text="alpha unrelated",
        embedding=_ortho_vec(0),
        url_suffix="a",
    )
    _, pid_b = await _insert_doc(
        db_session,
        country_codes=["ER"],
        publication_date=date(2024, 1, 1),
        title="B",
        passage_text="beta matches detention keyword",
        embedding=_ortho_vec(1),
        url_suffix="b",
    )
    await db_session.commit()

    async def _fake_embed(self: LLMClient, texts: list[str]) -> list[list[float]]:
        _ = texts
        return [_ortho_vec(0)]

    async def _prefer_b(
        query: str,
        passages: list[RetrievedPassage],
        session: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        backend: str | None = None,
        settings: Settings | None = None,
    ) -> list[RetrievedPassage]:
        _ = query, session, organization_id, user_id, backend, settings
        by_id = {p.passage_id: p for p in passages}
        return [by_id[pid_b], by_id[pid_a]]

    monkeypatch.setattr(LLMClient, "embed", _fake_embed)
    monkeypatch.setattr("retrieval.passage_search.rerank_passages", _prefer_b)

    out = await search(
        db_session,
        "detention keyword",
        organization_id=None,
        user_id=None,
        country_codes=["ER"],
        top_k=2,
        cache=DictRetrievalCache({}),
        settings=Settings().model_copy(update={"retrieval_cache_enabled": True}),
    )
    assert [p.passage_id for p in out] == [pid_b, pid_a]


@pytest.mark.asyncio(loop_scope="session")
async def test_cache_hit_skips_embed_but_not_rerank(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_doc(
        db_session,
        country_codes=["ER"],
        publication_date=date(2024, 1, 1),
        title="One",
        passage_text="body",
        embedding=_ortho_vec(5),
        url_suffix="one",
    )
    await db_session.commit()

    embed_calls = 0
    rerank_calls = 0

    async def _counting_embed(self: LLMClient, texts: list[str]) -> list[list[float]]:
        nonlocal embed_calls
        embed_calls += 1
        _ = texts
        return [_ortho_vec(5)]

    async def _counting_rerank(
        query: str,
        passages: list[RetrievedPassage],
        session: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        backend: str | None = None,
        settings: Settings | None = None,
    ) -> list[RetrievedPassage]:
        nonlocal rerank_calls
        rerank_calls += 1
        _ = query, session, organization_id, user_id, backend, settings
        return list(passages)

    monkeypatch.setattr(LLMClient, "embed", _counting_embed)
    monkeypatch.setattr("retrieval.passage_search.rerank_passages", _counting_rerank)

    store: dict[str, list[uuid.UUID]] = {}
    mem_cache = DictRetrievalCache(store)
    s = Settings().model_copy(update={"retrieval_cache_enabled": True})

    await search(
        db_session,
        "same query",
        organization_id=None,
        user_id=None,
        country_codes=["ER"],
        top_k=10,
        cache=mem_cache,
        settings=s,
    )
    await search(
        db_session,
        "same query",
        organization_id=None,
        user_id=None,
        country_codes=["ER"],
        top_k=10,
        cache=mem_cache,
        settings=s,
    )
    assert embed_calls == 1
    assert rerank_calls == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_cache_disabled_skips_cache_reads_and_writes(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _insert_doc(
        db_session,
        country_codes=["ER"],
        publication_date=date(2024, 1, 1),
        title="X",
        passage_text="x",
        embedding=_ortho_vec(7),
        url_suffix="x",
    )
    await db_session.commit()

    embed_calls = 0

    async def _counting_embed(self: LLMClient, texts: list[str]) -> list[list[float]]:
        nonlocal embed_calls
        embed_calls += 1
        _ = texts
        return [_ortho_vec(7)]

    async def _identity_rerank(
        query: str,
        passages: list[RetrievedPassage],
        session: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        backend: str | None = None,
        settings: Settings | None = None,
    ) -> list[RetrievedPassage]:
        _ = query, session, organization_id, user_id, backend, settings
        return list(passages)

    monkeypatch.setattr(LLMClient, "embed", _counting_embed)
    monkeypatch.setattr("retrieval.passage_search.rerank_passages", _identity_rerank)

    gets: list[str] = []
    sets: list[str] = []

    class SpyCache(DictRetrievalCache):
        async def get_candidate_ids(self, cache_key: str) -> list[uuid.UUID] | None:
            gets.append(cache_key)
            return await super().get_candidate_ids(cache_key)

        async def set_candidate_ids(
            self,
            cache_key: str,
            passage_ids: list[uuid.UUID],
        ) -> None:
            sets.append(cache_key)
            await super().set_candidate_ids(cache_key, passage_ids)

    spy = SpyCache({})
    s = Settings().model_copy(update={"retrieval_cache_enabled": False})

    await search(
        db_session,
        "q1",
        organization_id=None,
        user_id=None,
        country_codes=["ER"],
        top_k=10,
        cache=spy,
        settings=s,
    )
    await search(
        db_session,
        "q1",
        organization_id=None,
        user_id=None,
        country_codes=["ER"],
        top_k=10,
        cache=spy,
        settings=s,
    )
    assert embed_calls == 2
    assert gets == []
    assert sets == []


@pytest.mark.asyncio(loop_scope="session")
async def test_search_p95_latency_under_threshold(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for i in range(3):
        await _insert_doc(
            db_session,
            country_codes=["ER"],
            publication_date=date(2024, 1, 1),
            title=f"D{i}",
            passage_text=f"p{i}",
            embedding=_ortho_vec(20 + i),
            url_suffix=f"p{i}",
        )
    await db_session.commit()

    async def _fast_embed(self: LLMClient, texts: list[str]) -> list[list[float]]:
        _ = texts
        return [_ortho_vec(20)]

    async def _fast_rerank(
        query: str,
        passages: list[RetrievedPassage],
        session: AsyncSession,
        *,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        backend: str | None = None,
        settings: Settings | None = None,
    ) -> list[RetrievedPassage]:
        _ = query, session, organization_id, user_id, backend, settings
        return list(passages)

    monkeypatch.setattr(LLMClient, "embed", _fast_embed)
    monkeypatch.setattr("retrieval.passage_search.rerank_passages", _fast_rerank)

    timings: list[float] = []
    for _ in range(25):
        t0 = time.perf_counter()
        await search(
            db_session,
            "latency probe",
            organization_id=None,
            user_id=None,
            country_codes=["ER"],
            top_k=5,
            cache=DictRetrievalCache({}),
            settings=Settings().model_copy(update={"retrieval_cache_enabled": True}),
        )
        timings.append(time.perf_counter() - t0)
    timings.sort()
    if len(timings) < 2:
        raise AssertionError("expected multiple timings")
    p95_idx = int(round(0.95 * (len(timings) - 1)))
    p95 = timings[p95_idx]
    assert p95 < 0.6


@pytest.mark.asyncio(loop_scope="session")
async def test_rerank_llm_path_via_complete_structured_mock(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Smoke: default LLM rerank wires through LLMClient.complete_structured."""
    _, pid_a = await _insert_doc(
        db_session,
        country_codes=["ER"],
        publication_date=date(2024, 1, 1),
        title="A2",
        passage_text="first",
        embedding=_ortho_vec(0),
        url_suffix="a2",
    )
    _, pid_b = await _insert_doc(
        db_session,
        country_codes=["ER"],
        publication_date=date(2024, 1, 1),
        title="B2",
        passage_text="second",
        embedding=_ortho_vec(1),
        url_suffix="b2",
    )
    await db_session.commit()

    async def _fake_embed(self: LLMClient, texts: list[str]) -> list[list[float]]:
        _ = texts
        return [_ortho_vec(0)]

    async def _fake_complete_structured(
        self: LLMClient,
        prompt: object,
        schema: type[RerankOutput],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> RerankOutput:
        _ = prompt, max_tokens, temperature
        assert schema is RerankOutput
        return RerankOutput(ordered_passage_ids=[pid_b, pid_a])

    monkeypatch.setattr(LLMClient, "embed", _fake_embed)
    monkeypatch.setattr(LLMClient, "complete_structured", _fake_complete_structured)

    from retrieval import rerank as rerank_mod

    out = await rerank_mod.rerank_passages(
        "q",
        [
            RetrievedPassage(
                passage_id=pid_a,
                document_id=uuid.uuid4(),
                source_family="state_dept_human_rights",
                document_title="t",
                publication_date=date(2024, 1, 1),
                url="u",
                section_anchor="s",
                text="first",
                similarity_score=0.9,
            ),
            RetrievedPassage(
                passage_id=pid_b,
                document_id=uuid.uuid4(),
                source_family="state_dept_human_rights",
                document_title="t",
                publication_date=date(2024, 1, 1),
                url="u",
                section_anchor="s",
                text="second",
                similarity_score=0.1,
            ),
        ],
        db_session,
        organization_id=None,
        user_id=None,
        backend="llm",
        settings=Settings().model_copy(update={"retrieval_rerank_backend": "llm"}),
    )
    assert [p.passage_id for p in out] == [pid_b, pid_a]


@pytest.mark.asyncio(loop_scope="session")
async def test_cross_encoder_backend_import_error_message(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins
    from collections.abc import Mapping

    real_import = builtins.__import__

    def _block_sentence_transformers(
        name: str,
        globals_: Mapping[str, object] | None = None,
        locals_: Mapping[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name == "sentence_transformers":
            raise ImportError("blocked for test")
        return real_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_sentence_transformers)
    from retrieval import rerank as rerank_mod

    p = RetrievedPassage(
        passage_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        source_family="state_dept_human_rights",
        document_title="t",
        publication_date=date(2024, 1, 1),
        url="u",
        section_anchor="s",
        text="body",
        similarity_score=0.5,
    )
    with pytest.raises(RuntimeError, match="sentence-transformers"):
        await rerank_mod.rerank_passages(
            "q",
            [p],
            db_session,
            organization_id=None,
            user_id=None,
            backend="cross_encoder",
            settings=Settings().model_copy(
                update={"retrieval_rerank_backend": "cross_encoder"},
            ),
        )
