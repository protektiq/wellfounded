"""CPJ ingestion: fixture parsing."""

from __future__ import annotations

from pathlib import Path

from retrieval.ingestion.cpj import CpjIngester

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cpj_eritrea.html"


def test_parse_cpj_fixture_has_expected_sections() -> None:
    raw = _FIXTURE.read_text(encoding="utf-8")
    ing = CpjIngester(countries=["ER"], fixture_html=raw)
    passages = ing.parse(raw)
    anchors = {p.section_anchor for p in passages}
    assert "Press freedom conditions" in anchors
    assert "Recent cases" in anchors
