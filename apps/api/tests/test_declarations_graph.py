"""Declaration drafting API and LangGraph (mocked LLM, real Postgres)."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditLogEntry
from cases.models import ClaimBasis
from declarations.models import DeclarationDraftStatus
from declarations.prompts import (
    DECL_DRAFT_PROMPT,
    DECL_EXTRACT_PROMPT,
    DECL_INCONSISTENCY_PROMPT,
    DECL_REVISE_PROMPT,
)
from declarations.schemas import (
    DECLARATION_SECTION_IDS,
    ClaimIntermediateRepresentation,
    DeclarationDraftContent,
    DeclarationFlagType,
    DeclarationParagraph,
    DeclarationSection,
    DraftFlagOut,
    DraftOutput,
    ExtractOutput,
    FlagSpan,
    InconsistencyCheckOutput,
    InconsistencyItem,
    ReviseOutput,
)
from llm.client import LLMClient
from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "declaration_eritrea_journalist.json"


def _load_fixture() -> dict[str, Any]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


def _empty_sections() -> dict[str, DeclarationSection]:
    sections: dict[str, DeclarationSection] = {}
    for sid in DECLARATION_SECTION_IDS:
        sections[sid] = DeclarationSection(
            section_id=sid,
            paragraphs=[
                DeclarationParagraph(
                    id=f"{sid}:p0",
                    text=f"Placeholder for {sid}.",
                    source_segment_ids=["seg-0"],
                ),
            ],
        )
    return sections


def _draft_with_inference(fixture: dict[str, Any]) -> DeclarationDraftContent:
    inf = fixture["draft_inference"]
    sections = _empty_sections()
    sections["past_persecution"] = DeclarationSection(
        section_id="past_persecution",
        paragraphs=[
            DeclarationParagraph(
                id=inf["paragraph_id"],
                text=inf["text"],
                source_segment_ids=["seg-1"],
                inference_spans=[],
            ),
        ],
    )
    return DeclarationDraftContent(sections=sections)


async def _magic_login(
    *,
    api_client: AsyncClient,
    db_session: AsyncSession,
    slug: str,
    email: str,
    role: UserRole,
    capsys: pytest.CaptureFixture[str],
) -> None:
    org_repo = OrgRepository(db_session)
    org = await org_repo.get_org_by_slug(slug)
    if org is None:
        org = await org_repo.create_org(name="Decl Org", slug=slug)
    existing = await org_repo.get_user_by_email(email, org.id)
    if existing is None:
        await org_repo.create_user(
            organization_id=org.id,
            email=email,
            display_name="Decl User",
            role=role,
            status=UserStatus.active,
        )
    await db_session.commit()
    await api_client.post(
        "/auth/magic-link",
        json={"email": email, "organization_slug": slug},
    )
    out = capsys.readouterr().out
    m = re.search(r"token=([^\s]+)", out)
    assert m is not None, out
    raw_token = m.group(1)
    r = await api_client.get(
        f"/auth/callback?token={raw_token}",
        follow_redirects=False,
    )
    assert r.status_code == 302


@pytest.fixture
def eritrea_fixture() -> dict[str, Any]:
    return _load_fixture()


@pytest.fixture
def mock_llm_eritrea(
    monkeypatch: pytest.MonkeyPatch,
    eritrea_fixture: dict[str, Any],
) -> Any:
    fixture = eritrea_fixture
    prior_id_holder: dict[str, uuid.UUID] = {}

    async def _fake_complete_structured(
        self: LLMClient,
        prompt: Any,
        schema: type[Any],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Any:
        _ = (max_tokens, temperature)
        if prompt.id == DECL_EXTRACT_PROMPT.id:
            ir = ClaimIntermediateRepresentation.model_validate(fixture["claim_ir"])
            return ExtractOutput(claim_ir=ir)
        if prompt.id == DECL_INCONSISTENCY_PROMPT.id:
            inc = fixture["inconsistency"]
            pid = prior_id_holder.get("id")
            assert pid is not None
            return InconsistencyCheckOutput(
                inconsistencies=[
                    InconsistencyItem(
                        description=inc["description"],
                        suggested_resolution=(
                            "Confirm with client whether three or four men were present."
                        ),
                        prior_statement_id=pid,
                        transcript_quote=inc["transcript_quote"],
                        prior_quote=inc["prior_quote"],
                    ),
                ],
            )
        if prompt.id == DECL_DRAFT_PROMPT.id:
            inf = fixture["draft_inference"]
            draft = _draft_with_inference(fixture)
            return DraftOutput(
                draft=draft,
                flags=[
                    DraftFlagOut(
                        type=DeclarationFlagType.INFERENCE,
                        paragraph_id=inf["paragraph_id"],
                        span=FlagSpan(
                            start=inf["inference_start"],
                            end=inf["inference_end"],
                        ),
                        description="Model inferred the year 2022; client did not state it.",
                        suggested_resolution=(
                            "Remove the 2022 reference or confirm the date with the client."
                        ),
                    ),
                ],
            )
        if prompt.id == DECL_REVISE_PROMPT.id:
            draft = _draft_with_inference(fixture)
            return ReviseOutput(draft=draft, new_flags=[])
        raise AssertionError(f"unexpected prompt {prompt.id}")

    monkeypatch.setattr(LLMClient, "complete_structured", _fake_complete_structured)

    def _set_prior_id(pid: uuid.UUID) -> None:
        prior_id_holder["id"] = pid

    return _set_prior_id


async def _seed_case_and_transcripts(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    eritrea_fixture: dict[str, Any],
    mock_llm_eritrea: Any,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    slug = f"decl-{uuid.uuid4().hex[:10]}"
    await _magic_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="decl-att@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    org_repo = OrgRepository(db_session)
    org = await org_repo.get_org_by_slug(slug)
    assert org is not None
    user = await org_repo.get_user_by_email("decl-att@example.com", org.id)
    assert user is not None

    r_create = await api_client.post(
        "/cases",
        json={
            "pseudonym": "M.A. — Eritrea",
            "country_code": "ER",
            "basis": ClaimBasis.political_opinion.value,
            "group_description": "Eritrean journalists",
            "filing_deadline": None,
            "asylum_office": None,
            "intake_notes": "Notes",
            "assignments": [
                {"user_id": str(user.id), "role_on_case": "lead_attorney"},
            ],
        },
    )
    assert r_create.status_code == 201
    case_id = uuid.UUID(r_create.json()["id"])

    t_body = eritrea_fixture["transcript"]
    r_t = await api_client.post(
        f"/cases/{case_id}/transcripts",
        json={
            **t_body,
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )
    assert r_t.status_code == 201, r_t.text
    transcript_id = uuid.UUID(r_t.json()["id"])

    p_body = eritrea_fixture["prior_statement"]
    r_p = await api_client.post(
        f"/cases/{case_id}/prior-statements",
        json=p_body,
    )
    assert r_p.status_code == 201, r_p.text
    prior_id = uuid.UUID(r_p.json()["id"])
    mock_llm_eritrea(prior_id)

    return case_id, transcript_id, prior_id


async def _wait_for_draft(
    api_client: AsyncClient,
    case_id: uuid.UUID,
    draft_id: uuid.UUID,
) -> dict[str, Any]:
    for _ in range(120):
        await asyncio.sleep(0.05)
        r = await api_client.get(f"/cases/{case_id}/declarations/{draft_id}")
        if r.status_code != 200:
            continue
        body = r.json()
        st = body["status"]
        if st in (
            DeclarationDraftStatus.draft_ready.value,
            DeclarationDraftStatus.flags_unresolved.value,
        ):
            return body
        if st == DeclarationDraftStatus.failed.value:
            pytest.fail(body.get("error_message", "failed"))
    pytest.fail("draft did not complete in time")


@pytest.mark.asyncio(loop_scope="session")
async def test_seed_transcript_and_prior_statement(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    eritrea_fixture: dict[str, Any],
    mock_llm_eritrea: Any,
) -> None:
    case_id, transcript_id, prior_id = await _seed_case_and_transcripts(
        api_client,
        db_session,
        capsys,
        eritrea_fixture,
        mock_llm_eritrea,
    )
    assert transcript_id
    assert prior_id
    r = await api_client.get(f"/cases/{case_id}")
    assert r.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_gap_first_incident_date(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    eritrea_fixture: dict[str, Any],
    mock_llm_eritrea: Any,
) -> None:
    case_id, transcript_id, prior_id = await _seed_case_and_transcripts(
        api_client,
        db_session,
        capsys,
        eritrea_fixture,
        mock_llm_eritrea,
    )
    r_post = await api_client.post(
        f"/cases/{case_id}/declarations",
        json={
            "transcript_id": str(transcript_id),
            "prior_statement_ids": [str(prior_id)],
        },
    )
    assert r_post.status_code == 202, r_post.text
    draft_id = uuid.UUID(r_post.json()["draft_id"])
    body = await _wait_for_draft(api_client, case_id, draft_id)
    gap_flags = [
        f
        for f in body["flags"]
        if f["type"] == DeclarationFlagType.GAP.value
        and f.get("element_key") == "first_incident_date"
    ]
    assert len(gap_flags) == 1
    assert gap_flags[0]["suggested_resolution"].strip()


@pytest.mark.asyncio(loop_scope="session")
async def test_inconsistency_agent_count(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    eritrea_fixture: dict[str, Any],
    mock_llm_eritrea: Any,
) -> None:
    case_id, transcript_id, prior_id = await _seed_case_and_transcripts(
        api_client,
        db_session,
        capsys,
        eritrea_fixture,
        mock_llm_eritrea,
    )
    r_post = await api_client.post(
        f"/cases/{case_id}/declarations",
        json={
            "transcript_id": str(transcript_id),
            "prior_statement_ids": [str(prior_id)],
        },
    )
    draft_id = uuid.UUID(r_post.json()["draft_id"])
    body = await _wait_for_draft(api_client, case_id, draft_id)
    inc_flags = [
        f for f in body["flags"] if f["type"] == DeclarationFlagType.INCONSISTENCY.value
    ]
    assert len(inc_flags) >= 1
    f0 = inc_flags[0]
    assert "four" in f0["transcript_quote"].lower() or "Four" in f0["transcript_quote"]
    assert "three" in f0["prior_quote"].lower() or "Three" in f0["prior_quote"]
    assert f0["suggested_resolution"].strip()


@pytest.mark.asyncio(loop_scope="session")
async def test_inference_flagged(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    eritrea_fixture: dict[str, Any],
    mock_llm_eritrea: Any,
) -> None:
    case_id, transcript_id, prior_id = await _seed_case_and_transcripts(
        api_client,
        db_session,
        capsys,
        eritrea_fixture,
        mock_llm_eritrea,
    )
    r_post = await api_client.post(
        f"/cases/{case_id}/declarations",
        json={
            "transcript_id": str(transcript_id),
            "prior_statement_ids": [str(prior_id)],
        },
    )
    draft_id = uuid.UUID(r_post.json()["draft_id"])
    body = await _wait_for_draft(api_client, case_id, draft_id)
    inf_flags = [
        f for f in body["flags"] if f["type"] == DeclarationFlagType.INFERENCE.value
    ]
    assert len(inf_flags) >= 1
    assert inf_flags[0]["paragraph_id"] == eritrea_fixture["draft_inference"]["paragraph_id"]


@pytest.mark.asyncio(loop_scope="session")
async def test_revise_preserves_open_flags(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    eritrea_fixture: dict[str, Any],
    mock_llm_eritrea: Any,
) -> None:
    case_id, transcript_id, prior_id = await _seed_case_and_transcripts(
        api_client,
        db_session,
        capsys,
        eritrea_fixture,
        mock_llm_eritrea,
    )
    r_post = await api_client.post(
        f"/cases/{case_id}/declarations",
        json={
            "transcript_id": str(transcript_id),
            "prior_statement_ids": [str(prior_id)],
        },
    )
    draft_id = uuid.UUID(r_post.json()["draft_id"])
    body = await _wait_for_draft(api_client, case_id, draft_id)
    open_before = {
        f["id"]
        for f in body["flags"]
        if f["status"] == "open"
        and f["type"] in ("GAP", "INCONSISTENCY", "INFERENCE")
    }
    assert open_before

    r_rev = await api_client.post(
        f"/cases/{case_id}/declarations/{draft_id}/revise",
        json={
            "instruction": "Strengthen the well-founded fear section only.",
            "scope": {"section_id": "well_founded_fear_future"},
        },
    )
    assert r_rev.status_code == 201, r_rev.text
    new_id = uuid.UUID(r_rev.json()["draft_id"])
    new_body = await _wait_for_draft(api_client, case_id, new_id)
    open_types = {
        (f["type"], f.get("element_key"), f.get("prior_statement_id"))
        for f in new_body["flags"]
        if f["status"] == "open"
    }
    assert any(t[0] == "GAP" for t in open_types)
    assert any(t[0] == "INCONSISTENCY" for t in open_types)


@pytest.mark.asyncio(loop_scope="session")
async def test_clean_export_409(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    eritrea_fixture: dict[str, Any],
    mock_llm_eritrea: Any,
) -> None:
    case_id, transcript_id, prior_id = await _seed_case_and_transcripts(
        api_client,
        db_session,
        capsys,
        eritrea_fixture,
        mock_llm_eritrea,
    )
    r_post = await api_client.post(
        f"/cases/{case_id}/declarations",
        json={
            "transcript_id": str(transcript_id),
            "prior_statement_ids": [str(prior_id)],
        },
    )
    draft_id = uuid.UUID(r_post.json()["draft_id"])
    await _wait_for_draft(api_client, case_id, draft_id)
    r_exp = await api_client.get(
        f"/cases/{case_id}/declarations/{draft_id}/export.docx",
        params={"mode": "clean"},
    )
    assert r_exp.status_code == 409
    detail = r_exp.json()["detail"]
    if isinstance(detail, dict):
        assert detail["unresolved_flag_ids"]
    else:
        assert "unresolved" in str(detail).lower() or "flag" in str(detail).lower()


@pytest.mark.asyncio(loop_scope="session")
async def test_clean_export_allowed_when_resolved(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    eritrea_fixture: dict[str, Any],
    mock_llm_eritrea: Any,
) -> None:
    case_id, transcript_id, prior_id = await _seed_case_and_transcripts(
        api_client,
        db_session,
        capsys,
        eritrea_fixture,
        mock_llm_eritrea,
    )
    r_post = await api_client.post(
        f"/cases/{case_id}/declarations",
        json={
            "transcript_id": str(transcript_id),
            "prior_statement_ids": [str(prior_id)],
        },
    )
    draft_id = uuid.UUID(r_post.json()["draft_id"])
    body = await _wait_for_draft(api_client, case_id, draft_id)
    for f in body["flags"]:
        if f["type"] in ("GAP", "INCONSISTENCY", "INFERENCE") and f["status"] == "open":
            r_patch = await api_client.patch(
                f"/cases/{case_id}/declarations/{draft_id}/flags/{f['id']}",
                json={"status": "resolved", "resolution_note": "Resolved in test"},
            )
            assert r_patch.status_code == 200, r_patch.text
    r_exp = await api_client.get(
        f"/cases/{case_id}/declarations/{draft_id}/export.docx",
        params={"mode": "clean"},
    )
    assert r_exp.status_code == 501


@pytest.mark.asyncio(loop_scope="session")
async def test_audit_on_generate_and_revise(
    api_client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    eritrea_fixture: dict[str, Any],
    mock_llm_eritrea: Any,
) -> None:
    case_id, transcript_id, prior_id = await _seed_case_and_transcripts(
        api_client,
        db_session,
        capsys,
        eritrea_fixture,
        mock_llm_eritrea,
    )
    r_post = await api_client.post(
        f"/cases/{case_id}/declarations",
        json={
            "transcript_id": str(transcript_id),
            "prior_statement_ids": [str(prior_id)],
        },
    )
    draft_id = uuid.UUID(r_post.json()["draft_id"])
    await _wait_for_draft(api_client, case_id, draft_id)

    stmt = select(AuditLogEntry.action).where(
        AuditLogEntry.resource_type == "declaration_draft",
        AuditLogEntry.resource_id == draft_id,
    )
    result = await db_session.execute(stmt)
    actions = {row[0] for row in result.all()}
    assert "declaration.generate.start" in actions
    assert "declaration.generate.complete" in actions or "declaration.extract.complete" in actions

    r_rev = await api_client.post(
        f"/cases/{case_id}/declarations/{draft_id}/revise",
        json={
            "instruction": "Clarify identity section.",
            "scope": {"section_id": "identity_background"},
        },
    )
    assert r_rev.status_code == 201
    new_id = uuid.UUID(r_rev.json()["draft_id"])
    stmt2 = select(AuditLogEntry.action).where(
        AuditLogEntry.resource_id == new_id,
    )
    result2 = await db_session.execute(stmt2)
    actions2 = {row[0] for row in result2.all()}
    assert "declaration.revise" in actions2
