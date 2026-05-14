"""Ingest USCIRF annual report PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from retrieval.ingestion import launch_catalog
from retrieval.ingestion.base import Passage, SourceIngester

_USCIRF_COUNTRY_CODES: list[str] = sorted(
    p.iso2 for p in launch_catalog.LAUNCH_COUNTRY_PROFILES
)
from retrieval.ingestion.document_upsert import upsert_source_document_with_passages
from retrieval.ingestion.html_passages import (
    content_hash_from_passages,
    parse_pdf_plain_text_to_passages,
)
from retrieval.ingestion.http_fetch import http_get_bytes
from retrieval.ingestion.pdf_text import extract_pdf_text
from retrieval.models import SourceFamily


@dataclass(frozen=True)
class UscirfDocumentRef:
    report_year: int
    url: str


class UscirfIngester(SourceIngester):
    """Fetches USCIRF annual report PDFs and chunks extracted text."""

    def __init__(
        self,
        *,
        year_from: int,
        year_to: int,
        fixture_path: Path | None = None,
        fixture_pdf_bytes: bytes | None = None,
        fixture_plain_text: str | None = None,
        single_ref: UscirfDocumentRef | None = None,
    ) -> None:
        y0 = min(year_from, year_to)
        y1 = max(year_from, year_to)
        self._year_from = y0
        self._year_to = y1
        self._fixture_path = fixture_path
        self._fixture_pdf_bytes = fixture_pdf_bytes
        self._fixture_plain_text = fixture_plain_text
        self._single_ref = single_ref

    def discover(self) -> list[UscirfDocumentRef]:
        if self._single_ref is not None:
            return [self._single_ref]
        out: list[UscirfDocumentRef] = []
        y_lo = max(self._year_from, launch_catalog.USCIRF_YEAR_START)
        y_hi = min(self._year_to, launch_catalog.USCIRF_YEAR_END)
        for report_year in range(y_lo, y_hi + 1):
            url = launch_catalog.USCIRF_ANNUAL_REPORT_PDF.get(report_year)
            if url is not None:
                out.append(UscirfDocumentRef(report_year=report_year, url=url))
        return out

    async def fetch(self, doc_ref: Any) -> str:
        if not isinstance(doc_ref, UscirfDocumentRef):
            raise TypeError("doc_ref must be UscirfDocumentRef")
        if self._fixture_plain_text is not None:
            return self._fixture_plain_text
        if self._fixture_pdf_bytes is not None:
            raw_bytes = self._fixture_pdf_bytes
        elif self._fixture_path is not None:
            raw_bytes = self._fixture_path.read_bytes()
        else:
            raw_bytes = await http_get_bytes(doc_ref.url)
        return extract_pdf_text(raw_bytes)

    def parse(self, raw: str) -> list[Passage]:
        return parse_pdf_plain_text_to_passages(raw)

    async def upsert(
        self,
        session: AsyncSession,
        doc_ref: Any,
        raw: str,
        passages: list[Passage],
    ) -> None:
        if not isinstance(doc_ref, UscirfDocumentRef):
            raise TypeError("doc_ref must be UscirfDocumentRef")
        if not passages:
            return
        content_hash = content_hash_from_passages(passages)
        title = f"USCIRF Annual Report {doc_ref.report_year}"
        await upsert_source_document_with_passages(
            session,
            source_family=SourceFamily.uscirf,
            title=title,
            publication_date=date(doc_ref.report_year, 12, 31),
            country_codes=_USCIRF_COUNTRY_CODES,
            url=doc_ref.url,
            passages=passages,
            content_hash=content_hash,
        )
