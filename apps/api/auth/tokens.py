"""Magic-link raw token generation and SHA-256 hashing (no JWT)."""

from __future__ import annotations

import hashlib
import secrets


def generate_raw_token() -> str:
    """Return a URL-safe opaque token suitable for a single-use magic link."""
    return secrets.token_urlsafe(32)


def hash_token(raw: str) -> bytes:
    """Return the SHA-256 digest of the raw token (32 bytes)."""
    return hashlib.sha256(raw.encode("utf-8")).digest()
