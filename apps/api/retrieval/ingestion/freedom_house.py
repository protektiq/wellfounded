"""Ingest Freedom House Freedom in the World country pages (HTML)."""

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
class FreedomHouseDocumentRef:
    year: int
    country_iso2: str
    country_slug: str
    url: str


class FreedomHouseIngester(SourceIngester):
    """Fetches Freedom in the World country score pages."""

    def __init__(
        self,
        *,
        year_from: int,
        year_to: int,
        countries: list[str] | None,
        fixture_html: str | None = None,
        fixture_path: Path | None = None,
        single_ref: FreedomHouseDocumentRef | None = None,
    ) -> None:
        y0 = min(year_from, year_to)
        y1 = max(year_from, year_to)
        self._year_from = y0
        self._year_to = y1
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

    def discover(self) -> list[FreedomHouseDocumentRef]:
        if self._single_ref is not None:
            return [self._single_ref]
        out: list[FreedomHouseDocumentRef] = []
        y_lo = max(self._year_from, launch_catalog.FREEDOM_HOUSE_YEAR_START)
        y_hi = min(self._year_to, launch_catalog.FREEDOM_HOUSE_YEAR_END)
        for year in range(y_lo, y_hi + 1):
            for iso2 in self._countries:
                slug = self._profiles[iso2].freedom_house_slug
                url = launch_catalog.freedom_house_country_year_url(year, slug)
                out.append(
                    FreedomHouseDocumentRef(
                        year=year,
                        country_iso2=iso2,
                        country_slug=slug,
                        url=url,
                    ),
                )
        return out

    async def fetch(self, doc_ref: Any) -> str:
        if not isinstance(doc_ref, FreedomHouseDocumentRef):
            raise TypeError("doc_ref must be FreedomHouseDocumentRef")
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
        if not isinstance(doc_ref, FreedomHouseDocumentRef):
            raise TypeError("doc_ref must be FreedomHouseDocumentRef")
        if not passages:
            return
        content_hash = content_hash_from_passages(passages)
        title = parse_html_document_title(
            raw, fallback="Freedom in the World country profile"
        )
        await upsert_source_document_with_passages(
            session,
            source_family=SourceFamily.freedom_house,
            title=title[:512],
            publication_date=date(doc_ref.year, 12, 31),
            country_codes=[doc_ref.country_iso2],
            url=doc_ref.url,
            passages=passages,
            content_hash=content_hash,
        )
