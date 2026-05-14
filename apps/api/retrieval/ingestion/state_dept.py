"""Ingest US State Department Country Reports on Human Rights Practices (HTML)."""

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
class StateDeptDocumentRef:
    year: int
    country_iso2: str
    slug: str
    url: str


def _report_url(year: int, slug: str) -> str:
    return launch_catalog.state_dept_report_url(year, slug)


def parse_state_dept_html(raw: str) -> list[Passage]:
    """One passage per H2 or H3 block; section anchor is the heading text."""
    return parse_article_by_headings(raw, heading_tags=("h2", "h3"))


class StateDeptIngester(SourceIngester):
    """Fetches and parses State Dept human rights country report pages."""

    def __init__(
        self,
        *,
        year_from: int,
        year_to: int,
        countries: list[str] | None,
        fixture_html: str | None = None,
        fixture_path: Path | None = None,
        single_fixture_ref: StateDeptDocumentRef | None = None,
    ) -> None:
        y0 = min(year_from, year_to)
        y1 = max(year_from, year_to)
        if y0 < 1990 or y1 > launch_catalog.calendar_year_today() + 1:
            raise ValueError("year range is out of bounds")
        self._year_from = y0
        self._year_to = y1
        profiles = list(launch_catalog.LAUNCH_COUNTRY_PROFILES)
        iso_by_slug = {p.iso2.upper(): p for p in profiles}
        if countries is None or len(countries) == 0:
            upper = [p.iso2.upper() for p in profiles]
        else:
            upper = [c.strip().upper() for c in countries]
            for c in upper:
                if c not in iso_by_slug:
                    allowed = sorted(iso_by_slug.keys())
                    raise ValueError(f"country {c} is not in launch catalog {allowed}")
        self._countries = upper
        self._profiles = iso_by_slug
        self._fixture_html = fixture_html
        self._fixture_path = fixture_path
        self._single_fixture_ref = single_fixture_ref

    def discover(self) -> list[StateDeptDocumentRef]:
        if self._single_fixture_ref is not None:
            return [self._single_fixture_ref]
        out: list[StateDeptDocumentRef] = []
        y_lo = max(self._year_from, launch_catalog.STATE_DEPT_YEAR_START)
        y_hi = min(self._year_to, launch_catalog.STATE_DEPT_YEAR_END)
        for year in range(y_lo, y_hi + 1):
            for iso2 in self._countries:
                prof = self._profiles[iso2]
                slug = prof.state_dept_slug
                out.append(
                    StateDeptDocumentRef(
                        year=year,
                        country_iso2=iso2,
                        slug=slug,
                        url=_report_url(year, slug),
                    ),
                )
        return out

    async def fetch(self, doc_ref: Any) -> str:
        if not isinstance(doc_ref, StateDeptDocumentRef):
            raise TypeError("doc_ref must be StateDeptDocumentRef")
        if self._fixture_html is not None:
            return self._fixture_html
        if self._fixture_path is not None:
            return self._fixture_path.read_text(encoding="utf-8")
        return await http_get_text(doc_ref.url)

    def parse(self, raw: str) -> list[Passage]:
        return parse_state_dept_html(raw)

    async def upsert(
        self,
        session: AsyncSession,
        doc_ref: Any,
        raw: str,
        passages: list[Passage],
    ) -> None:
        if not isinstance(doc_ref, StateDeptDocumentRef):
            raise TypeError("doc_ref must be StateDeptDocumentRef")
        if not passages:
            return
        content_hash = content_hash_from_passages(passages)
        title = parse_html_document_title(
            raw,
            fallback="Country Report on Human Rights Practices",
        )
        await upsert_source_document_with_passages(
            session,
            source_family=SourceFamily.state_dept_human_rights,
            title=title,
            publication_date=date(doc_ref.year, 12, 31),
            country_codes=[doc_ref.country_iso2],
            url=doc_ref.url,
            passages=passages,
            content_hash=content_hash,
        )
