"""Post-graph validation for declaration flags and draft content."""

from __future__ import annotations

import uuid

from declarations.elements import REQUIRED_ASYLUM_ELEMENTS
from declarations.flags import validate_flags as _validate_flag_fields
from declarations.schemas import (
    DeclarationDraftContent,
    DeclarationFlag,
    DeclarationFlagType,
    FlagSpan,
    validate_inference_flags,
)


def validate_declaration_output(
    draft: DeclarationDraftContent,
    flags: list[DeclarationFlag],
) -> None:
    _validate_flag_fields(flags)
    validate_inference_flags(draft, flags)
    for f in flags:
        if f.type == DeclarationFlagType.GAP:
            if not f.element_key:
                raise ValueError("GAP flag must include element_key")
            keys = {e.element_key for e in REQUIRED_ASYLUM_ELEMENTS}
            if f.element_key not in keys:
                raise ValueError(f"unknown element_key {f.element_key}")
        if f.type == DeclarationFlagType.INCONSISTENCY:
            if not f.transcript_quote or not f.prior_quote:
                raise ValueError("INCONSISTENCY flag must include both quotes")
            if f.prior_statement_id is None:
                raise ValueError("INCONSISTENCY flag must include prior_statement_id")


def gap_flags_from_ir(
    ir_dict: dict[str, object],
) -> list[DeclarationFlag]:
    from declarations.elements import is_element_present

    flags: list[DeclarationFlag] = []
    ir_data = {k: v for k, v in ir_dict.items()}
    for element in REQUIRED_ASYLUM_ELEMENTS:
        if is_element_present(ir_data, element):
            continue
        flags.append(
            DeclarationFlag(
                id=uuid.uuid4(),
                type=DeclarationFlagType.GAP,
                paragraph_id=f"gap:{element.element_key}",
                span=FlagSpan(start=0, end=0),
                description=element.gap_description_template,
                suggested_resolution=element.suggested_resolution_template,
                element_key=element.element_key,
            ),
        )
    return flags
