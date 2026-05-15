"""Vector search over the global source library with filters and reranking."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings, get_settings
from llm.client import LLMClient
from retrieval.cache import (
    NullRetrievalCache,
    RetrievalCache,
    build_retrieval_cache_key,
    default_retrieval_cache,
)
from retrieval.models import SourceFamily
from retrieval.rerank import rerank_passages
from retrieval.schemas import PassageExportMeta, RetrievedPassage

log = structlog.get_logger()

_MAX_QUERY_CHARS = 25_000
_MIN_TOP_K = 1
_MAX_TOP_K = 100


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def _validate_country_codes(codes: list[str]) -> list[str]:
    if not codes:
        raise ValueError("country_codes must be non-empty")
    if len(codes) > 200:
        raise ValueError("country_codes list exceeds maximum length")
    out: list[str] = []
    for i, c in enumerate(codes):
        if not isinstance(c, str):
            raise TypeError(f"country_codes[{i}] must be str")
        u = c.strip().upper()
        if len(u) != 2 or not u.isalpha():
            raise ValueError(
                f"country_codes[{i}] must be a two-letter ISO 3166-1 alpha-2 code",
            )
        out.append(u)
    return sorted(set(out))


def _validate_source_families(
    families: list[str] | None,
) -> tuple[str, ...] | None:
    if families is None or len(families) == 0:
        return None
    if len(families) > 32:
        raise ValueError("source_families list exceeds maximum length")
    seen: set[str] = set()
    for i, f in enumerate(families):
        if not isinstance(f, str):
            raise TypeError(f"source_families[{i}] must be str")
        key = f.strip()
        if not key:
            raise ValueError(f"source_families[{i}] is empty")
        try:
            SourceFamily(key)
        except ValueError as exc:
            raise ValueError(f"unknown source_family: {key!r}") from exc
        seen.add(key)
    return tuple(sorted(seen))


def _validate_query(q: str) -> str:
    if not isinstance(q, str):
        raise TypeError("query must be str")
    s = q.strip()
    if not s:
        raise ValueError("query must be non-empty")
    if len(s) > _MAX_QUERY_CHARS:
        raise ValueError(f"query exceeds {_MAX_QUERY_CHARS} characters")
    return s


def _candidate_limit(top_k: int, settings: Settings) -> int:
    raw = top_k * settings.retrieval_vector_candidate_multiplier
    return min(settings.retrieval_vector_max_candidates, max(top_k, raw))


def _sql_varchar2_array_literal(codes: list[str]) -> str:
    """SQL literal for overlap filter; ``codes`` must be validated ISO2 uppercase."""
    inner = ",".join(f"'{c}'" for c in codes)
    return f"ARRAY[{inner}]::varchar(2)[]"


def _sql_text_array_literal(values: list[str]) -> str:
    """SQL literal for source_family filter tokens (enum value strings)."""
    parts: list[str] = []
    for v in values:
        if not v or not all(ch.isalnum() or ch == "_" for ch in v):
            raise ValueError("invalid source_family token for SQL literal")
        parts.append("'" + v.replace("'", "''") + "'")
    return f"ARRAY[{','.join(parts)}]::text[]"


def _sql_uuid_in_list(ids: list[uuid.UUID]) -> str:
    if len(ids) > 500:
        raise ValueError("passage id list exceeds maximum length")
    return ",".join(f"'{u}'::uuid" for u in ids)


def _row_to_passage(
    row: dict[str, object],
) -> RetrievedPassage:
    pub = row["publication_date"]
    if not isinstance(pub, date):
        raise TypeError("publication_date must be date")
    sid = row["passage_id"]
    did = row["document_id"]
    if not isinstance(sid, uuid.UUID) or not isinstance(did, uuid.UUID):
        raise TypeError("passage and document ids must be UUID")
    sim_raw = row["similarity"]
    if isinstance(sim_raw, bool):
        raise TypeError("similarity must be numeric")
    if isinstance(sim_raw, int | float | Decimal):
        sim = float(sim_raw)
    else:
        raise TypeError("similarity must be numeric")
    title = row["document_title"]
    url = row["url"]
    anchor = row["section_anchor"]
    text_val = row["text"]
    fam = row["source_family"]
    if not isinstance(title, str):
        raise TypeError("document_title must be str")
    if not isinstance(url, str):
        raise TypeError("url must be str")
    if not isinstance(anchor, str):
        raise TypeError("section_anchor must be str")
    if not isinstance(text_val, str):
        raise TypeError("text must be str")
    if not isinstance(fam, str):
        raise TypeError("source_family must be str")
    return RetrievedPassage(
        passage_id=sid,
        document_id=did,
        source_family=fam,
        document_title=title,
        publication_date=pub,
        url=url,
        section_anchor=anchor,
        text=text_val,
        similarity_score=sim,
    )


def _row_to_passage_export_meta(row: dict[str, object]) -> PassageExportMeta:
    sid = row["passage_id"]
    if not isinstance(sid, uuid.UUID):
        raise TypeError("passage_id must be UUID")
    pub = row["publication_date"]
    if not isinstance(pub, date):
        raise TypeError("publication_date must be date")
    title = row["document_title"]
    url = row["url"]
    anchor = row["section_anchor"]
    fam = row["source_family"]
    lva = row["last_verified_at"]
    if not isinstance(title, str):
        raise TypeError("document_title must be str")
    if not isinstance(url, str):
        raise TypeError("url must be str")
    if not isinstance(anchor, str):
        raise TypeError("section_anchor must be str")
    if not isinstance(fam, str):
        raise TypeError("source_family must be str")
    if not isinstance(lva, datetime):
        raise TypeError("last_verified_at must be datetime")
    return PassageExportMeta(
        passage_id=sid,
        source_family=fam,
        document_title=title,
        publication_date=pub,
        url=url,
        section_anchor=anchor,
        last_verified_at=lva,
    )


async def fetch_passages_export_meta(
    session: AsyncSession,
    passage_ids: list[uuid.UUID],
) -> dict[uuid.UUID, PassageExportMeta]:
    """Load passage rows joined to documents for DOCX bibliography (not org-scoped)."""
    if not passage_ids:
        return {}
    unique: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for pid in passage_ids:
        if pid not in seen:
            seen.add(pid)
            unique.append(pid)
    in_list = _sql_uuid_in_list(unique)
    sql = text(
        f"""
        SELECT
            sp.id AS passage_id,
            sd.source_family::text AS source_family,
            sd.title AS document_title,
            sd.publication_date AS publication_date,
            sd.url AS url,
            sp.section_anchor AS section_anchor,
            sd.last_verified_at AS last_verified_at
        FROM source_passages sp
        INNER JOIN source_documents sd ON sd.id = sp.source_document_id
        WHERE sd.deleted_at IS NULL
          AND sp.id IN ({in_list})
        """,
    )
    result = await session.execute(sql)
    by_id: dict[uuid.UUID, PassageExportMeta] = {}
    for r in result.mappings().all():
        meta = _row_to_passage_export_meta(dict(r))
        by_id[meta.passage_id] = meta
    missing = [pid for pid in unique if pid not in by_id]
    if missing:
        raise ValueError(
            "missing or deleted source rows for passage_ids: "
            + ", ".join(str(x) for x in missing),
        )
    return by_id


async def _vector_ann_search(
    session: AsyncSession,
    *,
    query_vector_literal: str,
    country_codes: list[str],
    date_after: date | None,
    source_families: tuple[str, ...] | None,
    limit: int,
) -> list[RetrievedPassage]:
    date_clause = ""
    country_sql = _sql_varchar2_array_literal(country_codes)
    params: dict[str, object] = {
        "qv": query_vector_literal,
        "limit": limit,
    }
    if date_after is not None:
        date_clause = " AND sd.publication_date >= :date_after"
        params["date_after"] = date_after

    family_clause = ""
    if source_families is not None:
        fam_lit = _sql_text_array_literal(list(source_families))
        family_clause = f" AND sd.source_family::text = ANY({fam_lit})"

    sql = text(
        f"""
        SELECT
            sp.id AS passage_id,
            sd.id AS document_id,
            sd.source_family::text AS source_family,
            sd.title AS document_title,
            sd.publication_date AS publication_date,
            sd.url AS url,
            sp.section_anchor AS section_anchor,
            sp.text AS text,
            (1.0 - (sp.embedding::halfvec(3072) <=> (:qv)::halfvec(3072)))
                AS similarity
        FROM source_passages sp
        INNER JOIN source_documents sd ON sd.id = sp.source_document_id
        WHERE sd.deleted_at IS NULL
          AND sd.country_codes && {country_sql}
          {date_clause}
          {family_clause}
        ORDER BY sp.embedding::halfvec(3072) <=> (:qv)::halfvec(3072) ASC
        LIMIT :limit
        """,
    )
    result = await session.execute(sql, params)
    rows = result.mappings().all()
    return [_row_to_passage(dict(r)) for r in rows]


async def fetch_passages_by_ordered_ids(
    session: AsyncSession,
    ordered_ids: list[uuid.UUID],
) -> list[RetrievedPassage] | None:
    if not ordered_ids:
        return []
    in_list = _sql_uuid_in_list(ordered_ids)
    sql = text(
        f"""
        SELECT
            sp.id AS passage_id,
            sd.id AS document_id,
            sd.source_family::text AS source_family,
            sd.title AS document_title,
            sd.publication_date AS publication_date,
            sd.url AS url,
            sp.section_anchor AS section_anchor,
            sp.text AS text,
            0.0 AS similarity
        FROM source_passages sp
        INNER JOIN source_documents sd ON sd.id = sp.source_document_id
        WHERE sd.deleted_at IS NULL
          AND sp.id IN ({in_list})
        """,
    )
    result = await session.execute(sql)
    by_id: dict[uuid.UUID, RetrievedPassage] = {}
    for r in result.mappings().all():
        p = _row_to_passage(dict(r))
        by_id[p.passage_id] = p
    ordered: list[RetrievedPassage] = []
    for i, pid in enumerate(ordered_ids):
        row = by_id.get(pid)
        if row is None:
            return None
        proxy_score = 1.0 - (i / max(1, len(ordered_ids) - 1)) * 0.01
        ordered.append(
            RetrievedPassage(
                passage_id=row.passage_id,
                document_id=row.document_id,
                source_family=row.source_family,
                document_title=row.document_title,
                publication_date=row.publication_date,
                url=row.url,
                section_anchor=row.section_anchor,
                text=row.text,
                similarity_score=proxy_score,
            ),
        )
    return ordered


async def search(
    session: AsyncSession,
    query: str,
    *,
    organization_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
    country_codes: list[str],
    date_after: date | None = None,
    source_families: list[str] | None = None,
    top_k: int = 20,
    cache: RetrievalCache | None = None,
    settings: Settings | None = None,
) -> list[RetrievedPassage]:
    """Embed query (unless cache hit), ANN search with filters, rerank, return top_k."""
    s = settings if settings is not None else get_settings()
    q = _validate_query(query)
    cc = _validate_country_codes(country_codes)
    sf = _validate_source_families(source_families)
    if not isinstance(top_k, int) or top_k < _MIN_TOP_K or top_k > _MAX_TOP_K:
        raise ValueError(f"top_k must be between {_MIN_TOP_K} and {_MAX_TOP_K}")

    candidate_limit = _candidate_limit(top_k, s)
    cache_key = build_retrieval_cache_key(
        query=q,
        country_codes=cc,
        date_after=date_after,
        source_families=sf,
        candidate_limit=candidate_limit,
        top_k=top_k,
    )

    cache_backend: RetrievalCache = NullRetrievalCache()
    if s.retrieval_cache_enabled:
        cache_backend = cache if cache is not None else default_retrieval_cache(s)

    candidates: list[RetrievedPassage] = []
    cache_hit = False
    if s.retrieval_cache_enabled:
        cached_ids = await cache_backend.get_candidate_ids(cache_key)
        if cached_ids and len(cached_ids) > 0:
            loaded = await fetch_passages_by_ordered_ids(session, cached_ids)
            if loaded is not None and len(loaded) == len(cached_ids):
                candidates = loaded
                cache_hit = True
                log.debug(
                    "retrieval_cache_hit",
                    cache_key_suffix=cache_key[-16:],
                    n_candidates=len(candidates),
                )

    if not cache_hit:
        llm = LLMClient(session, organization_id, user_id)
        vectors = await llm.embed([q])
        if len(vectors) != 1:
            raise RuntimeError("embedding response must return exactly one vector")
        q_lit = _vector_literal(vectors[0])
        candidates = await _vector_ann_search(
            session,
            query_vector_literal=q_lit,
            country_codes=cc,
            date_after=date_after,
            source_families=sf,
            limit=candidate_limit,
        )
        if s.retrieval_cache_enabled:
            await cache_backend.set_candidate_ids(
                cache_key,
                [p.passage_id for p in candidates],
            )

    reranked = await rerank_passages(
        q,
        candidates,
        session,
        organization_id=organization_id,
        user_id=user_id,
        settings=s,
    )
    return reranked[:top_k]
