"""Amnesty International ingestion: fixture parsing."""

from __future__ import annotations

from pathlib import Path

from retrieval.ingestion.amnesty import AmnestyIngester

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "amnesty_eritrea.html"


def test_parse_amnesty_fixture_has_expected_sections() -> None:
    raw = _FIXTURE.read_text(encoding="utf-8")
    ing = AmnestyIngester(countries=["ER"], fixture_html=raw)
    passages = ing.parse(raw)
    anchors = {p.section_anchor for p in passages}
    assert "Human rights overview" in anchors
    assert "Detention" in anchors
