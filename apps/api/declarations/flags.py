"""Flag helpers for declaration drafts."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from declarations.schemas import (
    DeclarationFlag,
    DeclarationFlagStatus,
    DeclarationFlagType,
    DeclarationReviseScope,
)

REQUIRED_FOR_CLEAN_EXPORT: frozenset[DeclarationFlagType] = frozenset(
    {
        DeclarationFlagType.GAP,
        DeclarationFlagType.INFERENCE,
        DeclarationFlagType.INCONSISTENCY,
    }
)


def flags_from_dicts(raw: list[object]) -> list[DeclarationFlag]:
    out: list[DeclarationFlag] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(DeclarationFlag.model_validate(item))
    return out


def flags_to_dicts(flags: list[DeclarationFlag]) -> list[dict[str, Any]]:
    return [f.model_dump(mode="json") for f in flags]


def unresolved_required_flag_ids(flags: list[DeclarationFlag]) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []
    for f in flags:
        if f.type not in REQUIRED_FOR_CLEAN_EXPORT:
            continue
        if f.status == DeclarationFlagStatus.open:
            ids.append(f.id)
    return ids


def merge_flags_on_revise(
    parent_flags: list[DeclarationFlag],
    new_flags: list[DeclarationFlag],
    scope: DeclarationReviseScope,
) -> list[DeclarationFlag]:
    """Preserve open required flags unless explicitly revised in scope."""
    merged: dict[uuid.UUID, DeclarationFlag] = {f.id: f for f in parent_flags}
    scope_paragraph = scope.paragraph_id
    scope_section = scope.section_id

    for nf in new_flags:
        merged[nf.id] = nf

    for pf in parent_flags:
        if pf.status != DeclarationFlagStatus.open:
            continue
        if pf.type not in REQUIRED_FOR_CLEAN_EXPORT:
            continue
        if _flag_in_scope(pf, scope_paragraph, scope_section):
            replaced = any(
                nf.type == pf.type
                and nf.paragraph_id == pf.paragraph_id
                and nf.span.start == pf.span.start
                and nf.span.end == pf.span.end
                for nf in new_flags
            )
            if not replaced:
                merged[pf.id] = pf
        else:
            merged[pf.id] = pf

    return list(merged.values())


def _flag_in_scope(
    flag: DeclarationFlag,
    paragraph_id: str | None,
    section_id: str | None,
) -> bool:
    if paragraph_id is not None and flag.paragraph_id == paragraph_id:
        return True
    if section_id is not None and flag.paragraph_id.startswith(f"{section_id}:"):
        return True
    return False


def validate_flags(flags: list[DeclarationFlag]) -> None:
    for f in flags:
        if not f.suggested_resolution.strip():
            raise ValueError(f"flag {f.id} missing suggested_resolution")


def status_after_flags(flags: list[DeclarationFlag]) -> Literal["draft_ready", "flags_unresolved"]:
    if unresolved_required_flag_ids(flags):
        return "flags_unresolved"
    return "draft_ready"
