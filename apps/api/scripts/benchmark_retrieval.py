"""Benchmark retrieval latency (embed + ANN + rerank) against a populated library."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
import uuid

import structlog

from config import Settings
from db.session import get_async_session_maker
from retrieval.passage_search import search

log = structlog.get_logger()


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Run repeated retrieval.search calls and print latency stats. "
            "Requires Postgres, optional OpenAI key for embeddings, "
            "and non-empty source_passages."
        ),
    )
    p.add_argument("--iterations", type=int, default=30, help="Number of iterations (5-500)")
    p.add_argument("--country", type=str, default="ER", help="ISO2 filter (default ER)")
    p.add_argument("--top-k", type=int, default=20, help="Top-k results per search (1-100)")
    p.add_argument(
        "--disable-cache",
        action="store_true",
        help="Set retrieval_cache_enabled=false for cold-vector path",
    )
    p.add_argument(
        "--query",
        type=str,
        default="Human rights and security force practices in Eritrea.",
        help="Natural-language retrieval query",
    )
    return p.parse_args(argv)


async def _async_main(argv: list[str] | None) -> int:
    args = _parse_args(argv)
    rid = uuid.uuid4()
    try:
        structlog.contextvars.bind_contextvars(request_id=str(rid))
        cc = args.country.strip().upper()
        if len(cc) != 2 or not cc.isalpha():
            print("country must be ISO2 letters", file=sys.stderr)
            return 2
        if not 5 <= args.iterations <= 500:
            print("--iterations must be between 5 and 500", file=sys.stderr)
            return 2
        if not 1 <= args.top_k <= 100:
            print("--top-k must be between 1 and 100", file=sys.stderr)
            return 2

        settings = Settings()
        if args.disable_cache:
            settings = settings.model_copy(update={"retrieval_cache_enabled": False})

        factory = get_async_session_maker()
        lat_ms: list[float] = []
        async with factory() as session:
            for i in range(args.iterations):
                t0 = time.perf_counter()
                try:
                    await search(
                        session,
                        args.query,
                        organization_id=None,
                        user_id=None,
                        country_codes=[cc],
                        top_k=args.top_k,
                        settings=settings,
                    )
                except Exception as exc:
                    log.exception(
                        "benchmark_search_failed", iteration=i, error=str(exc)
                    )
                    print(f"Search failed at iteration {i}: {exc}", file=sys.stderr)
                    return 1
                lat_ms.append((time.perf_counter() - t0) * 1000.0)
                await session.rollback()

        lat_ms.sort()
        p50 = statistics.median(lat_ms)
        p95_idx = min(len(lat_ms) - 1, int(round(0.95 * (len(lat_ms) - 1))))
        p95 = lat_ms[p95_idx]
        print(
            f"iterations={args.iterations} top_k={args.top_k} "
            f"cache_enabled={settings.retrieval_cache_enabled} "
            f"rerank={settings.retrieval_rerank_backend}",
        )
        print(
            f"latency_ms p50={p50:.1f} p95={p95:.1f} "
            f"min={lat_ms[0]:.1f} max={lat_ms[-1]:.1f}"
        )
        return 0
    finally:
        structlog.contextvars.unbind_contextvars("request_id")


def main() -> None:
    raise SystemExit(asyncio.run(_async_main(None)))
