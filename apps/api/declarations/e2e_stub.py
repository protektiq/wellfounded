"""Local E2E fixture payload for declaration generation."""

from __future__ import annotations

import copy
import uuid
from typing import Any

from declarations.flags import flags_to_dicts
from declarations.schemas import (
    DeclarationDraftContent,
    DeclarationFlag,
    DeclarationFlagStatus,
    DeclarationFlagType,
    DeclarationReviseScope,
)

_E2E_GAP_FLAG_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0001")
_E2E_INCONSISTENCY_FLAG_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0002")
_E2E_INFERENCE_FLAG_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeee0003")
_E2E_PRIOR_STATEMENT_ID = uuid.UUID("bbbbbbbb-bbbb-cccc-dddd-eeeeeeee0001")


def e2e_stub_declaration_payload() -> dict[str, Any]:
    """Minimal complete draft for Playwright when declaration_e2e_stub is enabled."""
    return {
        "draft": {
            "sections": {
                "identity_background": {
                    "section_id": "identity_background",
                    "paragraphs": [
                        {
                            "id": "identity_background:p0",
                            "text": "I am M.A., a journalist from Eritrea.",
                            "source_segment_ids": ["seg-0"],
                            "inference_spans": [],
                        },
                    ],
                },
                "past_persecution": {
                    "section_id": "past_persecution",
                    "paragraphs": [
                        {
                            "id": "past_persecution:p0",
                            "text": (
                                "In March 2023, four men in plain clothes detained me."
                            ),
                            "source_segment_ids": ["seg-1"],
                            "inference_spans": [
                                {
                                    "start": 0,
                                    "end": 10,
                                    "rationale": "E2E inference span for testing.",
                                },
                            ],
                        },
                    ],
                },
                "perpetrator_motivation": {
                    "section_id": "perpetrator_motivation",
                    "paragraphs": [
                        {
                            "id": "perpetrator_motivation:p0",
                            "text": "They targeted me because of my reporting.",
                            "source_segment_ids": ["seg-2"],
                            "inference_spans": [],
                        },
                    ],
                },
                "well_founded_fear_future": {
                    "section_id": "well_founded_fear_future",
                    "paragraphs": [
                        {
                            "id": "well_founded_fear_future:p0",
                            "text": "I fear arrest if I am returned.",
                            "source_segment_ids": ["seg-3"],
                            "inference_spans": [],
                        },
                    ],
                },
                "internal_relocation": {
                    "section_id": "internal_relocation",
                    "paragraphs": [
                        {
                            "id": "internal_relocation:p0",
                            "text": "I cannot live safely elsewhere in Eritrea.",
                            "source_segment_ids": ["seg-4"],
                            "inference_spans": [],
                        },
                    ],
                },
                "filing_bar_facts": {
                    "section_id": "filing_bar_facts",
                    "paragraphs": [
                        {
                            "id": "filing_bar_facts:p0",
                            "text": "I entered the United States in April 2023.",
                            "source_segment_ids": ["seg-5"],
                            "inference_spans": [],
                        },
                    ],
                },
            },
        },
        "flags": [
            {
                "id": str(_E2E_GAP_FLAG_ID),
                "type": DeclarationFlagType.GAP.value,
                "paragraph_id": "filing_bar_facts:p0",
                "span": {"start": 0, "end": 0},
                "description": "First incident date not stated in interview.",
                "suggested_resolution": (
                    "Add the date of the first incident: March 3, 2023."
                ),
                "status": DeclarationFlagStatus.open.value,
                "element_key": "first_incident_date",
            },
            {
                "id": str(_E2E_INCONSISTENCY_FLAG_ID),
                "type": DeclarationFlagType.INCONSISTENCY.value,
                "paragraph_id": "past_persecution:p0",
                "span": {"start": 16, "end": 24},
                "description": (
                    "Number of agents differs between interview and prior statement."
                ),
                "suggested_resolution": (
                    "Confirm with client whether there were three or four men."
                ),
                "status": DeclarationFlagStatus.open.value,
                "prior_statement_id": str(_E2E_PRIOR_STATEMENT_ID),
                "transcript_quote": "four men in plain clothes detained me",
                "prior_quote": "Three men in plain clothes grabbed me",
            },
            {
                "id": str(_E2E_INFERENCE_FLAG_ID),
                "type": DeclarationFlagType.INFERENCE.value,
                "paragraph_id": "past_persecution:p0",
                "span": {"start": 0, "end": 10},
                "description": "Opening phrase goes beyond direct client statement.",
                "suggested_resolution": (
                    "Revise to begin with the client's exact words from the transcript."
                ),
                "status": DeclarationFlagStatus.open.value,
            },
        ],
        "claim_ir": {
            "biographical_data": {"role": "journalist"},
            "timeline_events": [
                {
                    "event_date": "2023-03",
                    "description": "Detention by agents",
                    "segment_ids": ["seg-1"],
                },
            ],
            "identified_persecutors": ["state security"],
            "articulated_harms": ["detention"],
            "protected_ground_evidence": "political opinion",
            "nexus_evidence": "reporting",
            "well_founded_fear_evidence": "fear of arrest",
            "internal_relocation_evidence": "surveillance nationwide",
            "one_year_filing_bar_facts": "entered April 2023",
            "first_incident_date": "2023-03-03",
        },
        "model_versions": {"e2e": "fixture"},
    }


def e2e_stub_revise_payload(
    *,
    parent_draft: DeclarationDraftContent,
    parent_flags: list[DeclarationFlag],
    instruction: str,
    scope: DeclarationReviseScope,
) -> dict[str, Any]:
    """Deterministic revise result for local E2E (no LLM)."""
    draft = copy.deepcopy(parent_draft)
    note = f" [Revised: {instruction[:120]}]"
    section_id = scope.section_id
    paragraph_id = scope.paragraph_id
    for sid, section in draft.sections.items():
        if section_id is not None and sid != section_id:
            continue
        for idx, para in enumerate(section.paragraphs):
            if paragraph_id is not None and para.id != paragraph_id:
                continue
            if section_id is None and paragraph_id is None:
                continue
            updated = para.model_copy(update={"text": para.text + note})
            paragraphs = list(section.paragraphs)
            paragraphs[idx] = updated
            draft.sections[sid] = section.model_copy(update={"paragraphs": paragraphs})
            break
        else:
            continue
        break

    flags = [f.model_copy() for f in parent_flags]
    return {
        "draft": draft.model_dump(mode="json"),
        "flags": flags_to_dicts(flags),
    }
