"""Ingest EUAA Country of Origin Information PDFs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from retrieval.ingestion import launch_catalog
from retrieval.ingestion.base import Passage, SourceIngester
from retrieval.ingestion.document_upsert import upsert_source_document_with_passages
from retrieval.ingestion.html_passages import (
    content_hash_from_passages,
    parse_pdf_plain_text_to_passages,
)
from retrieval.ingestion.http_fetch import http_get_bytes
from retrieval.ingestion.pdf_text import extract_pdf_text
from retrieval.models import SourceFamily


@dataclass(frozen=True)
class EuaaCoiDocumentRef:
    url: str
    country_codes: list[str]
    publication_year: int
    title: str


class EuaaCoiIngester(SourceIngester):
    """Fetches EUAA COI PDFs listed in the launch catalog."""

    def __init__(
        self,
        *,
        fixture_path: Path | None = None,
        fixture_pdf_bytes: bytes | None = None,
        fixture_plain_text: str | None = None,
        single_ref: EuaaCoiDocumentRef | None = None,
    ) -> None:
        self._fixture_path = fixture_path
        self._fixture_pdf_bytes = fixture_pdf_bytes
        self._fixture_plain_text = fixture_plain_text
        self._single_ref = single_ref

    def discover(self) -> list[EuaaCoiDocumentRef]:
        if self._single_ref is not None:
            return [self._single_ref]
        out: list[EuaaCoiDocumentRef] = []
        for url, codes, pub_y, title in launch_catalog.EUAA_COI_PDF_URLS:
            out.append(
                EuaaCoiDocumentRef(
                    url=url,
                    country_codes=list(codes),
                    publication_year=pub_y,
                    title=title,
                ),
            )
        return out

    async def fetch(self, doc_ref: Any) -> str:
        if not isinstance(doc_ref, EuaaCoiDocumentRef):
            raise TypeError("doc_ref must be EuaaCoiDocumentRef")
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
        if not isinstance(doc_ref, EuaaCoiDocumentRef):
            raise TypeError("doc_ref must be EuaaCoiDocumentRef")
        if not passages:
            return
        content_hash = content_hash_from_passages(passages)
        await upsert_source_document_with_passages(
            session,
            source_family=SourceFamily.euaa_coi,
            title=doc_ref.title[:512],
            publication_date=date(doc_ref.publication_year, 6, 1),
            country_codes=sorted(
                {c.strip().upper()[:2] for c in doc_ref.country_codes}
            ),
            url=doc_ref.url,
            passages=passages,
            content_hash=content_hash,
        )
