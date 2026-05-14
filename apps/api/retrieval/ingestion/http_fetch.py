"""HTTP fetch helpers for ingestion (browser-like User-Agent)."""

from __future__ import annotations

import httpx

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


async def http_get_text(url: str, *, timeout_s: float = 90.0) -> str:
    async with httpx.AsyncClient(timeout=timeout_s, headers=_DEFAULT_HEADERS) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text


async def http_get_bytes(url: str, *, timeout_s: float = 120.0) -> bytes:
    headers = {
        **_DEFAULT_HEADERS,
        "Accept": "application/pdf,*/*;q=0.8",
    }
    async with httpx.AsyncClient(timeout=timeout_s, headers=headers) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content
