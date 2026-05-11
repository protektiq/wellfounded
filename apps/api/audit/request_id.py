"""RFC 9562 UUID version 7 for per-request correlation.

Python 3.12 stdlib does not provide uuid.uuid7 (added in 3.13). This module
implements the timestamp-first layout from RFC 9562 without an extra dependency.
"""

from __future__ import annotations

import secrets
import time
import uuid


def generate_request_id_v7() -> uuid.UUID:
    """Return a new UUIDv7 using the current Unix time in milliseconds."""
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = secrets.randbelow(1 << 12)
    rand_b = secrets.randbelow(1 << 62)

    b = bytearray(16)
    b[0:6] = timestamp_ms.to_bytes(6, "big")
    b[6] = (7 << 4) | ((rand_a >> 8) & 0x0F)
    b[7] = rand_a & 0xFF
    b[8] = 0x80 | ((rand_b >> 56) & 0x3F)
    b[9:16] = (rand_b & ((1 << 56) - 1)).to_bytes(7, "big")
    return uuid.UUID(bytes=bytes(b))
