"""Re-ingest living-document source families (run from cron monthly or similar)."""

from __future__ import annotations

import asyncio
import uuid

import structlog

from db.session import get_async_session_maker
from retrieval.ingestion import launch_catalog
from retrieval.ingestion.freedom_house import FreedomHouseIngester
from retrieval.ingestion.state_dept import StateDeptIngester
from retrieval.ingestion.uscirf import UscirfIngester

log = structlog.get_logger()


async def _async_main() -> int:
    try:
        rid = uuid.uuid4()
        structlog.contextvars.bind_contextvars(request_id=str(rid))
        log.info("living_source_refresh_started")
        factory = get_async_session_maker()
        async with factory() as session:
            sd = StateDeptIngester(
                year_from=launch_catalog.STATE_DEPT_YEAR_START,
                year_to=launch_catalog.STATE_DEPT_YEAR_END,
                countries=None,
            )
            await sd.run(session)
            us = UscirfIngester(
                year_from=launch_catalog.USCIRF_YEAR_START,
                year_to=launch_catalog.USCIRF_YEAR_END,
            )
            await us.run(session)
            fh = FreedomHouseIngester(
                year_from=launch_catalog.FREEDOM_HOUSE_YEAR_START,
                year_to=launch_catalog.FREEDOM_HOUSE_YEAR_END,
                countries=None,
            )
            await fh.run(session)
        log.info("living_source_refresh_finished")
        return 0
    finally:
        structlog.contextvars.unbind_contextvars("request_id")


def main() -> None:
    raise SystemExit(asyncio.run(_async_main()))
