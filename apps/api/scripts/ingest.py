"""CLI to ingest source documents into Postgres (pgvector).

Run from ``apps/api``::

    poetry run python -m scripts.ingest --source state_dept --year 2024 --country ER

With a saved HTML fixture (no network)::

    poetry run python -m scripts.ingest --source state_dept --year 2024 --country ER \\
        --fixture-path tests/fixtures/state_dept_eritrea_2024.html
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from db.session import get_async_session_maker
from retrieval.ingestion.state_dept import StateDeptIngester


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest source library documents.")
    parser.add_argument(
        "--source",
        required=True,
        choices=["state_dept"],
        help="Ingestion pipeline to run",
    )
    parser.add_argument(
        "--year",
        type=int,
        required=True,
        help="Report year (MVP: 2024 only)",
    )
    parser.add_argument(
        "--country",
        required=True,
        choices=["ER", "HN", "VE"],
        help="ISO 3166-1 alpha-2 country code (MVP allowlist)",
    )
    parser.add_argument(
        "--fixture-path",
        type=Path,
        default=None,
        help=(
            "Optional path to HTML file; when set, fetch reads this file "
            "instead of HTTP"
        ),
    )
    return parser.parse_args(argv)


async def _async_main(argv: list[str] | None) -> int:
    args = _parse_args(argv)
    if args.source == "state_dept":
        if args.year != 2024:
            print("Only year 2024 is supported for state_dept in MVP.", file=sys.stderr)
            return 2
        fixture_path = args.fixture_path
        if fixture_path is not None:
            if not fixture_path.is_file():
                print(f"Fixture not found: {fixture_path}", file=sys.stderr)
                return 2
        ingester = StateDeptIngester(
            year=args.year,
            countries=[args.country],
            fixture_path=fixture_path,
        )
    else:
        raise AssertionError("unhandled source")

    factory = get_async_session_maker()
    async with factory() as session:
        await ingester.run(session)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_async_main(None)))
