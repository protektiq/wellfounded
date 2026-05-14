"""USCIRF ingestion: PDF-derived text parsing."""

from __future__ import annotations

from retrieval.ingestion.uscirf import UscirfIngester


def test_parse_uscirf_plain_text_produces_passages() -> None:
    body = "Intro paragraph. " * 50
    ing = UscirfIngester(
        year_from=2024,
        year_to=2024,
        fixture_plain_text=body,
    )
    passages = ing.parse(body)
    assert len(passages) >= 1
    assert passages[0].section_anchor.startswith("Extract")
