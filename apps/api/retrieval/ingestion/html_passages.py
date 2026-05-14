"""Shared HTML passage splitting and hashing for retrieval ingesters."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from bs4 import BeautifulSoup
from bs4.element import Tag

from retrieval.ingestion.base import Passage


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_html_document_title(raw: str, *, fallback: str) -> str:
    soup = BeautifulSoup(raw, "html.parser")
    title_tag = soup.find("title")
    if isinstance(title_tag, Tag):
        title_text = title_tag.get_text()
        if title_text.strip():
            return normalize_ws(title_text)
    h1 = soup.find("h1")
    if isinstance(h1, Tag):
        return normalize_ws(h1.get_text())
    return fallback


def token_estimate(text: str) -> int:
    return max(1, len(text) // 4)


def content_hash_from_passages(passages: Sequence[Passage]) -> str:
    """SHA-256 of normalized passage anchors and bodies (stable idempotency key)."""
    lines: list[str] = []
    for p in passages:
        lines.append(f"{normalize_ws(p.section_anchor)}\n{normalize_ws(p.text)}")
    canon = "\n\n".join(lines).encode("utf-8")
    return hashlib.sha256(canon).hexdigest()


def parse_article_by_headings(
    raw: str,
    *,
    heading_tags: tuple[str, ...] = ("h2", "h3"),
) -> list[Passage]:
    """One passage per heading block; section anchor is the heading text."""
    soup = BeautifulSoup(raw, "html.parser")
    raw_root = soup.find("article") or soup.find("main") or soup.body
    if not isinstance(raw_root, Tag):
        return []
    root = raw_root
    passages: list[Passage] = []
    for heading in root.find_all(list(heading_tags)):
        anchor = normalize_ws(heading.get_text(separator=" ", strip=True))
        if not anchor:
            continue
        chunks: list[str] = []
        for sib in heading.find_next_siblings():
            name = getattr(sib, "name", None)
            if name in heading_tags:
                break
            if name is None:
                continue
            chunk = sib.get_text(separator=" ", strip=True)
            if chunk:
                chunks.append(chunk)
        body = normalize_ws(" ".join(chunks))
        if not body:
            continue
        passages.append(
            Passage(
                section_anchor=anchor,
                page_number=None,
                text=body,
                token_count=token_estimate(body),
            ),
        )
    return passages


def parse_pdf_plain_text_to_passages(
    text: str,
    *,
    max_chars_per_passage: int = 8000,
) -> list[Passage]:
    """Split flattened PDF text into passages with synthetic section anchors."""
    cleaned = normalize_ws(text)
    if not cleaned:
        return []
    passages: list[Passage] = []
    part = 1
    start = 0
    while start < len(cleaned):
        chunk = cleaned[start : start + max_chars_per_passage].strip()
        if not chunk:
            break
        passages.append(
            Passage(
                section_anchor=f"Extract part {part}",
                page_number=None,
                text=chunk,
                token_count=token_estimate(chunk),
            ),
        )
        part += 1
        start += max_chars_per_passage
    return passages
