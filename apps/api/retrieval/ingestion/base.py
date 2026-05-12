"""Abstract ingestion pipeline for source documents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class Passage:
    """A chunk of source text prior to or after embedding."""

    section_anchor: str
    page_number: int | None
    text: str
    token_count: int
    embedding: list[float] | None = None


class SourceIngester(ABC):
    """Template: discover refs, fetch raw bytes, parse, embed, upsert."""

    @abstractmethod
    def discover(self) -> list[Any]:
        """Return document references to ingest (bounded MVP lists are fine)."""

    @abstractmethod
    async def fetch(self, doc_ref: Any) -> str:
        """Load raw HTML or text for a reference."""

    @abstractmethod
    def parse(self, raw: str) -> list[Passage]:
        """Split raw content into passages (no network)."""

    async def embed(self, passages: Sequence[Passage]) -> None:
        """Fill ``embedding`` on each passage."""
        if not passages:
            return
        from retrieval.embed import embed_texts as _embed_texts

        texts = [p.text for p in passages]
        vectors = await _embed_texts(texts)
        for passage, vector in zip(passages, vectors, strict=True):
            passage.embedding = vector

    @abstractmethod
    async def upsert(
        self,
        session: AsyncSession,
        doc_ref: Any,
        raw: str,
        passages: list[Passage],
    ) -> None:
        """Persist document and passages idempotently."""

    async def run(
        self,
        session: AsyncSession,
        doc_refs: Iterable[Any] | None = None,
    ) -> None:
        """Ingest each discovered reference in its own transaction."""
        refs = list(doc_refs) if doc_refs is not None else self.discover()
        for ref in refs:
            raw = await self.fetch(ref)
            passages = self.parse(raw)
            await self.embed(passages)
            await self.upsert(session, ref, raw, passages)
            await session.commit()
