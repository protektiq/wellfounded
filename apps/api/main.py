from __future__ import annotations

import logging
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from audit.middleware import RequestContextMiddleware
from auth.routes import router as auth_router
from config import Settings, get_settings
from orgs.router import router as orgs_router


def _configure_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _configure_structlog()
    yield


app = FastAPI(title="Wellfounded API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)


def _cors_allow_origins() -> list[str]:
    """Browser clients (Next.js) call the API with cookies; origins must be explicit."""
    settings = get_settings()
    origins = list(settings.resolved_webauthn_expected_origins())
    for extra in ("http://127.0.0.1:3000", "http://localhost:3000"):
        if extra not in origins:
            origins.append(extra)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)
app.include_router(orgs_router)
app.include_router(auth_router)

# Register ORM models with SQLAlchemy metadata.
import audit.models  # noqa: E402, F401
import auth.models  # noqa: E402, F401
import orgs.models  # noqa: E402, F401


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_app_version(settings: Settings) -> str:
    if settings.git_sha:
        return settings.git_sha.strip()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
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
    return "unknown"


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "version": resolve_app_version(settings),
    }
