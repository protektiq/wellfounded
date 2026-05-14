"""Shared idempotent upsert for source_documents and source_passages."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from retrieval.ingestion.base import Passage
from retrieval.models import SourceDocument, SourceFamily, SourcePassage


async def upsert_source_document_with_passages(
    session: AsyncSession,
    *,
    source_family: SourceFamily,
    title: str,
    publication_date: date,
    country_codes: list[str],
    url: str,
    passages: list[Passage],
    content_hash: str,
) -> None:
    """Insert document and passages, or refresh last_verified_at when hash matches."""
    if not passages:
        return
    for p in passages:
        if p.embedding is None:
            raise ValueError("passages must be embedded before upsert")

    existing_id = await session.scalar(
        select(SourceDocument.id).where(
            SourceDocument.source_family == source_family,
            SourceDocument.content_hash == content_hash,
        ),
    )
    now = datetime.now(UTC)
    if existing_id is not None:
        existing = await session.get(SourceDocument, existing_id)
        if existing is None:
            raise RuntimeError("source document row missing after id lookup")
        existing.last_verified_at = now
        existing.title = title
        return

    doc = SourceDocument(
        source_family=source_family,
        title=title,
        publication_date=publication_date,
        country_codes=country_codes,
        url=url,
        last_verified_at=now,
        content_hash=content_hash,
        deleted_at=None,
    )
    session.add(doc)
    await session.flush()
    for p in passages:
        session.add(
            SourcePassage(
                source_document_id=doc.id,
                section_anchor=p.section_anchor,
                page_number=p.page_number,
                text=p.text,
                embedding=p.embedding,
                token_count=p.token_count,
            ),
        )
