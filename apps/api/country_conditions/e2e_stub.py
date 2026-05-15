"""Deterministic country-conditions memo payload for Playwright / E2E (local only)."""

from __future__ import annotations

import uuid

from country_conditions.schemas import (
    CC_SECTION_IDS,
    BibliographyEntryStructured,
    FinalMemoStructured,
    MemoSectionStructured,
)

# Fixed passage id referenced by seed script and stub memo bodies.
E2E_STUB_PASSAGE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def e2e_stub_final_memo_dict() -> dict[str, object]:
    """Minimal valid final memo citing ``E2E_STUB_PASSAGE_ID`` in every section."""
    cite = f'<cite passage_id="{E2E_STUB_PASSAGE_ID}"/>'
    sections: list[MemoSectionStructured] = []
    titles = {
        "general_conditions": "General country conditions",
        "treatment_of_group": "Treatment of the particular social group",
        "state_actor_involvement": "State actor involvement",
        "internal_relocation": "Internal relocation",
        "recent_trends": "Recent trends",
    }
    for sid in CC_SECTION_IDS:
        sections.append(
            MemoSectionStructured(
                section_id=sid,
                title=titles[sid],
                body=f"Overview for {sid}. Evidence supports this analysis. {cite}",
            ),
        )
    final = FinalMemoStructured(
        sections=sections,
        bibliography=[
            BibliographyEntryStructured(
                index=1,
                passage_id=E2E_STUB_PASSAGE_ID,
                source_title="E2E Country Conditions Report",
                publication_date="2024-01-01",
                url="https://example.test/e2e-country-report",
                section_anchor="Section A",
            ),
        ],
    )
    return final.model_dump(mode="json")
