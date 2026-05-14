"""Ingest Amnesty International country location pages (HTML)."""

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
    parse_article_by_headings,
    parse_html_document_title,
)
from retrieval.ingestion.http_fetch import http_get_text
from retrieval.models import SourceFamily


@dataclass(frozen=True)
class AmnestyDocumentRef:
    country_iso2: str
    location_path: str
    url: str


class AmnestyIngester(SourceIngester):
    """Fetches Amnesty country/location overview pages."""

    def __init__(
        self,
        *,
        countries: list[str] | None,
        fixture_html: str | None = None,
        fixture_path: Path | None = None,
        single_ref: AmnestyDocumentRef | None = None,
    ) -> None:
        profiles = {p.iso2.upper(): p for p in launch_catalog.LAUNCH_COUNTRY_PROFILES}
        if countries is None or len(countries) == 0:
            upper = sorted(profiles.keys())
        else:
            upper = [c.strip().upper() for c in countries]
            for c in upper:
                if c not in profiles:
                    raise ValueError(f"country {c} is not in launch catalog")
        self._countries = upper
        self._profiles = profiles
        self._fixture_html = fixture_html
        self._fixture_path = fixture_path
        self._single_ref = single_ref

    def discover(self) -> list[AmnestyDocumentRef]:
        if self._single_ref is not None:
            return [self._single_ref]
        out: list[AmnestyDocumentRef] = []
        for iso2 in self._countries:
            path = self._profiles[iso2].amnesty_location_path
            url = launch_catalog.amnesty_country_url(path)
            out.append(
                AmnestyDocumentRef(
                    country_iso2=iso2,
                    location_path=path,
                    url=url,
                ),
            )
        return out

    async def fetch(self, doc_ref: Any) -> str:
        if not isinstance(doc_ref, AmnestyDocumentRef):
            raise TypeError("doc_ref must be AmnestyDocumentRef")
        if self._fixture_html is not None:
            return self._fixture_html
        if self._fixture_path is not None:
            return self._fixture_path.read_text(encoding="utf-8")
        return await http_get_text(doc_ref.url)

    def parse(self, raw: str) -> list[Passage]:
        return parse_article_by_headings(raw, heading_tags=("h2", "h3"))

    async def upsert(
        self,
        session: AsyncSession,
        doc_ref: Any,
        raw: str,
        passages: list[Passage],
    ) -> None:
        if not isinstance(doc_ref, AmnestyDocumentRef):
            raise TypeError("doc_ref must be AmnestyDocumentRef")
        if not passages:
            return
        content_hash = content_hash_from_passages(passages)
        title = parse_html_document_title(
            raw, fallback="Amnesty International country page"
        )
        await upsert_source_document_with_passages(
            session,
            source_family=SourceFamily.amnesty,
            title=title[:512],
            publication_date=date(2025, 1, 1),
            country_codes=[doc_ref.country_iso2],
            url=doc_ref.url,
            passages=passages,
            content_hash=content_hash,
        )
