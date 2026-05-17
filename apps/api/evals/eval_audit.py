"""No-op audit writer for eval graph runs (avoids org FK requirements)."""

from __future__ import annotations

import uuid
from typing import Any


class EvalAuditWriter:
    """Audit interface for declaration graph eval runs; does not persist."""

    async def record(
        self,
        action: str,
        organization_id: uuid.UUID,
        user_id: uuid.UUID | None,
        resource_type: str,
        resource_id: uuid.UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        del action, organization_id, user_id, resource_type, resource_id, metadata
