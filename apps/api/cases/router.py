"""HTTP routes for case files."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from audit.deps import get_audit_writer
from audit.writer import AuditWriter
from auth.deps import RequestAuth, get_request_auth
from cases.models import Case, CaseAssignment, CaseAssignmentRole, CaseQueryStatus
from cases.repository import CaseRepository, CaseRepositoryError
from cases.schemas import (
    CaseAssignmentOut,
    CaseAssignmentsPatch,
    CaseCreate,
    CaseDetail,
    CaseListItem,
    CaseUpdate,
)
from db.session import get_db_session
from orgs.models import User, UserRole

router = APIRouter(prefix="/cases", tags=["cases"])


def _case_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Case not found",
    )


def _has_attorney_assignment(
    user_id: uuid.UUID,
    assigns: list[CaseAssignment],
) -> bool:
    return any(
        a.user_id == user_id
        and a.role_on_case
        in (CaseAssignmentRole.lead_attorney, CaseAssignmentRole.supporting_attorney)
        for a in assigns
    )


def _is_assigned(user_id: uuid.UUID, assignments: list[CaseAssignment]) -> bool:
    return any(a.user_id == user_id for a in assignments)


def _can_get_case(user: User, case: Case) -> bool:
    if user.role is UserRole.admin:
        return True
    if case.deleted_at is not None:
        return False
    if user.role is UserRole.attorney:
        return True
    return _is_assigned(user.id, list(case.assignments))


def _can_edit_case(user: User, case: Case) -> bool:
    if user.role is UserRole.admin:
        return True
    if case.deleted_at is not None:
        return False
    if user.role is UserRole.student:
        return False
    if user.role is UserRole.attorney:
        return _has_attorney_assignment(user.id, list(case.assignments))
    if user.role is UserRole.paralegal:
        return _is_assigned(user.id, list(case.assignments))
    return False


def _can_archive_case(user: User, assignments: list[CaseAssignment]) -> bool:
    if user.role is UserRole.admin:
        return True
    if user.role is not UserRole.attorney:
        return False
    return _has_attorney_assignment(user.id, assignments)


def _can_modify_assignments(user: User, assignments: list[CaseAssignment]) -> bool:
    if user.role is UserRole.admin:
        return True
    if user.role is not UserRole.attorney:
        return False
    return _has_attorney_assignment(user.id, assignments)


def _ensure_status_allowed(user: User, q: CaseQueryStatus) -> None:
    if user.role is UserRole.admin:
        return
    if q in (CaseQueryStatus.all, CaseQueryStatus.deleted):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This status filter is only available to administrators",
        )


def _list_item(case: Case, access: Literal["full", "read_only"]) -> CaseListItem:
    return CaseListItem(
        id=case.id,
        pseudonym=case.pseudonym,
        country_code=case.country_code,
        basis=case.basis,
        filing_deadline=case.filing_deadline,
        archived_at=case.archived_at,
        deleted_at=case.deleted_at,
        created_at=case.created_at,
        access=access,
        assignments=[CaseAssignmentOut.model_validate(a) for a in case.assignments],
    )


def _detail(case: Case, can_edit: bool) -> CaseDetail:
    return CaseDetail(
        id=case.id,
        pseudonym=case.pseudonym,
        country_code=case.country_code,
        basis=case.basis,
        group_description=case.group_description,
        filing_deadline=case.filing_deadline,
        asylum_office=case.asylum_office,
        intake_notes=case.intake_notes,
        created_by_user_id=case.created_by_user_id,
        created_at=case.created_at,
        archived_at=case.archived_at,
        deleted_at=case.deleted_at,
        assignments=[CaseAssignmentOut.model_validate(a) for a in case.assignments],
        can_edit=can_edit,
    )


@router.post("", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CaseCreate,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> CaseDetail:
    user = auth.user
    org_id = auth.organization.id
    if user.role is UserRole.student:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    has_lead = any(
        a.role_on_case is CaseAssignmentRole.lead_attorney for a in body.assignments
    )
    if not has_lead:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="assignments must include at least one lead_attorney",
        )

    repo = CaseRepository(db)
    try:
        case = await repo.create_case(
            organization_id=org_id,
            created_by_user_id=user.id,
            pseudonym=body.pseudonym,
            country_code=body.country_code,
            basis=body.basis,
            group_description=body.group_description,
            filing_deadline=body.filing_deadline,
            asylum_office=body.asylum_office,
            intake_notes=body.intake_notes,
            assignments=[(a.user_id, a.role_on_case) for a in body.assignments],
        )
    except CaseRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await audit.record(
        "cases.create",
        org_id,
        user.id,
        "case",
        case.id,
        metadata={"pseudonym": case.pseudonym},
    )
    await db.commit()
    reloaded = await repo.get_case_for_org(org_id, case.id)
    assert reloaded is not None
    return _detail(reloaded, can_edit=_can_edit_case(user, reloaded))


@router.get("", response_model=list[CaseListItem])
async def list_cases(
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    list_status: Annotated[
        CaseQueryStatus,
        Query(alias="status"),
    ] = CaseQueryStatus.active,
) -> list[CaseListItem]:
    user = auth.user
    org_id = auth.organization.id
    _ensure_status_allowed(user, list_status)
    repo = CaseRepository(db)
    rows = await repo.list_cases(org_id, user, list_status)
    return [_list_item(c, access) for c, access in rows]


@router.get("/{case_id}", response_model=CaseDetail)
async def get_case(
    case_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CaseDetail:
    user = auth.user
    org_id = auth.organization.id
    repo = CaseRepository(db)
    case = await repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    return _detail(case, can_edit=_can_edit_case(user, case))


@router.patch("/{case_id}", response_model=CaseDetail)
async def patch_case(
    case_id: uuid.UUID,
    body: CaseUpdate,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> CaseDetail:
    user = auth.user
    org_id = auth.organization.id
    repo = CaseRepository(db)
    case = await repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    if not _can_edit_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )

    try:
        updated = await repo.patch_case(org_id, case_id, updates)
    except CaseRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    assert updated is not None

    await audit.record(
        "cases.update",
        org_id,
        user.id,
        "case",
        case_id,
        metadata={"fields": sorted(updates.keys())},
    )
    await db.commit()
    reloaded = await repo.get_case_for_org(org_id, case_id)
    assert reloaded is not None
    return _detail(reloaded, can_edit=_can_edit_case(user, reloaded))


@router.post("/{case_id}/archive", response_model=CaseDetail)
async def archive_case(
    case_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> CaseDetail:
    user = auth.user
    org_id = auth.organization.id
    repo = CaseRepository(db)
    case = await repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    if not _can_archive_case(user, list(case.assignments)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    archived = await repo.archive_case(org_id, case_id)
    if archived is None:
        raise _case_not_found()

    await audit.record(
        "cases.archive",
        org_id,
        user.id,
        "case",
        case_id,
        metadata={},
    )
    await db.commit()
    reloaded = await repo.get_case_for_org(org_id, case_id)
    assert reloaded is not None
    return _detail(reloaded, can_edit=_can_edit_case(user, reloaded))


@router.post("/{case_id}/assignments", response_model=CaseDetail)
async def patch_assignments(
    case_id: uuid.UUID,
    body: CaseAssignmentsPatch,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> CaseDetail:
    user = auth.user
    org_id = auth.organization.id
    if not body.add and not body.remove:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="add or remove must be non-empty",
        )

    repo = CaseRepository(db)
    case = await repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    if not _can_modify_assignments(user, list(case.assignments)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    try:
        updated = await repo.apply_assignment_changes(
            org_id,
            case_id,
            add=[(a.user_id, a.role_on_case) for a in body.add],
            remove=[(r.user_id, r.role_on_case) for r in body.remove],
        )
    except CaseRepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    assert updated is not None

    if body.add:
        await audit.record(
            "cases.assignments.add",
            org_id,
            user.id,
            "case",
            case_id,
            metadata={"count": len(body.add)},
        )
    if body.remove:
        await audit.record(
            "cases.assignments.remove",
            org_id,
            user.id,
            "case",
            case_id,
            metadata={"count": len(body.remove)},
        )
    await db.commit()
    reloaded = await repo.get_case_for_org(org_id, case_id)
    assert reloaded is not None
    return _detail(reloaded, can_edit=_can_edit_case(user, reloaded))


@router.post(
    "/{case_id}/soft-delete",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def soft_delete_case(
    case_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> Response:
    user = auth.user
    org_id = auth.organization.id
    if user.role is not UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    repo = CaseRepository(db)
    deleted = await repo.soft_delete_case(org_id, case_id)
    if deleted is None:
        raise _case_not_found()

    await audit.record(
        "cases.soft_delete",
        org_id,
        user.id,
        "case",
        case_id,
        metadata={},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{case_id}/restore",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def restore_case(
    case_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> Response:
    user = auth.user
    org_id = auth.organization.id
    if user.role is not UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    repo = CaseRepository(db)
    restored = await repo.restore_case(org_id, case_id)
    if restored is None:
        raise _case_not_found()

    await audit.record(
        "cases.restore",
        org_id,
        user.id,
        "case",
        case_id,
        metadata={},
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)