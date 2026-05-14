"""Bounded launch-scope URLs and country metadata for bulk ingestion.

Operators may extend tuples below as editorial scope grows. Year ranges follow
PRD-style windows (State Dept: current year minus four through current;
USCIRF: 2020-2025 per build plan).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Inclusive calendar years for State Dept country reports (human rights practices).
STATE_DEPT_YEAR_START = 2021
STATE_DEPT_YEAR_END = 2025

# USCIRF annual report PDFs (one document per year; global scope).
USCIRF_YEAR_START = 2020
USCIRF_YEAR_END = 2025

# Freedom in the World scores pages (country + year).
FREEDOM_HOUSE_YEAR_START = 2020
FREEDOM_HOUSE_YEAR_END = 2025

# Human Rights Watch World Report country chapters.
HRW_YEAR_START = 2020
HRW_YEAR_END = 2025


@dataclass(frozen=True)
class CountryLaunchProfile:
    """Per-country URL path segments for sources that publish country pages."""

    iso2: str
    state_dept_slug: str
    hrw_chapter_slug: str
    freedom_house_slug: str
    amnesty_location_path: str
    cpj_path: str


# High-priority asylum COI countries; slug fields verified against live URL patterns.
LAUNCH_COUNTRY_PROFILES: tuple[CountryLaunchProfile, ...] = (
    CountryLaunchProfile(
        "ER",
        "eritrea",
        "eritrea",
        "eritrea",
        "africa/east-africa/eritrea",
        "africa/eritrea",
    ),
    CountryLaunchProfile(
        "ET",
        "ethiopia",
        "ethiopia",
        "ethiopia",
        "africa/east-africa/ethiopia",
        "africa/ethiopia",
    ),
    CountryLaunchProfile(
        "SO",
        "somalia",
        "somalia",
        "somalia",
        "africa/east-africa/somalia",
        "africa/somalia",
    ),
    CountryLaunchProfile(
        "SD", "sudan", "sudan", "sudan", "africa/east-africa/sudan", "africa/sudan"
    ),
    CountryLaunchProfile(
        "SS",
        "south-sudan",
        "south-sudan",
        "south-sudan",
        "africa/east-africa/south-sudan",
        "africa/south-sudan",
    ),
    CountryLaunchProfile(
        "CF",
        "central-african-republic",
        "central-african-republic",
        "central-african-republic",
        "africa/central-africa/central-african-republic",
        "africa/central-african-republic",
    ),
    CountryLaunchProfile(
        "CM",
        "cameroon",
        "cameroon",
        "cameroon",
        "africa/west-and-central-africa/cameroon",
        "africa/cameroon",
    ),
    CountryLaunchProfile(
        "NG",
        "nigeria",
        "nigeria",
        "nigeria",
        "africa/west-and-central-africa/nigeria",
        "africa/nigeria",
    ),
    CountryLaunchProfile(
        "ML",
        "mali",
        "mali",
        "mali",
        "africa/west-and-central-africa/mali",
        "africa/mali",
    ),
    CountryLaunchProfile(
        "NE",
        "niger",
        "niger",
        "niger",
        "africa/west-and-central-africa/niger",
        "africa/niger",
    ),
    CountryLaunchProfile(
        "SY",
        "syria",
        "syria",
        "syria",
        "middle-east-and-north-africa/syria",
        "middle-east-north-africa/syria",
    ),
    CountryLaunchProfile(
        "IQ",
        "iraq",
        "iraq",
        "iraq",
        "middle-east-and-north-africa/iraq",
        "middle-east-north-africa/iraq",
    ),
    CountryLaunchProfile(
        "YE",
        "yemen",
        "yemen",
        "yemen",
        "middle-east-and-north-africa/yemen",
        "middle-east-north-africa/yemen",
    ),
    CountryLaunchProfile(
        "AF",
        "afghanistan",
        "afghanistan",
        "afghanistan",
        "asia-and-pacific/afghanistan",
        "asia/afghanistan",
    ),
    CountryLaunchProfile(
        "MM", "burma", "burma", "myanmar", "asia-and-pacific/myanmar", "asia/myanmar"
    ),
    CountryLaunchProfile(
        "UA",
        "ukraine",
        "ukraine",
        "ukraine",
        "europe-and-central-asia/ukraine",
        "europe/ukraine",
    ),
    CountryLaunchProfile(
        "BY",
        "belarus",
        "belarus",
        "belarus",
        "europe-and-central-asia/belarus",
        "europe/belarus",
    ),
    CountryLaunchProfile(
        "RU",
        "russia",
        "russia",
        "russia",
        "europe-and-central-asia/russia",
        "europe/russia",
    ),
    CountryLaunchProfile(
        "VE",
        "venezuela",
        "venezuela",
        "venezuela",
        "americas/venezuela",
        "americas/venezuela",
    ),
    CountryLaunchProfile(
        "CU", "cuba", "cuba", "cuba", "americas/cuba", "americas/cuba"
    ),
    CountryLaunchProfile(
        "NI",
        "nicaragua",
        "nicaragua",
        "nicaragua",
        "americas/nicaragua",
        "americas/nicaragua",
    ),
    CountryLaunchProfile(
        "HN",
        "honduras",
        "honduras",
        "honduras",
        "americas/honduras",
        "americas/honduras",
    ),
    CountryLaunchProfile(
        "GT",
        "guatemala",
        "guatemala",
        "guatemala",
        "americas/guatemala",
        "americas/guatemala",
    ),
    CountryLaunchProfile(
        "HT", "haiti", "haiti", "haiti", "americas/haiti", "americas/haiti"
    ),
    CountryLaunchProfile(
        "CO",
        "colombia",
        "colombia",
        "colombia",
        "americas/colombia",
        "americas/colombia",
    ),
    CountryLaunchProfile(
        "IR",
        "iran",
        "iran",
        "iran",
        "middle-east-and-north-africa/iran",
        "middle-east-north-africa/iran",
    ),
    CountryLaunchProfile(
        "PK",
        "pakistan",
        "pakistan",
        "pakistan",
        "asia-and-pacific/pakistan",
        "asia/pakistan",
    ),
    CountryLaunchProfile(
        "CN", "china", "china", "china", "asia-and-pacific/china", "asia/china"
    ),
    CountryLaunchProfile(
        "TR",
        "turkey",
        "turkey",
        "turkey",
        "europe-and-central-asia/turkey",
        "europe/turkey",
    ),
)


def calendar_year_today() -> int:
    return date.today().year


def state_dept_report_url(year: int, slug: str) -> str:
    return f"https://www.state.gov/reports/{year}-country-reports-on-human-rights-practices/{slug}/"


def hrw_world_report_chapter_url(year: int, chapter_slug: str) -> str:
    return f"https://www.hrw.org/world-report/{year}/country-chapters/{chapter_slug}"


def freedom_house_country_year_url(year: int, country_slug: str) -> str:
    return f"https://freedomhouse.org/country/{country_slug}/freedom-world/{year}"


def amnesty_country_url(location_path: str) -> str:
    return f"https://www.amnesty.org/en/location/{location_path}/"


def cpj_country_url(path_under_cpj: str) -> str:
    base = path_under_cpj.strip().strip("/")
    return f"https://cpj.org/{base}/"


# USCIRF annual report PDF URLs (spot-checked 2026-05; extend when USCIRF
# publishes new paths).
USCIRF_ANNUAL_REPORT_PDF: dict[int, str] = {
    2022: "https://www.uscirf.gov/sites/default/files/2022%20Annual%20Report.pdf",
    2024: "https://www.uscirf.gov/sites/default/files/2024-05/USCIRF%202024%20Annual%20Report.pdf",
}

# UNHCR data portal PDF downloads (document id stable; expand list over time).
UNHCR_DATA2_PDF_DOWNLOADS: tuple[tuple[str, list[str], int, str], ...] = (
    (
        "https://data2.unhcr.org/en/documents/download/46114",
        ["ER"],
        2016,
        "UNHCR data portal document 46114",
    ),
    (
        "https://data2.unhcr.org/en/documents/download/62744",
        ["VE"],
        2020,
        "UNHCR data portal document 62744",
    ),
    (
        "https://data2.unhcr.org/en/documents/download/70452",
        ["SY"],
        2021,
        "UNHCR data portal document 70452",
    ),
)

# EUAA COI PDFs: populate with commission-approved URLs (paths change when
# EUAA republishes).
EUAA_COI_PDF_URLS: tuple[tuple[str, list[str], int, str], ...] = ()


def country_profile(iso2: str) -> CountryLaunchProfile:
    u = iso2.strip().upper()
    for p in LAUNCH_COUNTRY_PROFILES:
        if p.iso2 == u:
            return p
    allowed = ", ".join(sorted(x.iso2 for x in LAUNCH_COUNTRY_PROFILES))
    raise KeyError(f"unknown launch-catalog country {iso2!r}; allowed: {allowed}")
