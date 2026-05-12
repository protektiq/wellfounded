"""Async persistence for case files with organization scoping on every query."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any, Literal

from sqlalchemy import and_, delete, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from cases.models import (
    AsylumOffice,
    Case,
    CaseAssignment,
    CaseAssignmentRole,
    CaseQueryStatus,
    ClaimBasis,
)
from orgs.models import User, UserRole, UserStatus


class CaseRepositoryError(Exception):
    """Domain error from case persistence (map to HTTP in routes)."""


def _status_sql_predicate(status: CaseQueryStatus) -> ColumnElement[bool]:
    if status is CaseQueryStatus.active:
        return and_(Case.deleted_at.is_(None), Case.archived_at.is_(None))
    if status is CaseQueryStatus.archived:
        return and_(Case.deleted_at.is_(None), Case.archived_at.is_not(None))
    if status is CaseQueryStatus.deleted:
        return Case.deleted_at.is_not(None)
    return true()


class CaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_users_in_org(
        self,
        organization_id: uuid.UUID,
        user_ids: set[uuid.UUID],
    ) -> dict[uuid.UUID, User]:
        if not user_ids:
            return {}
        stmt = select(User).where(
            User.organization_id == organization_id,
            User.id.in_(user_ids),
            User.deleted_at.is_(None),
            User.status == UserStatus.active,
        )
        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        return {u.id: u for u in rows}

    async def create_case(
        self,
        *,
        organization_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        pseudonym: str,
        country_code: str,
        basis: ClaimBasis,
        group_description: str,
        filing_deadline: date | None,
        asylum_office: AsylumOffice | None,
        intake_notes: str,
        assignments: Sequence[tuple[uuid.UUID, CaseAssignmentRole]],
    ) -> Case:
        if not any(role is CaseAssignmentRole.lead_attorney for _, role in assignments):
            raise CaseRepositoryError(
                "Case requires at least one lead_attorney assignment",
            )

        user_ids = {uid for uid, _ in assignments} | {created_by_user_id}
        users = await self._get_users_in_org(organization_id, user_ids)
        if created_by_user_id not in users:
            raise CaseRepositoryError(
                "created_by user is not active in this organization",
            )
        for uid, _ in assignments:
            if uid not in users:
                raise CaseRepositoryError(
                    "Each assigned user must be active in this organization",
                )

        case = Case(
            id=uuid.uuid4(),
            organization_id=organization_id,
            pseudonym=pseudonym,
            country_code=country_code,
            basis=basis,
            group_description=group_description,
        filing_deadline=filing_deadline,
        asylum_office=asylum_office,
            intake_notes=intake_notes,
            created_by_user_id=created_by_user_id,
        )
        self._session.add(case)
        await self._session.flush()

        for uid, role in assignments:
            self._session.add(
                CaseAssignment(case_id=case.id, user_id=uid, role_on_case=role),
            )
        await self._session.flush()
        await self._session.refresh(case, attribute_names=["assignments"])
        return case

    async def get_case_for_org(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> Case | None:
        stmt = (
            select(Case)
            .options(selectinload(Case.assignments))
            .where(Case.id == case_id, Case.organization_id == organization_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_cases(
        self,
        organization_id: uuid.UUID,
        viewer: User,
        status: CaseQueryStatus,
    ) -> list[tuple[Case, Literal["full", "read_only"]]]:
        pred = _status_sql_predicate(status)
        base = (
            select(Case)
            .options(selectinload(Case.assignments))
            .where(Case.organization_id == organization_id)
            .where(pred)
        )

        if viewer.role is UserRole.admin:
            result = await self._session.execute(base.order_by(Case.created_at.desc()))
            cases = list(result.scalars().all())
            return [(c, "full") for c in cases]

        if viewer.role is UserRole.attorney:
            result = await self._session.execute(
                base.where(Case.deleted_at.is_(None)).order_by(Case.created_at.desc()),
            )
            cases = list(result.scalars().all())
            out: list[tuple[Case, Literal["full", "read_only"]]] = []
            for c in cases:
                assigned = any(a.user_id == viewer.id for a in c.assignments)
                mode: Literal["full", "read_only"] = (
                    "full" if assigned else "read_only"
                )
                out.append((c, mode))
            return out

        stmt = (
            select(Case)
            .options(selectinload(Case.assignments))
            .join(CaseAssignment, CaseAssignment.case_id == Case.id)
            .where(
                Case.organization_id == organization_id,
                CaseAssignment.user_id == viewer.id,
                Case.deleted_at.is_(None),
            )
            .where(pred)
            .order_by(Case.created_at.desc())
        )
        result = await self._session.execute(stmt)
        cases = list(result.unique().scalars().all())
        return [(c, "full") for c in cases]

    async def patch_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        updates: dict[str, Any],
    ) -> Case | None:
        allowed = {
            "pseudonym",
            "country_code",
            "basis",
            "group_description",
            "intake_notes",
            "filing_deadline",
            "asylum_office",
        }
        extra = set(updates) - allowed
        if extra:
            raise CaseRepositoryError(f"Unsupported patch fields: {sorted(extra)}")

        case = await self.get_case_for_org(organization_id, case_id)
        if case is None:
            return None

        if "pseudonym" in updates:
            case.pseudonym = str(updates["pseudonym"])
        if "country_code" in updates:
            case.country_code = str(updates["country_code"])
        if "basis" in updates:
            b = updates["basis"]
            if not isinstance(b, ClaimBasis):
                raise CaseRepositoryError("basis must be a valid claim basis")
            case.basis = b
        if "group_description" in updates:
            case.group_description = str(updates["group_description"])
        if "intake_notes" in updates:
            case.intake_notes = str(updates["intake_notes"])
        if "filing_deadline" in updates:
            fd = updates["filing_deadline"]
            if fd is not None and not isinstance(fd, date):
                raise CaseRepositoryError("filing_deadline must be a date or null")
            case.filing_deadline = fd
        if "asylum_office" in updates:
            ao = updates["asylum_office"]
            if ao is not None and not isinstance(ao, AsylumOffice):
                raise CaseRepositoryError(
                    "asylum_office must be a valid asylum office or null",
                )
            case.asylum_office = ao

        await self._session.flush()
        return case

    async def archive_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> Case | None:
        case = await self.get_case_for_org(organization_id, case_id)
        if case is None:
            return None
        if case.deleted_at is not None:
            return None
        now = datetime.now(UTC)
        case.archived_at = now
        await self._session.flush()
        return case

    async def soft_delete_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> Case | None:
        case = await self.get_case_for_org(organization_id, case_id)
        if case is None:
            return None
        case.deleted_at = datetime.now(UTC)
        await self._session.flush()
        return case

    async def restore_case(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
    ) -> Case | None:
        case = await self.get_case_for_org(organization_id, case_id)
        if case is None:
            return None
        case.deleted_at = None
        await self._session.flush()
        return case

    def _count_leads(self, assignments: Sequence[CaseAssignment]) -> int:
        return sum(
            1 for a in assignments if a.role_on_case is CaseAssignmentRole.lead_attorney
        )

    async def apply_assignment_changes(
        self,
        organization_id: uuid.UUID,
        case_id: uuid.UUID,
        *,
        add: Sequence[tuple[uuid.UUID, CaseAssignmentRole]],
        remove: Sequence[tuple[uuid.UUID, CaseAssignmentRole]],
    ) -> Case | None:
        case = await self.get_case_for_org(organization_id, case_id)
        if case is None:
            return None

        add_user_ids = {uid for uid, _ in add}
        users = await self._get_users_in_org(organization_id, add_user_ids)
        for uid, _ in add:
            if uid not in users:
                raise CaseRepositoryError(
                    "Each assigned user must be active in this organization",
                )

        for uid, role in remove:
            stmt = delete(CaseAssignment).where(
                CaseAssignment.case_id == case_id,
                CaseAssignment.user_id == uid,
                CaseAssignment.role_on_case == role,
            )
            await self._session.execute(stmt)

        await self._session.flush()
        await self._session.refresh(case, attribute_names=["assignments"])

        for uid, role in add:
            existing = next(
                (a for a in case.assignments if a.user_id == uid),
                None,
            )
            if existing is not None:
                existing.role_on_case = role
            else:
                self._session.add(
                    CaseAssignment(case_id=case_id, user_id=uid, role_on_case=role),
                )

        await self._session.flush()
        await self._session.refresh(case, attribute_names=["assignments"])
        if self._count_leads(case.assignments) < 1:
            raise CaseRepositoryError(
                "Case requires at least one lead_attorney assignment",
            )
        return case
