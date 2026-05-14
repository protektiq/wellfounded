"""Country conditions memo API and LangGraph (mocked LLM, real Postgres)."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from audit.models import AuditLogEntry
from cases.models import (
    Case,
    CaseArtifact,
    CaseArtifactType,
    CaseAssignment,
    CaseAssignmentRole,
    ClaimBasis,
)
from config import get_settings
from country_conditions.graph import build_country_conditions_graph
from country_conditions.models import CountryConditionsMemo, CountryConditionsMemoStatus
from country_conditions.prompts import (
    CC_DRAFT_PROMPT,
    CC_PLAN_PROMPT,
    CC_SYNTHESIZE_PROMPT,
    CC_VERIFY_PROMPT,
)
from country_conditions.schemas import (
    CC_SECTION_IDS,
    ClaimVerificationEntry,
    CountryConditionsInputs,
    MemoSectionStructured,
    PlanOutput,
    SectionDraftOutput,
    SynthesizeSectionsOut,
    VerifySectionOutput,
)
from llm.client import LLMClient
from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository


def _plan_fixture() -> PlanOutput:
    queries = {sid: f"query for {sid}" for sid in CC_SECTION_IDS}
    titles = {
        "general_conditions": "General conditions",
        "treatment_of_group": "Treatment of the group",
        "state_actor_involvement": "State actors",
        "internal_relocation": "Internal relocation",
        "recent_trends": "Recent trends",
    }
    return PlanOutput(
        outline="Outline for memo.",
        section_queries=queries,
        section_titles=titles,
    )


def _fake_search_rows() -> dict[str, list[dict[str, Any]]]:
    by_section: dict[str, list[dict[str, Any]]] = {}
    for sid in CC_SECTION_IDS:
        pid = uuid.uuid4()
        by_section[sid] = [
            {
                "passage_id": str(pid),
                "document_id": str(uuid.uuid4()),
                "source_family": "state_dept",
                "document_title": f"Title {sid}",
                "publication_date": date(2024, 1, 1).isoformat(),
                "url": "https://example.invalid/doc",
                "section_anchor": "s1",
                "text": "Official report text supporting claims.",
                "similarity_score": 0.9,
            },
        ]
    return by_section


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
        org = await org_repo.create_org(name="CC Org", slug=slug)
    existing = await org_repo.get_user_by_email(email, org.id)
    if existing is None:
        await org_repo.create_user(
            organization_id=org.id,
            email=email,
            display_name="CC User",
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


@pytest.mark.asyncio(loop_scope="session")
async def test_country_conditions_happy_path_mocked_llm(
    db_session: AsyncSession,
    api_client: AsyncClient,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slug = f"cc-{uuid.uuid4().hex[:10]}"
    await _magic_login(
        api_client=api_client,
        db_session=db_session,
        slug=slug,
        email="cc-att@example.com",
        role=UserRole.attorney,
        capsys=capsys,
    )
    org_repo = OrgRepository(db_session)
    org = await org_repo.get_org_by_slug(slug)
    assert org is not None
    user = await org_repo.get_user_by_email("cc-att@example.com", org.id)
    assert user is not None

    r_create = await api_client.post(
        "/cases",
        json={
            "pseudonym": "M.A. — Test",
            "country_code": "er",
            "basis": ClaimBasis.political_opinion.value,
            "group_description": "Journalists",
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

    fake_rows = _fake_search_rows()

    async def _fake_search(
        session: AsyncSession,
        query: str,
        *,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        country_codes: list[str],
        date_after: date | None = None,
        source_families: list[str] | None = None,
        top_k: int = 20,
        cache: Any = None,
        settings: Any = None,
    ) -> Any:
        for sid in CC_SECTION_IDS:
            if query == f"query for {sid}":
                from retrieval.schemas import RetrievedPassage

                rows = fake_rows[sid]
                p = rows[0]
                return [
                    RetrievedPassage(
                        passage_id=uuid.UUID(p["passage_id"]),
                        document_id=uuid.UUID(p["document_id"]),
                        source_family=p["source_family"],
                        document_title=p["document_title"],
                        publication_date=date.fromisoformat(p["publication_date"]),
                        url=p["url"],
                        section_anchor=p["section_anchor"],
                        text=p["text"],
                        similarity_score=float(p["similarity_score"]),
                    ),
                ]
        return []

    monkeypatch.setattr(
        "country_conditions.graph.search",
        _fake_search,
    )

    async def _fake_complete_structured(
        self: LLMClient,
        prompt: Any,
        schema: type[Any],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Any:
        _ = (max_tokens, temperature)
        if prompt.id == CC_PLAN_PROMPT.id:
            return _plan_fixture()
        if prompt.id == CC_DRAFT_PROMPT.id:
            vars_d = dict(prompt.variables)
            sid = vars_d["section_id"]
            pdata = json.loads(vars_d["passages_json"])
            pid = uuid.UUID(pdata[0]["passage_id"])
            prose = (
                f"Conditions are reported in official sources. "
                f'<cite passage_id="{pid}"/>'
            )
            return SectionDraftOutput(section_id=sid, prose=prose)
        if prompt.id == CC_VERIFY_PROMPT.id:
            vars_d = dict(prompt.variables)
            sid = vars_d["section_id"]
            draft = vars_d["draft_prose"]
            return VerifySectionOutput(
                section_id=sid,
                revised_prose=draft,
                claims=[
                    ClaimVerificationEntry(
                        claim_text="main",
                        support="supported",
                    ),
                ],
            )
        if prompt.id == CC_SYNTHESIZE_PROMPT.id:
            vj = json.loads(dict(prompt.variables)["verified_json"])
            sections: list[MemoSectionStructured] = []
            plan = _plan_fixture()
            for sid in CC_SECTION_IDS:
                sections.append(
                    MemoSectionStructured(
                        section_id=sid,
                        title=plan.section_titles[sid],
                        body=vj[sid],
                    ),
                )
            return SynthesizeSectionsOut(sections=sections)
        raise AssertionError(f"unexpected prompt {prompt.id}")

    monkeypatch.setattr(LLMClient, "complete_structured", _fake_complete_structured)

    r_post = await api_client.post(
        f"/cases/{case_id}/country-conditions",
        json={
            "country_code": "ER",
            "basis": ClaimBasis.political_opinion.value,
            "group_description": "Journalists",
            "timeframe_start_year": 2020,
            "jurisdiction_asylum_office": None,
        },
    )
    assert r_post.status_code == 202, r_post.text
    memo_id = uuid.UUID(r_post.json()["memo_id"])

    for _ in range(80):
        await asyncio.sleep(0.05)
        r_get = await api_client.get(f"/cases/{case_id}/country-conditions/{memo_id}")
        if r_get.status_code != 200:
            continue
        st = r_get.json()["status"]
        if st == CountryConditionsMemoStatus.complete.value:
            break
        if st == CountryConditionsMemoStatus.failed.value:
            pytest.fail(r_get.json().get("error_message", "failed"))
    else:
        pytest.fail("memo did not complete in time")

    r_get = await api_client.get(f"/cases/{case_id}/country-conditions/{memo_id}")
    assert r_get.status_code == 200
    body = r_get.json()
    assert body["status"] == CountryConditionsMemoStatus.complete.value
    out = body["output"]
    assert out is not None
    assert len(out["sections"]) == 5
    for sec in out["sections"]:
        assert "<cite passage_id=" in sec["body"]
        pid = sec["body"].split('passage_id="')[1].split('"')[0]
        expected_ids = {
            uuid.UUID(fake_rows[s][0]["passage_id"]) for s in CC_SECTION_IDS
        }
        assert uuid.UUID(pid) in expected_ids

    stmt = select(AuditLogEntry).where(
        AuditLogEntry.resource_id == memo_id,
    )
    rows = (await db_session.execute(stmt)).scalars().all()
    actions = {e.action for e in rows}
    assert "country_conditions.generate.start" in actions
    assert "country_conditions.plan.complete" in actions
    assert "country_conditions.retrieve.complete" in actions
    assert "country_conditions.draft.complete" in actions
    assert "country_conditions.verify.complete" in actions
    assert "country_conditions.synthesize.complete" in actions
    assert "country_conditions.generate.complete" in actions


@pytest.mark.asyncio(loop_scope="session")
async def test_country_conditions_checkpoint_resume(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rows = _fake_search_rows()

    async def _fake_search(
        session: AsyncSession,
        query: str,
        *,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        country_codes: list[str],
        date_after: date | None = None,
        source_families: list[str] | None = None,
        top_k: int = 20,
        cache: Any = None,
        settings: Any = None,
    ) -> Any:
        from retrieval.schemas import RetrievedPassage

        for sid in CC_SECTION_IDS:
            if query == f"query for {sid}":
                p = fake_rows[sid][0]
                return [
                    RetrievedPassage(
                        passage_id=uuid.UUID(p["passage_id"]),
                        document_id=uuid.UUID(p["document_id"]),
                        source_family=p["source_family"],
                        document_title=p["document_title"],
                        publication_date=date.fromisoformat(p["publication_date"]),
                        url=p["url"],
                        section_anchor=p["section_anchor"],
                        text=p["text"],
                        similarity_score=float(p["similarity_score"]),
                    ),
                ]
        return []

    monkeypatch.setattr("country_conditions.graph.search", _fake_search)

    call_n = {"v": 0}

    async def _fake_complete_structured(
        self: LLMClient,
        prompt: Any,
        schema: type[Any],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Any:
        _ = (max_tokens, temperature)
        if prompt.id == CC_PLAN_PROMPT.id:
            return _plan_fixture()
        if prompt.id == CC_DRAFT_PROMPT.id:
            call_n["v"] += 1
            vars_d = dict(prompt.variables)
            sid = vars_d["section_id"]
            pdata = json.loads(vars_d["passages_json"])
            pid = uuid.UUID(pdata[0]["passage_id"])
            prose = f'Draft for {sid}. <cite passage_id="{pid}"/>'
            return SectionDraftOutput(section_id=sid, prose=prose)
        if prompt.id == CC_VERIFY_PROMPT.id:
            vars_d = dict(prompt.variables)
            sid = vars_d["section_id"]
            draft = vars_d["draft_prose"]
            return VerifySectionOutput(
                section_id=sid,
                revised_prose=draft,
                claims=[],
            )
        if prompt.id == CC_SYNTHESIZE_PROMPT.id:
            vj = json.loads(dict(prompt.variables)["verified_json"])
            sections = []
            plan = _plan_fixture()
            for sid in CC_SECTION_IDS:
                sections.append(
                    MemoSectionStructured(
                        section_id=sid,
                        title=plan.section_titles[sid],
                        body=vj[sid],
                    ),
                )
            return SynthesizeSectionsOut(sections=sections)
        raise AssertionError(f"unexpected prompt {prompt.id}")

    monkeypatch.setattr(LLMClient, "complete_structured", _fake_complete_structured)

    org_repo = OrgRepository(db_session)
    slug_re = f"re-{uuid.uuid4().hex[:8]}"
    org = await org_repo.create_org(name="Resume Org", slug=slug_re)
    org_id = org.id
    u = await org_repo.create_user(
        organization_id=org_id,
        email="re@example.com",
        display_name="R",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    from audit.writer import AuditWriter

    case = Case(
        id=uuid.uuid4(),
        organization_id=org_id,
        pseudonym="P",
        country_code="ER",
        basis=ClaimBasis.political_opinion,
        group_description="G",
        filing_deadline=None,
        asylum_office=None,
        intake_notes="i",
        created_by_user_id=u.id,
    )
    db_session.add(case)
    db_session.add(
        CaseAssignment(
            case_id=case.id,
            user_id=u.id,
            role_on_case=CaseAssignmentRole.lead_attorney,
        ),
    )
    await db_session.flush()

    memo_id = uuid.uuid4()
    art_id = uuid.uuid4()
    db_session.add(
        CaseArtifact(
            id=art_id,
            case_id=case.id,
            artifact_type=CaseArtifactType.country_conditions_memo,
        ),
    )
    db_session.add(
        CountryConditionsMemo(
            id=memo_id,
            organization_id=org_id,
            case_id=case.id,
            case_artifact_id=art_id,
            status=CountryConditionsMemoStatus.generating,
            inputs=CountryConditionsInputs(
                country_code="ER",
                basis=ClaimBasis.political_opinion,
                group_description="G",
                timeframe_start_year=2020,
                jurisdiction_asylum_office=None,
            ).model_dump(mode="json"),
            output=None,
            version=1,
            generated_by_user_id=u.id,
            generated_at=None,
            model_versions={},
            error_message=None,
            correlation_request_id=uuid.uuid4(),
        ),
    )
    await db_session.commit()

    settings = get_settings()
    uri = settings.resolved_checkpoint_database_url()
    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
        await checkpointer.setup()
        from db.session import get_async_session_maker

        factory = get_async_session_maker()
        async with factory() as session:
            audit = AuditWriter(session, uuid.uuid4())
            g1 = build_country_conditions_graph(
                checkpointer=checkpointer,
                session=session,
                organization_id=org_id,
                user_id=u.id,
                memo_id=memo_id,
                audit=audit,
                interrupt_after=["retrieve"],
            )
            init: dict[str, Any] = {
                "organization_id": org_id,
                "case_id": case.id,
                "memo_id": memo_id,
                "requested_by_user_id": u.id,
                "inputs": CountryConditionsInputs(
                    country_code="ER",
                    basis=ClaimBasis.political_opinion,
                    group_description="G",
                    timeframe_start_year=2020,
                    jurisdiction_asylum_office=None,
                ).model_dump(mode="json"),
                "model_versions": {},
            }
            cfg = {"configurable": {"thread_id": str(memo_id)}}
            await g1.ainvoke(init, cfg)
            g2 = build_country_conditions_graph(
                checkpointer=checkpointer,
                session=session,
                organization_id=org_id,
                user_id=u.id,
                memo_id=memo_id,
                audit=audit,
                interrupt_after=None,
            )
            final = await g2.ainvoke(None, cfg)
    assert "final_memo" in final
    assert len(final["final_memo"]["sections"]) == 5


@pytest.mark.asyncio(loop_scope="session")
async def test_verify_removes_planted_unsupported_sentence(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_rows = _fake_search_rows()

    async def _fake_search(
        session: AsyncSession,
        query: str,
        *,
        organization_id: uuid.UUID | None,
        user_id: uuid.UUID | None,
        country_codes: list[str],
        date_after: date | None = None,
        source_families: list[str] | None = None,
        top_k: int = 20,
        cache: Any = None,
        settings: Any = None,
    ) -> Any:
        from retrieval.schemas import RetrievedPassage

        for sid in CC_SECTION_IDS:
            if query == f"query for {sid}":
                p = fake_rows[sid][0]
                return [
                    RetrievedPassage(
                        passage_id=uuid.UUID(p["passage_id"]),
                        document_id=uuid.UUID(p["document_id"]),
                        source_family=p["source_family"],
                        document_title=p["document_title"],
                        publication_date=date.fromisoformat(p["publication_date"]),
                        url=p["url"],
                        section_anchor=p["section_anchor"],
                        text=p["text"],
                        similarity_score=float(p["similarity_score"]),
                    ),
                ]
        return []

    monkeypatch.setattr("country_conditions.graph.search", _fake_search)

    async def _fake_complete_structured(
        self: LLMClient,
        prompt: Any,
        schema: type[Any],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Any:
        _ = (max_tokens, temperature)
        if prompt.id == CC_PLAN_PROMPT.id:
            return _plan_fixture()
        if prompt.id == CC_DRAFT_PROMPT.id:
            vars_d = dict(prompt.variables)
            sid = vars_d["section_id"]
            pdata = json.loads(vars_d["passages_json"])
            pid = uuid.UUID(pdata[0]["passage_id"])
            base = f'Official text exists. <cite passage_id="{pid}"/>'
            if sid == "general_conditions":
                base += " PLANTED_UNSUPPORTED_CLAIM_XYZ."
            return SectionDraftOutput(section_id=sid, prose=base)
        if prompt.id == CC_VERIFY_PROMPT.id:
            vars_d = dict(prompt.variables)
            sid = vars_d["section_id"]
            draft = vars_d["draft_prose"]
            cleaned = draft.replace(" PLANTED_UNSUPPORTED_CLAIM_XYZ.", "")
            pdata = json.loads(vars_d["passages_json"])
            pid = uuid.UUID(pdata[0]["passage_id"])
            if "PLANTED" in draft:
                assert sid == "general_conditions"
                if not cleaned.strip().endswith("/>"):
                    cleaned = f'Official text exists. <cite passage_id="{pid}"/>'
                return VerifySectionOutput(
                    section_id=sid,
                    revised_prose=cleaned,
                    claims=[
                        ClaimVerificationEntry(
                            claim_text="planted",
                            support="unsupported",
                        ),
                    ],
                )
            return VerifySectionOutput(
                section_id=sid,
                revised_prose=draft,
                claims=[],
            )
        if prompt.id == CC_SYNTHESIZE_PROMPT.id:
            vj = json.loads(dict(prompt.variables)["verified_json"])
            sections = []
            plan = _plan_fixture()
            for s2 in CC_SECTION_IDS:
                sections.append(
                    MemoSectionStructured(
                        section_id=s2,
                        title=plan.section_titles[s2],
                        body=vj[s2],
                    ),
                )
            return SynthesizeSectionsOut(sections=sections)
        raise AssertionError(f"unexpected prompt {prompt.id}")

    monkeypatch.setattr(LLMClient, "complete_structured", _fake_complete_structured)

    org_repo = OrgRepository(db_session)
    org = await org_repo.create_org(name="V Org", slug=f"v-{uuid.uuid4().hex[:8]}")
    u = await org_repo.create_user(
        organization_id=org.id,
        email="v@example.com",
        display_name="V",
        role=UserRole.attorney,
        status=UserStatus.active,
    )
    await db_session.commit()

    from audit.writer import AuditWriter

    case = Case(
        id=uuid.uuid4(),
        organization_id=org.id,
        pseudonym="P",
        country_code="ER",
        basis=ClaimBasis.political_opinion,
        group_description="G",
        filing_deadline=None,
        asylum_office=None,
        intake_notes="i",
        created_by_user_id=u.id,
    )
    db_session.add(case)
    db_session.add(
        CaseAssignment(
            case_id=case.id,
            user_id=u.id,
            role_on_case=CaseAssignmentRole.lead_attorney,
        ),
    )
    await db_session.flush()

    memo_id = uuid.uuid4()
    art_id = uuid.uuid4()
    db_session.add(
        CaseArtifact(
            id=art_id,
            case_id=case.id,
            artifact_type=CaseArtifactType.country_conditions_memo,
        ),
    )
    db_session.add(
        CountryConditionsMemo(
            id=memo_id,
            organization_id=org.id,
            case_id=case.id,
            case_artifact_id=art_id,
            status=CountryConditionsMemoStatus.generating,
            inputs=CountryConditionsInputs(
                country_code="ER",
                basis=ClaimBasis.political_opinion,
                group_description="G",
                timeframe_start_year=2020,
                jurisdiction_asylum_office=None,
            ).model_dump(mode="json"),
            output=None,
            version=1,
            generated_by_user_id=u.id,
            generated_at=None,
            model_versions={},
            error_message=None,
            correlation_request_id=uuid.uuid4(),
        ),
    )
    await db_session.commit()

    settings = get_settings()
    uri = settings.resolved_checkpoint_database_url()
    async with AsyncPostgresSaver.from_conn_string(uri) as checkpointer:
        await checkpointer.setup()
        from db.session import get_async_session_maker

        factory = get_async_session_maker()
        async with factory() as session:
            audit = AuditWriter(session, uuid.uuid4())
            graph = build_country_conditions_graph(
                checkpointer=checkpointer,
                session=session,
                organization_id=org.id,
                user_id=u.id,
                memo_id=memo_id,
                audit=audit,
            )
            init: dict[str, Any] = {
                "organization_id": org.id,
                "case_id": case.id,
                "memo_id": memo_id,
                "requested_by_user_id": u.id,
                "inputs": CountryConditionsInputs(
                    country_code="ER",
                    basis=ClaimBasis.political_opinion,
                    group_description="G",
                    timeframe_start_year=2020,
                    jurisdiction_asylum_office=None,
                ).model_dump(mode="json"),
                "model_versions": {},
            }
            final = await graph.ainvoke(
                init,
                {"configurable": {"thread_id": str(memo_id)}},
            )
    body = final["final_memo"]
    gen_sec = next(
        s for s in body["sections"] if s["section_id"] == "general_conditions"
    )
    assert "PLANTED_UNSUPPORTED_CLAIM_XYZ" not in gen_sec["body"]
