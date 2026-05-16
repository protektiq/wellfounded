"""Required asylum claim elements for deterministic gap analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RequiredElement:
    element_key: str
    ir_path: str
    gap_description_template: str
    suggested_resolution_template: str


REQUIRED_ASYLUM_ELEMENTS: tuple[RequiredElement, ...] = (
    RequiredElement(
        element_key="first_incident_date",
        ir_path="first_incident_date",
        gap_description_template=(
            "The source interview does not state when the first incident of harm occurred."
        ),
        suggested_resolution_template=(
            "Ask the client for the date (or month and year) of the first incident "
            "and add it to the declaration and I-589 timeline."
        ),
    ),
    RequiredElement(
        element_key="biographical_identity",
        ir_path="biographical_data",
        gap_description_template=(
            "Biographical identity (name used in declaration, birthplace, family) "
            "is missing or incomplete in the source material."
        ),
        suggested_resolution_template=(
            "Conduct a follow-up interview to confirm biographical details for "
            "the identity and background section."
        ),
    ),
    RequiredElement(
        element_key="past_persecution_events",
        ir_path="timeline_events",
        gap_description_template=(
            "No timeline of past persecution events was extracted from the interview."
        ),
        suggested_resolution_template=(
            "Ask the client to walk through each incident chronologically and record "
            "dates, locations, and actors."
        ),
    ),
    RequiredElement(
        element_key="persecutors_identified",
        ir_path="identified_persecutors",
        gap_description_template=(
            "Perpetrators or threatening actors were not identified in the source material."
        ),
        suggested_resolution_template=(
            "Clarify who detained, threatened, or harmed the client and their affiliation."
        ),
    ),
    RequiredElement(
        element_key="harms_articulated",
        ir_path="articulated_harms",
        gap_description_template=(
            "Specific harms suffered are not articulated in the source material."
        ),
        suggested_resolution_template=(
            "Ask the client to describe physical, psychological, or economic harm "
            "for each incident."
        ),
    ),
    RequiredElement(
        element_key="protected_ground_stated",
        ir_path="protected_ground_evidence",
        gap_description_template=(
            "Protected ground (race, religion, nationality, political opinion, PSG) "
            "is not stated in the source material."
        ),
        suggested_resolution_template=(
            "Confirm which protected ground applies and obtain client statements linking "
            "harm to that ground."
        ),
    ),
    RequiredElement(
        element_key="nexus_articulated",
        ir_path="nexus_evidence",
        gap_description_template=(
            "Nexus between harm and protected ground is not articulated in the source."
        ),
        suggested_resolution_template=(
            "Ask why the client believes they were targeted and document motive evidence."
        ),
    ),
    RequiredElement(
        element_key="well_founded_fear_future",
        ir_path="well_founded_fear_evidence",
        gap_description_template=(
            "Well-founded fear of future harm is not addressed in the source material."
        ),
        suggested_resolution_template=(
            "Ask the client what they fear if returned and what supports that fear today."
        ),
    ),
    RequiredElement(
        element_key="internal_relocation_addressed",
        ir_path="internal_relocation_evidence",
        gap_description_template=(
            "Internal relocation feasibility is not discussed in the source material."
        ),
        suggested_resolution_template=(
            "Ask whether the client could live safely elsewhere in the country and why not."
        ),
    ),
    RequiredElement(
        element_key="one_year_filing_bar_facts",
        ir_path="one_year_filing_bar_facts",
        gap_description_template=(
            "One-year filing bar facts (date of last entry, filing deadline) are missing."
        ),
        suggested_resolution_template=(
            "Confirm date of arrival in the United States and any changed circumstances "
            "affecting the one-year bar."
        ),
    ),
)


def _value_at_path(data: dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    cur: Any = data
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def is_element_present(ir: dict[str, Any], element: RequiredElement) -> bool:
    value = _value_at_path(ir, element.ir_path)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list | dict):
        return len(value) > 0
    return True
