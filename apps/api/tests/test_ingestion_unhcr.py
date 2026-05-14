"""UNHCR ingestion: PDF-derived text parsing."""

from __future__ import annotations

from retrieval.ingestion.unhcr import UnhcrIngester


def test_parse_unhcr_plain_text_produces_passages() -> None:
    body = "Eligibility context. " * 80
    ing = UnhcrIngester(fixture_plain_text=body)
    passages = ing.parse(body)
    assert len(passages) >= 1
