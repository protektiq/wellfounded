"""Freedom House ingestion: fixture parsing."""

from __future__ import annotations

from pathlib import Path

from retrieval.ingestion.freedom_house import FreedomHouseIngester

_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "freedom_house_eritrea_2024.html"
)


def test_parse_freedom_house_fixture_has_expected_sections() -> None:
    raw = _FIXTURE.read_text(encoding="utf-8")
    ing = FreedomHouseIngester(
        year_from=2024,
        year_to=2024,
        countries=["ER"],
        fixture_html=raw,
    )
    passages = ing.parse(raw)
    anchors = {p.section_anchor for p in passages}
    assert "Political Rights" in anchors
    assert "Civil Liberties" in anchors
