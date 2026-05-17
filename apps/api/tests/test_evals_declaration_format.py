"""Tests for declaration eval serialization helper."""

from __future__ import annotations

from evals.declaration_format import format_draft_for_judge


def test_format_draft_for_judge_includes_sections_and_sources() -> None:
    draft = {
        "sections": {
            "identity_background": {
                "section_id": "identity_background",
                "paragraphs": [
                    {
                        "id": "identity_background:p0",
                        "text": "I am M.A. from Eritrea.",
                        "source_segment_ids": ["seg-0"],
                    },
                ],
            },
            "past_persecution": {
                "section_id": "past_persecution",
                "paragraphs": [
                    {
                        "id": "past_persecution:p0",
                        "text": "In March 2023 I was detained.",
                        "source_segment_ids": ["seg-1"],
                    },
                ],
            },
        },
    }
    transcript = {
        "segments": [
            {
                "english_text": "My name is M.A.",
            },
            {
                "english_text": "In March 2023 I was detained.",
            },
        ],
        "full_english_text": "My name is M.A. In March 2023 I was detained.",
    }
    flags = [
        {
            "type": "GAP",
            "description": "Missing first incident date",
        },
    ]
    priors = [
        {
            "statement_type": "credible_fear_interview",
            "english_text": "Three men grabbed me.",
        },
    ]

    rendered = format_draft_for_judge(
        draft=draft,
        flags=flags,
        transcript=transcript,
        prior_statements=priors,
    )

    assert "seg-0: My name is M.A." in rendered
    assert "I am M.A. from Eritrea." in rendered
    assert "Past persecution" in rendered
    assert "Prior 1" in rendered
    assert "GAP" in rendered
