"""State Department ingestion: parse, idempotency, vector index (offline)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from retrieval.ingestion.state_dept import (
    StateDeptDocumentRef,
    StateDeptIngester,
    parse_state_dept_html,
)
from retrieval.models import SourceDocument, SourcePassage

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "state_dept_eritrea_2024.html"


@pytest.fixture
def eritrea_html() -> str:
    return _FIXTURE.read_text(encoding="utf-8")


def test_parse_fixture_produces_section_anchored_passages(eritrea_html: str) -> None:
    passages = parse_state_dept_html(eritrea_html)
    assert len(passages) >= 2
    anchors = {p.section_anchor for p in passages}
    assert "Executive Summary" in anchors
    assert "Respect for the Integrity of the Person" in anchors
    for p in passages:
        assert p.text
        assert p.token_count >= 1


@pytest.mark.asyncio(loop_scope="session")
async def test_upsert_twice_no_duplicate_rows(
    db_session: AsyncSession,
    eritrea_html: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    async def _fake_embed_texts(
        texts: list[str],
        *,
        api_key: str | None = None,
    ) -> list[list[float]]:
        calls.append(len(texts))
        return [
            [0.002 * float((i + j) % 17) for j in range(3072)]
            for i in range(len(texts))
        ]

    monkeypatch.setattr("retrieval.embed.embed_texts", _fake_embed_texts)

    _er_url = (
        "https://www.state.gov/reports/"
        "2024-country-reports-on-human-rights-practices/eritrea/"
    )
    ref = StateDeptDocumentRef(
        year=2024,
        country_iso2="ER",
        slug="eritrea",
        url=_er_url,
    )
    ingester = StateDeptIngester(year=2024, countries=["ER"], fixture_html=eritrea_html)

    for _ in range(2):
        raw = await ingester.fetch(ref)
        passages = ingester.parse(raw)
        await ingester.embed(passages)
        await ingester.upsert(db_session, ref, raw, passages)
        await db_session.commit()

    n_docs = await db_session.scalar(select(func.count()).select_from(SourceDocument))
    n_pass = await db_session.scalar(select(func.count()).select_from(SourcePassage))
    assert n_docs == 1
    assert n_pass == len(parse_state_dept_html(eritrea_html))
    assert all(p.embedding is not None for p in passages)
    assert calls == [len(passages), len(passages)]


@pytest.mark.asyncio(loop_scope="session")
async def test_similarity_query_and_hnsw_index(
    db_session: AsyncSession,
    eritrea_html: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_embed_texts(
        texts: list[str],
        *,
        api_key: str | None = None,
    ) -> list[list[float]]:
        out: list[list[float]] = []
        for i, _ in enumerate(texts):
            row = [0.0] * 3072
            row[i % 3072] = 1.0
            out.append(row)
        return out

    monkeypatch.setattr("retrieval.embed.embed_texts", _fake_embed_texts)

    _er_url = (
        "https://www.state.gov/reports/"
        "2024-country-reports-on-human-rights-practices/eritrea/"
    )
    ref = StateDeptDocumentRef(
        year=2024,
        country_iso2="ER",
        slug="eritrea",
        url=_er_url,
    )
    ingester = StateDeptIngester(year=2024, countries=["ER"], fixture_html=eritrea_html)
    raw = await ingester.fetch(ref)
    passages = ingester.parse(raw)
    await ingester.embed(passages)
    await ingester.upsert(db_session, ref, raw, passages)
    await db_session.commit()

    qvec = [0.0] * 3072
    qvec[0] = 1.0
    vec_literal = "[" + ",".join(str(float(x)) for x in qvec) + "]"

    await db_session.execute(text("SET LOCAL enable_seqscan = OFF"))
    explain = await db_session.execute(
        text(
            "EXPLAIN (FORMAT JSON) SELECT id FROM source_passages "
            "ORDER BY embedding::halfvec(3072) <=> (:qv)::halfvec LIMIT 5",
        ),
        {"qv": vec_literal},
    )
    plan_blob = explain.scalar_one()
    plan_str = json.dumps(plan_blob)
    assert "ix_source_passages_embedding_hnsw" in plan_str

    result = await db_session.execute(
        text(
            "SELECT id::text FROM source_passages "
            "ORDER BY embedding::halfvec(3072) <=> (:qv)::halfvec LIMIT 5",
        ),
        {"qv": vec_literal},
    )
    rows = result.fetchall()
    assert len(rows) >= 1
