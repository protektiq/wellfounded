"""HTTP routes for case files."""

from __future__ import annotations

import uuid
from io import BytesIO
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
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
from country_conditions.docx_memo import (
    build_country_conditions_docx_bytes,
    cited_passage_ids_ordered,
    export_docx_filename,
)
from country_conditions.models import CountryConditionsMemoStatus
from country_conditions.repository import CountryConditionsRepository
from country_conditions.schemas import (
    CitedPassagePayload,
    CountryConditionsGenerateRequest,
    CountryConditionsGenerateResponse,
    CountryConditionsInputs,
    CountryConditionsMemoDetail,
    CountryConditionsMemoSummary,
    FinalMemoStructured,
)
from country_conditions.service import (
    CountryConditionsService,
    get_country_conditions_service,
)
from db.session import get_db_session
from declarations.flags import flags_from_dicts as decl_flags_from_dicts
from declarations.flags import unresolved_required_flag_ids
from declarations.models import DeclarationDraftStatus
from declarations.models import PriorStatementType as PriorStatementTypeOrm
from declarations.models import SourceLanguage as SourceLanguageOrm
from declarations.repository import DeclarationsRepository
from declarations.schemas import (
    CleanExportBlockedResponse,
    DeclarationDraftDetail,
    DeclarationDraftSummary,
    DeclarationGenerateRequest,
    DeclarationGenerateResponse,
    DeclarationReviseRequest,
    DeclarationReviseResponse,
    FlagResolveRequest,
    PriorStatementCreate,
    PriorStatementOut,
    TranscriptCreate,
    TranscriptOut,
)
from declarations.service import DeclarationsService, get_declarations_service
from encryption.service import DataKeyRevokedError
from orgs.models import User, UserRole
from retrieval.passage_search import (
    fetch_passages_by_ordered_ids,
    fetch_passages_export_meta,
)
from transcription.repository import TranscriptionRepository
from transcription.schemas import (
    InterviewAudioOut,
    InterviewUploadResponse,
    TranscriptDetailOut,
)
from transcription.service import TranscriptionService, get_transcription_service

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


@router.post(
    "/{case_id}/country-conditions",
    response_model=CountryConditionsGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_country_conditions_memo(
    case_id: uuid.UUID,
    body: CountryConditionsGenerateRequest,
    request: Request,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
    svc: Annotated[CountryConditionsService, Depends(get_country_conditions_service)],
) -> CountryConditionsGenerateResponse:
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
    rid = getattr(request.state, "request_id", None)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request context was not initialized (missing request_id).",
        )
    memo_id, version = await svc.generate(
        organization_id=org_id,
        case_id=case_id,
        inputs=body.to_inputs(),
        requested_by_user_id=user.id,
        correlation_request_id=rid,
        session=db,
        audit=audit,
    )
    await db.commit()
    return CountryConditionsGenerateResponse(
        memo_id=memo_id,
        version=version,
        status=CountryConditionsMemoStatus.pending,
    )


@router.get(
    "/{case_id}/country-conditions",
    response_model=list[CountryConditionsMemoSummary],
)
async def list_country_conditions_memos(
    case_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[CountryConditionsMemoSummary]:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    cc_repo = CountryConditionsRepository(db)
    rows = await cc_repo.list_memos_for_case(org_id, case_id)
    return [
        CountryConditionsMemoSummary(
            id=m.id,
            case_id=m.case_id,
            version=m.version,
            status=m.status,
            generated_at=m.generated_at,
        )
        for m in rows
    ]


@router.get(
    "/{case_id}/country-conditions/{memo_id}",
    response_model=CountryConditionsMemoDetail,
)
async def get_country_conditions_memo(
    case_id: uuid.UUID,
    memo_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> CountryConditionsMemoDetail:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    cc_repo = CountryConditionsRepository(db)
    memo = await cc_repo.get_memo(org_id, memo_id)
    if memo is None or memo.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found",
        )
    cited_passages: list[CitedPassagePayload] = []
    if (
        memo.status is CountryConditionsMemoStatus.complete
        and memo.output is not None
    ):
        try:
            final = FinalMemoStructured.model_validate(memo.output)
        except ValidationError:
            final = None
        if final is not None:
            ordered_ids = cited_passage_ids_ordered(final)
            loaded = await fetch_passages_by_ordered_ids(db, ordered_ids)
            if loaded is not None:
                cited_passages = [
                    CitedPassagePayload(
                        passage_id=p.passage_id,
                        source_family=p.source_family,
                        document_title=p.document_title,
                        publication_date=p.publication_date,
                        url=p.url,
                        section_anchor=p.section_anchor,
                        text=p.text,
                    )
                    for p in loaded
                ]
    return CountryConditionsMemoDetail(
        id=memo.id,
        case_id=memo.case_id,
        version=memo.version,
        status=memo.status,
        inputs=CountryConditionsInputs.model_validate(memo.inputs),
        output=memo.output,
        model_versions=dict(memo.model_versions),
        error_message=memo.error_message,
        generated_at=memo.generated_at,
        cited_passages=cited_passages,
    )


@router.get("/{case_id}/country-conditions/{memo_id}/export.docx")
async def export_country_conditions_memo_docx(
    case_id: uuid.UUID,
    memo_id: uuid.UUID,
    request: Request,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> StreamingResponse:
    user = auth.user
    org_id = auth.organization.id
    rid = getattr(request.state, "request_id", None)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request context was not initialized (missing request_id).",
        )
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    cc_repo = CountryConditionsRepository(db)
    memo = await cc_repo.get_memo(org_id, memo_id)
    if memo is None or memo.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memo not found",
        )
    if memo.status is not CountryConditionsMemoStatus.complete or memo.output is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Memo is not ready for export",
        )
    try:
        final = FinalMemoStructured.model_validate(memo.output)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Memo output is invalid for export",
        ) from None
    passage_ids = cited_passage_ids_ordered(final)
    try:
        export_meta = await fetch_passages_export_meta(db, passage_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load source metadata for citations",
        ) from exc
    inputs = CountryConditionsInputs.model_validate(memo.inputs)
    docx_bytes = build_country_conditions_docx_bytes(
        final=final,
        inputs=inputs,
        case_pseudonym=case.pseudonym,
        export_meta=export_meta,
        memo_generated_at=memo.generated_at,
    )
    filename = export_docx_filename(case.pseudonym, memo.version)
    await audit.record(
        "country_conditions.memo.export.docx",
        org_id,
        user.id,
        "country_conditions_memo",
        memo_id,
        metadata={"case_id": str(case_id), "memo_version": memo.version},
    )
    await db.commit()
    return StreamingResponse(
        BytesIO(docx_bytes),
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/{case_id}/interviews",
    response_model=InterviewUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_interview_audio(
    case_id: uuid.UUID,
    request: Request,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
    svc: Annotated[TranscriptionService, Depends(get_transcription_service)],
    file: UploadFile = File(...),
    source_language: SourceLanguageOrm = Form(...),
) -> InterviewUploadResponse:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    if not _can_edit_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    rid = getattr(request.state, "request_id", None)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request context was not initialized (missing request_id).",
        )
    try:
        audio_id, transcript_id = await svc.upload_interview(
            organization_id=org_id,
            case_id=case_id,
            source_language=source_language,
            upload=file,
            uploaded_by_user_id=user.id,
            correlation_request_id=rid,
            session=db,
            audit=audit,
        )
    except DataKeyRevokedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    from declarations.models import TranscriptionStatus

    return InterviewUploadResponse(
        interview_audio_id=audio_id,
        transcript_id=transcript_id,
        status=TranscriptionStatus.pending,
    )


@router.get(
    "/{case_id}/interviews/{audio_id}",
    response_model=InterviewAudioOut,
)
async def get_interview_audio(
    case_id: uuid.UUID,
    audio_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> InterviewAudioOut:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    repo = TranscriptionRepository(db)
    audio = await repo.get_interview_audio_for_case(org_id, case_id, audio_id)
    if audio is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview audio not found",
        )
    transcript = await repo.get_transcript_for_audio(org_id, audio_id)
    out = InterviewAudioOut.model_validate(audio)
    return out.model_copy(
        update={"transcript_id": transcript.id if transcript is not None else None},
    )


@router.get(
    "/{case_id}/transcripts/{transcript_id}",
    response_model=TranscriptDetailOut,
)
async def get_transcript_detail(
    case_id: uuid.UUID,
    transcript_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> TranscriptDetailOut:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    repo = TranscriptionRepository(db)
    row = await repo.get_transcript(org_id, transcript_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transcript not found",
        )
    return TranscriptDetailOut.model_validate(row)


@router.post(
    "/{case_id}/transcripts",
    response_model=TranscriptOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_transcript(
    case_id: uuid.UUID,
    body: TranscriptCreate,
    request: Request,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> TranscriptOut:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    if not _can_edit_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    rid = getattr(request.state, "request_id", None)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request context was not initialized (missing request_id).",
        )
    from datetime import UTC, datetime

    completed = body.completed_at or datetime.now(UTC)
    decl_repo = DeclarationsRepository(db)
    row = await decl_repo.create_transcript_with_artifact(
        org_id,
        case_id,
        interview_audio_id=body.interview_audio_id,
        source_language=SourceLanguageOrm(body.source_language.value),
        segments=[s.model_dump(mode="json") for s in body.segments],
        full_source_text=body.full_source_text,
        full_english_text=body.full_english_text,
        model_version=body.model_version,
        completed_at=completed,
        created_by_user_id=user.id,
    )
    await audit.record(
        "transcript.seed.create",
        org_id,
        user.id,
        "transcript",
        row.id,
        metadata={"case_id": str(case_id)},
    )
    await db.commit()
    return TranscriptOut.model_validate(row)


@router.get(
    "/{case_id}/prior-statements",
    response_model=list[PriorStatementOut],
)
async def list_prior_statements(
    case_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[PriorStatementOut]:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    decl_repo = DeclarationsRepository(db)
    rows = await decl_repo.list_all_prior_statements(org_id, case_id)
    return [PriorStatementOut.model_validate(r) for r in rows]


@router.post(
    "/{case_id}/prior-statements",
    response_model=PriorStatementOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_prior_statement(
    case_id: uuid.UUID,
    body: PriorStatementCreate,
    request: Request,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
) -> PriorStatementOut:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    if not _can_edit_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    rid = getattr(request.state, "request_id", None)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request context was not initialized (missing request_id).",
        )
    decl_repo = DeclarationsRepository(db)
    row = await decl_repo.create_prior_statement_with_artifact(
        org_id,
        case_id,
        statement_type=PriorStatementTypeOrm(body.statement_type.value),
        source_text=body.source_text,
        english_text=body.english_text,
        source_language=SourceLanguageOrm(body.source_language.value),
        uploaded_by_user_id=user.id,
    )
    await audit.record(
        "prior_statement.create",
        org_id,
        user.id,
        "prior_statement",
        row.id,
        metadata={"case_id": str(case_id)},
    )
    await db.commit()
    return PriorStatementOut.model_validate(row)


@router.post(
    "/{case_id}/declarations",
    response_model=DeclarationGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_declaration_draft(
    case_id: uuid.UUID,
    body: DeclarationGenerateRequest,
    request: Request,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
    svc: Annotated[DeclarationsService, Depends(get_declarations_service)],
) -> DeclarationGenerateResponse:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    if not _can_edit_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    rid = getattr(request.state, "request_id", None)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request context was not initialized (missing request_id).",
        )
    try:
        draft_id, version = await svc.generate(
            organization_id=org_id,
            case_id=case_id,
            transcript_id=body.transcript_id,
            prior_statement_ids=body.prior_statement_ids,
            requested_by_user_id=user.id,
            correlation_request_id=rid,
            session=db,
            audit=audit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return DeclarationGenerateResponse(
        draft_id=draft_id,
        version=version,
        status=DeclarationDraftStatus.pending,
    )


@router.get(
    "/{case_id}/declarations",
    response_model=list[DeclarationDraftSummary],
)
async def list_declaration_drafts(
    case_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[DeclarationDraftSummary]:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    decl_repo = DeclarationsRepository(db)
    rows = await decl_repo.list_drafts_for_case(org_id, case_id)
    return [
        DeclarationDraftSummary(
            id=r.id,
            case_id=r.case_id,
            version=r.version,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get(
    "/{case_id}/declarations/{draft_id}",
    response_model=DeclarationDraftDetail,
)
async def get_declaration_draft(
    case_id: uuid.UUID,
    draft_id: uuid.UUID,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    svc: Annotated[DeclarationsService, Depends(get_declarations_service)],
) -> DeclarationDraftDetail:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    decl_repo = DeclarationsRepository(db)
    row = await decl_repo.get_draft(org_id, draft_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Declaration draft not found",
        )
    return svc.draft_to_detail(row)


@router.patch(
    "/{case_id}/declarations/{draft_id}/flags/{flag_id}",
    response_model=DeclarationDraftDetail,
)
async def resolve_declaration_flag(
    case_id: uuid.UUID,
    draft_id: uuid.UUID,
    flag_id: uuid.UUID,
    body: FlagResolveRequest,
    request: Request,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
    svc: Annotated[DeclarationsService, Depends(get_declarations_service)],
) -> DeclarationDraftDetail:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    if not _can_edit_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    rid = getattr(request.state, "request_id", None)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request context was not initialized (missing request_id).",
        )
    from declarations.schemas import DeclarationFlagStatus

    try:
        await svc.resolve_flag(
            organization_id=org_id,
            draft_id=draft_id,
            flag_id=flag_id,
            status=DeclarationFlagStatus(body.status),
            resolution_note=body.resolution_note,
            user_id=user.id,
            session=db,
            audit=audit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    await db.commit()
    decl_repo = DeclarationsRepository(db)
    row = await decl_repo.get_draft(org_id, draft_id)
    assert row is not None
    return svc.draft_to_detail(row)


@router.post(
    "/{case_id}/declarations/{draft_id}/revise",
    response_model=DeclarationReviseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def revise_declaration_draft(
    case_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DeclarationReviseRequest,
    request: Request,
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    audit: Annotated[AuditWriter, Depends(get_audit_writer)],
    svc: Annotated[DeclarationsService, Depends(get_declarations_service)],
) -> DeclarationReviseResponse:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    if not _can_edit_case(user, case):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    rid = getattr(request.state, "request_id", None)
    if not isinstance(rid, uuid.UUID):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request context was not initialized (missing request_id).",
        )
    try:
        new_id, version, st = await svc.revise(
            organization_id=org_id,
            case_id=case_id,
            parent_draft_id=draft_id,
            instruction=body.instruction,
            scope=body.scope,
            requested_by_user_id=user.id,
            correlation_request_id=rid,
            session=db,
            audit=audit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    await db.commit()
    return DeclarationReviseResponse(
        draft_id=new_id,
        version=version,
        status=st,
    )


@router.get(
    "/{case_id}/declarations/{draft_id}/export.docx",
    responses={
        409: {"model": CleanExportBlockedResponse},
        501: {"description": "DOCX rendering ships in Task 3.3"},
    },
)
async def export_declaration_docx(
    case_id: uuid.UUID,
    draft_id: uuid.UUID,
    mode: Annotated[Literal["working", "clean"], Query()],
    auth: Annotated[RequestAuth, Depends(get_request_auth)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    user = auth.user
    org_id = auth.organization.id
    case_repo = CaseRepository(db)
    case = await case_repo.get_case_for_org(org_id, case_id)
    if case is None or not _can_get_case(user, case):
        raise _case_not_found()
    decl_repo = DeclarationsRepository(db)
    row = await decl_repo.get_draft(org_id, draft_id)
    if row is None or row.case_id != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Declaration draft not found",
        )
    if row.draft is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Declaration draft is not ready for export",
        )
    if mode == "clean":
        flags = decl_flags_from_dicts(list(row.flags))
        blocked = unresolved_required_flag_ids(flags)
        if blocked:
            payload = CleanExportBlockedResponse(unresolved_flag_ids=blocked)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=payload.model_dump(mode="json"),
            )
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Clean DOCX export is not yet implemented (Task 3.3)",
        )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Working DOCX export is not yet implemented (Task 3.3)",
    )
