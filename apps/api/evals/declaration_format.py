"""Serialize declaration drafts and source material for LLM-as-judge evals."""

from __future__ import annotations

import json
from typing import Any

from declarations.schemas import DECLARATION_SECTION_IDS

_SECTION_LABELS: dict[str, str] = {
    "identity_background": "Identity and background",
    "past_persecution": "Past persecution",
    "perpetrator_motivation": "Perpetrator motivation",
    "well_founded_fear_future": "Well-founded fear of future harm",
    "internal_relocation": "Internal relocation",
    "filing_bar_facts": "Filing bar and entry facts",
}

_MAX_JUDGE_CHARS = 50_000


def format_draft_for_judge(
    *,
    draft: dict[str, Any],
    flags: list[dict[str, Any]],
    transcript: dict[str, Any],
    prior_statements: list[dict[str, Any]],
) -> str:
    """Build a single evaluation package for the declaration quality judge."""
    parts: list[str] = []

    parts.append("## Source transcript (English segments)\n")
    segments = transcript.get("segments")
    if isinstance(segments, list):
        for i, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue
            english = seg.get("english_text", "")
            if isinstance(english, str) and english.strip():
                parts.append(f"- seg-{i}: {english.strip()}\n")
    full_en = transcript.get("full_english_text")
    if isinstance(full_en, str) and full_en.strip():
        parts.append(f"\nFull English transcript:\n{full_en.strip()}\n")

    if prior_statements:
        parts.append("\n## Prior statements\n")
        for i, prior in enumerate(prior_statements):
            if not isinstance(prior, dict):
                continue
            stype = prior.get("statement_type", "unknown")
            english = prior.get("english_text", "")
            if isinstance(english, str) and english.strip():
                parts.append(f"### Prior {i + 1} ({stype})\n{english.strip()}\n")

    parts.append("\n## Generated declaration draft\n")
    sections = draft.get("sections") if isinstance(draft, dict) else None
    if isinstance(sections, dict):
        for section_id in DECLARATION_SECTION_IDS:
            section = sections.get(section_id)
            label = _SECTION_LABELS.get(section_id, section_id)
            parts.append(f"### {label}\n")
            if not isinstance(section, dict):
                parts.append("(missing)\n")
                continue
            paragraphs = section.get("paragraphs")
            if not isinstance(paragraphs, list) or not paragraphs:
                parts.append("(empty)\n")
                continue
            for para in paragraphs:
                if not isinstance(para, dict):
                    continue
                text = para.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(f"{text.strip()}\n\n")

    parts.append("\n## Flags\n")
    if not flags:
        parts.append("(none)\n")
    else:
        parts.append(json.dumps(flags, indent=2, default=str))
        parts.append("\n")

    rendered = "".join(parts)
    if len(rendered) > _MAX_JUDGE_CHARS:
        return rendered[:_MAX_JUDGE_CHARS]
    return rendered
