"""Deterministic S3 object keys for tenant-scoped blobs."""

from __future__ import annotations

import uuid


def interview_audio_storage_key(
    organization_id: uuid.UUID,
    case_id: uuid.UUID,
    audio_id: uuid.UUID,
) -> str:
    return f"{organization_id}/{case_id}/{audio_id}.enc"
