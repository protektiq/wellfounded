"""Deterministic application of flag resolution text to declaration draft content."""

from __future__ import annotations

from declarations.schemas import (
    DeclarationDraftContent,
    DeclarationFlag,
    DeclarationFlagStatus,
    DeclarationFlagType,
    DeclarationParagraph,
)


def _find_paragraph(
    draft: DeclarationDraftContent,
    paragraph_id: str,
) -> tuple[str, int, DeclarationParagraph]:
    for section_id, section in draft.sections.items():
        for idx, para in enumerate(section.paragraphs):
            if para.id == paragraph_id:
                return section_id, idx, para
    raise ValueError(f"paragraph {paragraph_id} not found in draft")


def apply_resolution_to_draft(
    draft: DeclarationDraftContent,
    flag: DeclarationFlag,
    resolution_text: str,
) -> DeclarationDraftContent:
    """Return a new draft with resolution text applied to the flagged paragraph."""
    if flag.status == DeclarationFlagStatus.deferred:
        return draft

    section_id, para_idx, para = _find_paragraph(draft, flag.paragraph_id)
    text = para.text
    start = flag.span.start
    end = flag.span.end
    if start > len(text) or end > len(text):
        raise ValueError("flag span is out of range for paragraph text")

    if (
        flag.type == DeclarationFlagType.GAP
        or start == end
        or (end - start) <= 0
    ):
        sep = "" if not text or text.endswith((" ", "\n")) else " "
        new_text = f"{text}{sep}{resolution_text}".strip()
        if len(new_text) < 1:
            raise ValueError("paragraph text would be empty after apply")
    else:
        new_text = text[:start] + resolution_text + text[end:]
        if len(new_text) < 1:
            raise ValueError("paragraph text would be empty after apply")

    updated_para = para.model_copy(update={"text": new_text})
    section = draft.sections[section_id]
    paragraphs = list(section.paragraphs)
    paragraphs[para_idx] = updated_para
    updated_section = section.model_copy(update={"paragraphs": paragraphs})
    sections = dict(draft.sections)
    sections[section_id] = updated_section
    return draft.model_copy(update={"sections": sections})
