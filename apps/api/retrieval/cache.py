"""Redis-backed cache for retrieval vector candidate passage IDs."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

import redis.asyncio as redis_async

from config import Settings, get_settings

_REDIS_CLIENT: redis_async.Redis | None = None
_CACHE_KEY_PREFIX = "retrieval:v1:candidates:"
_CACHE_TTL_SECONDS = 86_400


def _canonical_cache_payload(
    *,
    query: str,
    country_codes: list[str],
    date_after: date | None,
    source_families: tuple[str, ...] | None,
    candidate_limit: int,
    top_k: int,
) -> bytes:
    payload = {
        "candidate_limit": candidate_limit,
        "country_codes": sorted(c.upper() for c in country_codes),
        "date_after": date_after.isoformat() if date_after is not None else None,
        "query": query.strip(),
        "source_families": sorted(source_families) if source_families else None,
        "top_k": top_k,
    }
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def build_retrieval_cache_key(
    *,
    query: str,
    country_codes: list[str],
    date_after: date | None,
    source_families: tuple[str, ...] | None,
    candidate_limit: int,
    top_k: int,
) -> str:
    digest = hashlib.sha256(
        _canonical_cache_payload(
            query=query,
            country_codes=country_codes,
            date_after=date_after,
            source_families=source_families,
            candidate_limit=candidate_limit,
            top_k=top_k,
        ),
    ).hexdigest()
    return f"{_CACHE_KEY_PREFIX}{digest}"


@runtime_checkable
class RetrievalCache(Protocol):
    async def get_candidate_ids(self, cache_key: str) -> list[uuid.UUID] | None: ...

    async def set_candidate_ids(
        self,
        cache_key: str,
        passage_ids: list[uuid.UUID],
    ) -> None: ...


@dataclass
class NullRetrievalCache:
    async def get_candidate_ids(self, cache_key: str) -> list[uuid.UUID] | None:
        _ = cache_key
        return None

    async def set_candidate_ids(
        self,
        cache_key: str,
        passage_ids: list[uuid.UUID],
    ) -> None:
        _ = cache_key, passage_ids


@dataclass
class DictRetrievalCache:
    """In-memory cache for tests (same contract as Redis)."""

    store: dict[str, list[uuid.UUID]]

    async def get_candidate_ids(self, cache_key: str) -> list[uuid.UUID] | None:
        return self.store.get(cache_key)

    async def set_candidate_ids(
        self,
        cache_key: str,
        passage_ids: list[uuid.UUID],
    ) -> None:
        self.store[cache_key] = list(passage_ids)


def _shared_redis_client(settings: Settings) -> redis_async.Redis:
    global _REDIS_CLIENT
    if _REDIS_CLIENT is None:
        _REDIS_CLIENT = redis_async.from_url(  # type: ignore[no-untyped-call]
            settings.redis_url,
            decode_responses=True,
        )
    return _REDIS_CLIENT


def reset_shared_redis_client_for_tests() -> None:
    """Drop the process-global Redis client (tests only)."""
    global _REDIS_CLIENT
    _REDIS_CLIENT = None


@dataclass
class RedisRetrievalCache:
    client: redis_async.Redis

    async def get_candidate_ids(self, cache_key: str) -> list[uuid.UUID] | None:
        raw = await self.client.get(cache_key)
        if raw is None:
            return None
        if not isinstance(raw, str):
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, list):
            return None
        out: list[uuid.UUID] = []
        for item in data:
            if not isinstance(item, str):
                return None
            out.append(uuid.UUID(item))
        return out

    async def set_candidate_ids(
        self,
        cache_key: str,
        passage_ids: list[uuid.UUID],
    ) -> None:
        payload = json.dumps([str(pid) for pid in passage_ids])
        await self.client.set(cache_key, payload, ex=_CACHE_TTL_SECONDS)


def default_retrieval_cache(settings: Settings | None = None) -> RetrievalCache:
    s = settings if settings is not None else get_settings()
    if not s.retrieval_cache_enabled:
        return NullRetrievalCache()
    return RedisRetrievalCache(_shared_redis_client(s))
