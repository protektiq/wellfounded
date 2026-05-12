"""Ingest US State Department Country Reports on Human Rights Practices (HTML)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from retrieval.ingestion.base import Passage, SourceIngester
from retrieval.models import SourceDocument, SourceFamily, SourcePassage

# MVP scope: 2024 report and three ISO 3166-1 alpha-2 countries only.
_ALLOWED_YEARS = frozenset({2024})
_COUNTRY_SLUGS: dict[str, str] = {
    "ER": "eritrea",
    "HN": "honduras",
    "VE": "venezuela",
}

_STATE_DEPT_BASE = (
    "https://www.state.gov/reports/{year}-country-reports-on-human-rights-practices/{slug}/"
)


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True)
class StateDeptDocumentRef:
    year: int
    country_iso2: str
    slug: str
    url: str


def _report_url(year: int, slug: str) -> str:
    return _STATE_DEPT_BASE.format(year=year, slug=slug)


def _token_estimate(text: str) -> int:
    # Rough token count without tiktoken; tiktoken can replace this later.
    return max(1, len(text) // 4)


def _title_from_html(raw: str) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    title_tag = soup.find("title")
    if isinstance(title_tag, Tag):
        title_text = title_tag.get_text()
        if title_text.strip():
            return _normalize_ws(title_text)
    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        return _normalize_ws(h1.get_text())
    return "Country Report on Human Rights Practices"


def parse_state_dept_html(raw: str) -> list[Passage]:
    """One passage per H2 or H3 block; section anchor is the heading text."""
    soup = BeautifulSoup(raw, "html.parser")
    raw_root = soup.find("article") or soup.find("main") or soup.body
    if not isinstance(raw_root, Tag):
        return []
    root = raw_root
    passages: list[Passage] = []
    for heading in root.find_all(["h2", "h3"]):
        anchor = _normalize_ws(heading.get_text(separator=" ", strip=True))
        if not anchor:
            continue
        chunks: list[str] = []
        for sib in heading.find_next_siblings():
            name = getattr(sib, "name", None)
            if name in ("h2", "h3"):
                break
            if name is None:
                continue
            chunk = sib.get_text(separator=" ", strip=True)
            if chunk:
                chunks.append(chunk)
        body = _normalize_ws(" ".join(chunks))
        if not body:
            continue
        passages.append(
            Passage(
                section_anchor=anchor,
                page_number=None,
                text=body,
                token_count=_token_estimate(body),
            ),
        )
    return passages


def _content_hash(passages: Sequence[Passage]) -> str:
    """SHA-256 of normalized passage anchors and bodies (stable idempotency key)."""
    lines: list[str] = []
    for p in passages:
        lines.append(f"{_normalize_ws(p.section_anchor)}\n{_normalize_ws(p.text)}")
    canon = "\n\n".join(lines).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


class StateDeptIngester(SourceIngester):
    """Fetches and parses State Dept human rights country report pages."""

    def __init__(
        self,
        *,
        year: int,
        countries: list[str],
        fixture_html: str | None = None,
        fixture_path: Path | None = None,
    ) -> None:
        if year not in _ALLOWED_YEARS:
            msg = f"year {year} is not supported in MVP (allowed: {_ALLOWED_YEARS})"
            raise ValueError(msg)
        upper = [c.strip().upper() for c in countries]
        for c in upper:
            if c not in _COUNTRY_SLUGS:
                allowed = sorted(_COUNTRY_SLUGS.keys())
                raise ValueError(f"country {c} is not in MVP allowlist {allowed}")
        self._year = year
        self._countries = upper
        self._fixture_html = fixture_html
        self._fixture_path = fixture_path

    def discover(self) -> list[StateDeptDocumentRef]:
        return [
            StateDeptDocumentRef(
                year=self._year,
                country_iso2=iso2,
                slug=_COUNTRY_SLUGS[iso2],
                url=_report_url(self._year, _COUNTRY_SLUGS[iso2]),
            )
            for iso2 in self._countries
        ]

    async def fetch(self, doc_ref: Any) -> str:
        if not isinstance(doc_ref, StateDeptDocumentRef):
            raise TypeError("doc_ref must be StateDeptDocumentRef")
        if self._fixture_html is not None:
            return self._fixture_html
        if self._fixture_path is not None:
            return self._fixture_path.read_text(encoding="utf-8")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(doc_ref.url)
            response.raise_for_status()
            return response.text

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
        for p in passages:
            if p.embedding is None:
                raise ValueError("passages must be embedded before upsert")
        content_hash = _content_hash(passages)
        existing = await session.scalar(
            select(SourceDocument.id).where(
                SourceDocument.source_family == SourceFamily.state_dept_human_rights,
                SourceDocument.content_hash == content_hash,
            ),
        )
        if existing is not None:
            return

        title = _title_from_html(raw)
        now = datetime.now(UTC)
        doc = SourceDocument(
            source_family=SourceFamily.state_dept_human_rights,
            title=title,
            publication_date=date(doc_ref.year, 12, 31),
            country_codes=[doc_ref.country_iso2],
            url=doc_ref.url,
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
