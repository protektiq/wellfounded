"""EUAA COI ingestion: PDF-derived text parsing."""

from __future__ import annotations

from retrieval.ingestion.euaa_coi import EuaaCoiIngester


def test_parse_euaa_plain_text_produces_passages() -> None:
    body = "Country guidance analysis. " * 80
    ing = EuaaCoiIngester(fixture_plain_text=body)
    passages = ing.parse(body)
    assert len(passages) >= 1
