"""Persistence for country conditions memos (organization-scoped)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cases.models import Case, CaseArtifact, CaseArtifactType
from country_conditions.models import CountryConditionsMemo, CountryConditionsMemoStatus


class CountryConditionsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def case_exists_for_org(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> bool:
        stmt = select(Case.id).where(
            Case.id == case_id,
            Case.organization_id == organization_id,
            Case.deleted_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create_memo_with_artifact(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        *,
        inputs: dict[str, Any],
        generated_by_user_id: uuid.UUID,
        correlation_request_id: uuid.UUID | None,
    ) -> CountryConditionsMemo:
        case_stmt = (
            select(Case)
            .where(
                Case.id == case_id,
                Case.organization_id == organization_id,
                Case.deleted_at.is_(None),
            )
            .with_for_update()
        )
        locked = await self._session.execute(case_stmt)
        case_row = locked.scalar_one_or_none()
        if case_row is None:
            raise ValueError("case not found for organization")

        stmt = select(func.coalesce(func.max(CountryConditionsMemo.version), 0)).where(
            CountryConditionsMemo.organization_id == organization_id,
            CountryConditionsMemo.case_id == case_id,
        )
        result = await self._session.execute(stmt)
        next_version = int(result.scalar_one()) + 1

        artifact = CaseArtifact(
            id=uuid.uuid4(),
            case_id=case_id,
            artifact_type=CaseArtifactType.country_conditions_memo,
        )
        self._session.add(artifact)
        await self._session.flush()

        memo = CountryConditionsMemo(
            id=uuid.uuid4(),
            organization_id=organization_id,
            case_id=case_id,
            case_artifact_id=artifact.id,
            status=CountryConditionsMemoStatus.pending,
            inputs=inputs,
            output=None,
            version=next_version,
            generated_by_user_id=generated_by_user_id,
            generated_at=None,
            model_versions={},
            error_message=None,
            correlation_request_id=correlation_request_id,
        )
        self._session.add(memo)
        await self._session.flush()
        return memo

    async def get_memo(
        self,
        organization_id: uuid.UUID,
        memo_id: uuid.UUID,
    ) -> CountryConditionsMemo | None:
        stmt = select(CountryConditionsMemo).where(
            CountryConditionsMemo.organization_id == organization_id,
            CountryConditionsMemo.id == memo_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_memos_for_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> list[CountryConditionsMemo]:
        stmt = (
            select(CountryConditionsMemo)
            .where(
                CountryConditionsMemo.organization_id == organization_id,
                CountryConditionsMemo.case_id == case_id,
            )
            .order_by(CountryConditionsMemo.version.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_memo_status(
        self,
        organization_id: uuid.UUID,
        memo_id: uuid.UUID,
        status: CountryConditionsMemoStatus,
    ) -> None:
        stmt = (
            update(CountryConditionsMemo)
            .where(
                CountryConditionsMemo.organization_id == organization_id,
                CountryConditionsMemo.id == memo_id,
            )
            .values(status=status)
        )
        await self._session.execute(stmt)

    async def update_memo_complete(
        self,
        organization_id: uuid.UUID,
        memo_id: uuid.UUID,
        *,
        output: dict[str, Any],
        model_versions: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC)
        stmt = (
            update(CountryConditionsMemo)
            .where(
                CountryConditionsMemo.organization_id == organization_id,
                CountryConditionsMemo.id == memo_id,
            )
            .values(
                status=CountryConditionsMemoStatus.complete,
                output=output,
                model_versions=model_versions,
                generated_at=now,
                error_message=None,
            )
        )
        await self._session.execute(stmt)

    async def update_memo_failed(
        self,
        organization_id: uuid.UUID,
        memo_id: uuid.UUID,
        *,
        error_message: str,
    ) -> None:
        stmt = (
            update(CountryConditionsMemo)
            .where(
                CountryConditionsMemo.organization_id == organization_id,
                CountryConditionsMemo.id == memo_id,
            )
            .values(
                status=CountryConditionsMemoStatus.failed,
                error_message=error_message[:8000],
            )
        )
        await self._session.execute(stmt)
