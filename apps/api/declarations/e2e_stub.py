"""Local E2E fixture payload for declaration generation."""

from __future__ import annotations

from typing import Any


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
                            "inference_spans": [],
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
        "flags": [],
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
