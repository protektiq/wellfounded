"""Human Rights Watch ingestion: fixture parsing."""

from __future__ import annotations

from pathlib import Path

from retrieval.ingestion.hrw import HrwIngester

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "hrw_eritrea_2024.html"


def test_parse_hrw_fixture_has_expected_sections() -> None:
    raw = _FIXTURE.read_text(encoding="utf-8")
    ing = HrwIngester(year_from=2024, year_to=2024, countries=["ER"], fixture_html=raw)
    passages = ing.parse(raw)
    anchors = {p.section_anchor for p in passages}
    assert "Key Rights Concerns" in anchors
    assert "Arbitrary detention" in anchors
