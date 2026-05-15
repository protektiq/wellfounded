"""Seed org, user, case, and passage for country-conditions Playwright E2E.

Run from repo root after ``make up`` and ``make db-migrate``:

    cd apps/api && poetry run python -m scripts.e2e_seed_country_conditions

Prints one JSON line to stdout with ``organization_slug``, ``email``, ``case_id``.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select

from cases.models import Case, CaseAssignmentRole, ClaimBasis
from cases.repository import CaseRepository
from country_conditions.e2e_stub import E2E_STUB_PASSAGE_ID
from db.session import get_async_session_maker
from orgs.models import UserRole, UserStatus
from orgs.repository import OrgRepository
from retrieval.models import SourceDocument, SourceFamily, SourcePassage


def _ortho_vec(dim_index: int) -> list[float]:
    v = [0.0] * 3072
    v[dim_index % 3072] = 1.0
    return v


_ORG_SLUG = "wf-e2e-cc"
_USER_EMAIL = "e2e-cc-attorney@example.test"
_PASSAGE_TEXT = (
    "E2E seeded passage text for citation drawer verification. "
    "Conditions on the ground are documented in official sources."
)


async def _run() -> None:
    factory = get_async_session_maker()
    async with factory() as session:
        org_repo = OrgRepository(session)
        org = await org_repo.get_org_by_slug(_ORG_SLUG)
        if org is None:
            org = await org_repo.create_org(
                name="E2E Country Conditions",
                slug=_ORG_SLUG,
            )

        user = await org_repo.get_user_by_email(_USER_EMAIL, org.id)
        if user is None:
            user = await org_repo.create_user(
                organization_id=org.id,
                email=_USER_EMAIL,
                display_name="E2E Attorney",
                role=UserRole.attorney,
                status=UserStatus.active,
            )

        existing_passage = await session.get(SourcePassage, E2E_STUB_PASSAGE_ID)
        if existing_passage is None:
            doc = SourceDocument(
                source_family=SourceFamily.state_dept_human_rights,
                title="E2E Country Conditions Report",
                publication_date=date(2024, 1, 1),
                country_codes=["ER"],
                url="https://example.test/e2e-country-report",
                last_verified_at=datetime.now(UTC),
                content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            )
            session.add(doc)
            await session.flush()
            session.add(
                SourcePassage(
                    id=E2E_STUB_PASSAGE_ID,
                    source_document_id=doc.id,
                    section_anchor="Section A",
                    text=_PASSAGE_TEXT,
                    embedding=_ortho_vec(42),
                    token_count=max(1, len(_PASSAGE_TEXT) // 4),
                ),
            )
            await session.flush()

        stmt = select(Case).where(
            Case.organization_id == org.id,
            Case.pseudonym == "E2E M.A. — Eritrea",
            Case.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        case_row = result.scalar_one_or_none()
        if case_row is None:
            case_repo = CaseRepository(session)
            case_row = await case_repo.create_case(
                organization_id=org.id,
                created_by_user_id=user.id,
                pseudonym="E2E M.A. — Eritrea",
                country_code="ER",
                basis=ClaimBasis.political_opinion,
                group_description="Journalists",
                filing_deadline=None,
                asylum_office=None,
                intake_notes="E2E seed",
                assignments=[(user.id, CaseAssignmentRole.lead_attorney)],
            )

        await session.commit()
        payload = {
            "organization_slug": org.slug,
            "email": user.email,
            "case_id": str(case_row.id),
        }
        sys.stdout.write(json.dumps(payload) + "\n")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
