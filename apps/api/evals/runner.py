"""CLI runner for the eval harness.

Discovers JSON fixtures under ``<fixtures-root>/<category>/``, validates them
against the ``Fixture`` schema, then dispatches each one to a registered scorer
and writes a single ``RunManifest`` JSON file to ``<results-root>/``.

Operational contract:

* Empty category exits 0 with a well-formed manifest containing no fixtures.
* Malformed fixture JSON or schema violations become per-fixture errors in the
  manifest and do not fail the overall run (exit 0).
* A fixture that references an unregistered scorer name is treated as a hard
  configuration error: the runner prints the offending fixtures to stderr and
  exits non-zero (no manifest is written). This catches typos before they
  silently regress an entire category.
* A database session and ``LLMClient`` are constructed only if at least one
  loaded fixture's scorer has ``requires_llm = True``. Pure deterministic runs
  (such as the CI ``citation_faithfulness`` job) never touch Postgres.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

# Register ORM tables before LLMClient persists llm_call_records (FK to users).
import audit.models  # noqa: E402, F401
import auth.models  # noqa: E402, F401
import cases.models  # noqa: E402, F401
import country_conditions.models  # noqa: E402, F401
import llm.models  # noqa: E402, F401
import orgs.models  # noqa: E402, F401
import retrieval.models  # noqa: E402, F401
from evals.fixtures import (
    CATEGORIES,
    Category,
    Fixture,
    FixtureRun,
    RunManifest,
    ScoreResult,
    fixture_size_ok,
)
from evals.paths import (
    default_fixtures_root,
    default_results_root,
    default_rubrics_root,
)
from evals.scorers import SCORER_REGISTRY, ScorerContext
from llm.client import LLMClient

_RUNNER_VERSION: Literal[1] = 1
_LOG = structlog.get_logger("evals.runner")


class UnknownScorerError(RuntimeError):
    """Raised when a fixture references a scorer name not in SCORER_REGISTRY."""

    def __init__(self, offenders: list[tuple[Path, str]]) -> None:
        self.offenders = offenders
        joined = ", ".join(f"{p.name}->{name}" for p, name in offenders)
        super().__init__(f"unknown scorer(s) in fixtures: {joined}")


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _resolve_git_sha() -> str:
    env_sha = os.environ.get("GIT_SHA")
    if env_sha:
        return env_sha.strip()[:40] or "unknown"
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        sha = proc.stdout.strip()
        if sha:
            return sha
    except (OSError, subprocess.SubprocessError):
        pass
    return "nogit"


def _configure_structlog() -> None:
    if structlog.is_configured():
        return
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _discover_fixture_paths(category_dir: Path) -> list[Path]:
    if not category_dir.is_dir():
        return []
    paths: list[Path] = []
    for entry in sorted(category_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.suffix != ".json":
            continue
        if entry.name.startswith("_"):
            continue
        paths.append(entry)
    return paths


def _load_fixture(path: Path) -> tuple[Fixture | None, str | None]:
    """Parse + validate one fixture file. Returns ``(fixture, error_message)``."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"could not read fixture: {exc}"
    if not fixture_size_ok(raw):
        return None, "fixture file exceeds maximum allowed size"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})"
    if not isinstance(data, dict):
        return None, "fixture root must be a JSON object"
    try:
        return Fixture.model_validate(data), None
    except ValidationError as exc:
        return None, _summarize_validation_error(exc)


def _summarize_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) or "validation error"


@contextlib.asynccontextmanager
async def _maybe_session(needs_llm: bool) -> AsyncIterator[AsyncSession | None]:
    if not needs_llm:
        yield None
        return
    from db.session import get_async_session_maker

    factory = get_async_session_maker()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def _score_one(
    fixture: Fixture,
    path: Path,
    fixtures_root: Path,
    ctx: ScorerContext,
) -> FixtureRun:
    scorer = SCORER_REGISTRY[fixture.scorer]
    started = time.perf_counter()
    try:
        result = await scorer.score(fixture, ctx=ctx)
    except Exception as exc:  # noqa: BLE001 - boundary: scorer error must not abort run
        result = ScoreResult(error=f"scorer raised: {exc}")
    latency_ms = int((time.perf_counter() - started) * 1000)
    rel_path = _relativize(path, fixtures_root)
    _LOG.info(
        "eval.fixture.scored",
        fixture_id=fixture.id,
        scorer=fixture.scorer,
        score=result.score,
        passed=result.passed,
        latency_ms=latency_ms,
        error=result.error,
    )
    return FixtureRun(
        fixture_id=fixture.id,
        fixture_path=rel_path,
        scorer=fixture.scorer,
        result=result,
        latency_ms=latency_ms,
    )


def _relativize(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _synthetic_id_for(path: Path, used: set[str]) -> str:
    """Generate a stable, safe id when fixture validation fails before id is known."""
    base = path.stem.lower()
    sanitized = "".join(c if c.isalnum() or c in "._-" else "-" for c in base)
    safe = sanitized[:96] or "fixture"
    candidate = safe
    suffix = 1
    while candidate in used:
        candidate = f"{safe}-{suffix}"
        suffix += 1
    return candidate


async def run_category(
    *,
    category: Category,
    fixtures_root: Path,
    rubrics_root: Path,
) -> RunManifest:
    """Run all fixtures for ``category`` and return the manifest."""
    fixtures_root = fixtures_root.resolve()
    rubrics_root = rubrics_root.resolve()
    category_dir = fixtures_root / category
    started_at = _utcnow_iso()

    paths = _discover_fixture_paths(category_dir)
    loaded: list[tuple[Path, Fixture | None, str | None]] = []
    for p in paths:
        fixture, err = _load_fixture(p)
        loaded.append((p, fixture, err))

    offenders: list[tuple[Path, str]] = []
    for p, fx, _err in loaded:
        if fx is not None and fx.scorer not in SCORER_REGISTRY:
            offenders.append((p, fx.scorer))
    if offenders:
        raise UnknownScorerError(offenders)

    needs_llm = any(
        fx is not None and SCORER_REGISTRY[fx.scorer].requires_llm
        for _p, fx, _err in loaded
    )

    _LOG.info(
        "eval.run.started",
        category=category,
        fixture_count=len(loaded),
        needs_llm=needs_llm,
    )

    fixtures_runs: list[FixtureRun] = []
    used_ids: set[str] = set()

    async with _maybe_session(needs_llm) as session:
        llm: LLMClient | None = None
        if session is not None:
            llm = LLMClient(session, organization_id=None, user_id=None)
        ctx = ScorerContext(llm=llm, rubrics_root=rubrics_root, session=session)

        for p, fx, err in loaded:
            if fx is None:
                synthetic_id = _synthetic_id_for(p, used_ids)
                used_ids.add(synthetic_id)
                fixtures_runs.append(
                    FixtureRun(
                        fixture_id=synthetic_id,
                        fixture_path=_relativize(p, fixtures_root),
                        scorer="<invalid>",
                        result=ScoreResult(error=err or "unknown validation error"),
                        latency_ms=0,
                    ),
                )
                continue
            used_ids.add(fx.id)
            fixtures_runs.append(
                await _score_one(fx, p, fixtures_root, ctx),
            )

    finished_at = _utcnow_iso()
    manifest = RunManifest(
        runner_version=_RUNNER_VERSION,
        run_id=uuid.uuid4().hex[:16],
        git_sha=_resolve_git_sha(),
        category=category,
        started_at=started_at,
        finished_at=finished_at,
        fixtures_root=str(fixtures_root),
        fixtures=fixtures_runs,
    )

    _LOG.info(
        "eval.run.finished",
        category=category,
        fixture_count=len(fixtures_runs),
        errors=sum(1 for r in fixtures_runs if r.result.error is not None),
    )
    return manifest


def _default_output_path(results_root: Path, category: Category, git_sha: str) -> Path:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return results_root / f"{git_sha}-{category}-{stamp}.json"


def _write_manifest(manifest: RunManifest, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump(mode="json")
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    output.write_text(serialized, encoding="utf-8")


def _parse_args(argv: Iterable[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="evals.runner",
        description="Run an eval category and write a versioned result manifest.",
    )
    parser.add_argument(
        "--category",
        required=True,
        choices=CATEGORIES,
        help="Eval category to run.",
    )
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=None,
        help="Directory containing per-category fixture folders. "
        "Defaults to repo-root evals/fixtures.",
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=None,
        help="Directory to write the result manifest. "
        "Defaults to repo-root evals/results.",
    )
    parser.add_argument(
        "--rubrics-root",
        type=Path,
        default=None,
        help="Directory containing rubric markdown files. "
        "Defaults to repo-root evals/rubrics.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Explicit output path; overrides the auto-generated filename.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    _configure_structlog()
    args = _parse_args(argv)
    fixtures_root = (args.fixtures_root or default_fixtures_root()).resolve()
    results_root = (args.results_root or default_results_root()).resolve()
    rubrics_root = (args.rubrics_root or default_rubrics_root()).resolve()

    try:
        manifest = asyncio.run(
            run_category(
                category=args.category,
                fixtures_root=fixtures_root,
                rubrics_root=rubrics_root,
            ),
        )
    except UnknownScorerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output_path = args.output or _default_output_path(
        results_root,
        args.category,
        manifest.git_sha,
    )
    _write_manifest(manifest, output_path)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
