"""CLI to ingest source documents into Postgres (pgvector).

Run from ``apps/api``::

    poetry run python -m scripts.ingest --source state_dept \\
        --year-from 2024 --year-to 2024 --countries ER

With a saved HTML fixture (no network)::

    poetry run python -m scripts.ingest --source state_dept \\
        --year-from 2024 --year-to 2024 --countries ER \\
        --fixture-path tests/fixtures/state_dept_eritrea_2024.html
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Register ORM tables before LLMClient persists llm_call_records during embed.
import audit.models  # noqa: E402, F401
import auth.models  # noqa: E402, F401
import cases.models  # noqa: E402, F401
import country_conditions.models  # noqa: E402, F401
import llm.models  # noqa: E402, F401
import orgs.models  # noqa: E402, F401
import retrieval.models  # noqa: E402, F401
from db.session import get_async_session_maker
from retrieval.ingestion import launch_catalog
from retrieval.ingestion.amnesty import AmnestyDocumentRef, AmnestyIngester
from retrieval.ingestion.base import SourceIngester
from retrieval.ingestion.cpj import CpjDocumentRef, CpjIngester
from retrieval.ingestion.euaa_coi import EuaaCoiDocumentRef, EuaaCoiIngester
from retrieval.ingestion.freedom_house import (
    FreedomHouseDocumentRef,
    FreedomHouseIngester,
)
from retrieval.ingestion.hrw import HrwDocumentRef, HrwIngester
from retrieval.ingestion.state_dept import StateDeptDocumentRef, StateDeptIngester
from retrieval.ingestion.unhcr import UnhcrDocumentRef, UnhcrIngester
from retrieval.ingestion.uscirf import UscirfDocumentRef, UscirfIngester


def _parse_countries(raw: str | None) -> list[str] | None:
    if raw is None or not raw.strip():
        return None
    parts = [p.strip().upper() for p in raw.split(",") if p.strip()]
    if len(parts) > 200:
        raise ValueError("too many country codes (max 200)")
    for i, c in enumerate(parts):
        if len(c) != 2 or not c.isalpha():
            raise ValueError(f"invalid ISO2 at index {i}: {c!r}")
    return parts


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest source library documents.")
    parser.add_argument(
        "--source",
        required=True,
        choices=[
            "state_dept",
            "uscirf",
            "unhcr",
            "hrw",
            "amnesty",
            "freedom_house",
            "cpj",
            "euaa_coi",
        ],
        help="Ingestion pipeline to run",
    )
    parser.add_argument(
        "--year-from",
        type=int,
        default=None,
        help="Inclusive start year (sources that are year-scoped)",
    )
    parser.add_argument(
        "--year-to",
        type=int,
        default=None,
        help="Inclusive end year (sources that are year-scoped)",
    )
    parser.add_argument(
        "--countries",
        type=str,
        default=None,
        help="Comma-separated ISO 3166-1 alpha-2 codes (subset of launch catalog)",
    )
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=None,
        help="Optional file path; fetch reads this file instead of HTTP",
    )
    parser.add_argument(
        "--fixture-country",
        type=str,
        default="ER",
        help=(
            "When using --fixture-path, ISO2 metadata for HTML country sources "
            "(default ER)"
        ),
    )
    parser.add_argument(
        "--fixture-year",
        type=int,
        default=2024,
        help="When using --fixture-path, report year metadata for year-scoped sources",
    )
    return parser.parse_args(argv)


def _year_range(
    args: argparse.Namespace,
    *,
    default_start: int,
    default_end: int,
) -> tuple[int, int]:
    y0 = args.year_from if args.year_from is not None else default_start
    y1 = args.year_to if args.year_to is not None else default_end
    return y0, y1


async def _async_main(argv: list[str] | None) -> int:
    args = _parse_args(argv)
    countries = _parse_countries(args.countries)
    fixture_path = args.fixture_path
    if fixture_path is not None:
        if not fixture_path.is_file():
            print(f"Fixture not found: {fixture_path}", file=sys.stderr)
            return 2

    ingester: SourceIngester
    if args.source == "state_dept":
        y0, y1 = _year_range(
            args,
            default_start=launch_catalog.STATE_DEPT_YEAR_START,
            default_end=launch_catalog.STATE_DEPT_YEAR_END,
        )
        single: StateDeptDocumentRef | None = None
        if fixture_path is not None:
            fc = args.fixture_country.strip().upper()
            prof = launch_catalog.country_profile(fc)
            fy = args.fixture_year
            single = StateDeptDocumentRef(
                year=fy,
                country_iso2=fc,
                slug=prof.state_dept_slug,
                url=launch_catalog.state_dept_report_url(fy, prof.state_dept_slug),
            )
        ingester = StateDeptIngester(
            year_from=y0,
            year_to=y1,
            countries=countries,
            fixture_path=fixture_path,
            single_fixture_ref=single,
        )
    elif args.source == "uscirf":
        y0, y1 = _year_range(
            args,
            default_start=launch_catalog.USCIRF_YEAR_START,
            default_end=launch_catalog.USCIRF_YEAR_END,
        )
        single_pdf: UscirfDocumentRef | None = None
        if fixture_path is not None:
            single_pdf = UscirfDocumentRef(
                report_year=args.fixture_year,
                url=f"fixture://uscirf/{fixture_path.name}",
            )
        ingester = UscirfIngester(
            year_from=y0,
            year_to=y1,
            fixture_path=fixture_path,
            single_ref=single_pdf,
        )
    elif args.source == "unhcr":
        single_u: UnhcrDocumentRef | None = None
        if fixture_path is not None:
            fc = args.fixture_country.strip().upper()
            single_u = UnhcrDocumentRef(
                url=f"fixture://unhcr/{fixture_path.name}",
                country_codes=[fc],
                publication_year=args.fixture_year,
                title="UNHCR fixture document",
            )
        ingester = UnhcrIngester(
            fixture_path=fixture_path,
            single_ref=single_u,
        )
    elif args.source == "hrw":
        y0, y1 = _year_range(
            args,
            default_start=launch_catalog.HRW_YEAR_START,
            default_end=launch_catalog.HRW_YEAR_END,
        )
        single_h: HrwDocumentRef | None = None
        if fixture_path is not None:
            fc = args.fixture_country.strip().upper()
            prof = launch_catalog.country_profile(fc)
            fy = args.fixture_year
            single_h = HrwDocumentRef(
                year=fy,
                country_iso2=fc,
                chapter_slug=prof.hrw_chapter_slug,
                url=launch_catalog.hrw_world_report_chapter_url(
                    fy, prof.hrw_chapter_slug
                ),
            )
        ingester = HrwIngester(
            year_from=y0,
            year_to=y1,
            countries=countries,
            fixture_path=fixture_path,
            single_ref=single_h,
        )
    elif args.source == "amnesty":
        single_a: AmnestyDocumentRef | None = None
        if fixture_path is not None:
            fc = args.fixture_country.strip().upper()
            prof = launch_catalog.country_profile(fc)
            single_a = AmnestyDocumentRef(
                country_iso2=fc,
                location_path=prof.amnesty_location_path,
                url=launch_catalog.amnesty_country_url(prof.amnesty_location_path),
            )
        ingester = AmnestyIngester(
            countries=countries,
            fixture_path=fixture_path,
            single_ref=single_a,
        )
    elif args.source == "freedom_house":
        y0, y1 = _year_range(
            args,
            default_start=launch_catalog.FREEDOM_HOUSE_YEAR_START,
            default_end=launch_catalog.FREEDOM_HOUSE_YEAR_END,
        )
        single_f: FreedomHouseDocumentRef | None = None
        if fixture_path is not None:
            fc = args.fixture_country.strip().upper()
            prof = launch_catalog.country_profile(fc)
            fy = args.fixture_year
            single_f = FreedomHouseDocumentRef(
                year=fy,
                country_iso2=fc,
                country_slug=prof.freedom_house_slug,
                url=launch_catalog.freedom_house_country_year_url(
                    fy, prof.freedom_house_slug
                ),
            )
        ingester = FreedomHouseIngester(
            year_from=y0,
            year_to=y1,
            countries=countries,
            fixture_path=fixture_path,
            single_ref=single_f,
        )
    elif args.source == "cpj":
        single_c: CpjDocumentRef | None = None
        if fixture_path is not None:
            fc = args.fixture_country.strip().upper()
            prof = launch_catalog.country_profile(fc)
            single_c = CpjDocumentRef(
                country_iso2=fc,
                path_under_cpj=prof.cpj_path,
                url=launch_catalog.cpj_country_url(prof.cpj_path),
            )
        ingester = CpjIngester(
            countries=countries,
            fixture_path=fixture_path,
            single_ref=single_c,
        )
    elif args.source == "euaa_coi":
        single_e: EuaaCoiDocumentRef | None = None
        if fixture_path is not None:
            fc = args.fixture_country.strip().upper()
            single_e = EuaaCoiDocumentRef(
                url=f"fixture://euaa_coi/{fixture_path.name}",
                country_codes=[fc],
                publication_year=args.fixture_year,
                title="EUAA COI fixture document",
            )
        ingester = EuaaCoiIngester(
            fixture_path=fixture_path,
            single_ref=single_e,
        )
    else:
        raise AssertionError("unhandled source")

    factory = get_async_session_maker()
    async with factory() as session:
        if not isinstance(ingester, SourceIngester):
            raise TypeError("ingester must be SourceIngester")
        await ingester.run(session)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main(None)))
