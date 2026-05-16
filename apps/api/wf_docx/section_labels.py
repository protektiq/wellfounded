"""Human-readable section titles and GAP element to section mapping."""

from __future__ import annotations

from declarations.schemas import DECLARATION_SECTION_IDS

SECTION_LABELS: dict[str, str] = {
    "identity_background": "I. Identity and Background",
    "past_persecution": "II. Past Persecution",
    "perpetrator_motivation": "III. Perpetrator Motivation",
    "well_founded_fear_future": "IV. Well-Founded Fear of Future Harm",
    "internal_relocation": "V. Internal Relocation",
    "filing_bar_facts": "VI. One-Year Filing Bar and Related Facts",
}

# Maps gap-check element_key to the declaration section used for comment anchoring.
ELEMENT_KEY_SECTION: dict[str, str] = {
    "first_incident_date": "past_persecution",
    "biographical_identity": "identity_background",
    "past_persecution_events": "past_persecution",
    "persecutors_identified": "perpetrator_motivation",
    "harms_articulated": "past_persecution",
    "protected_ground_stated": "identity_background",
    "nexus_articulated": "perpetrator_motivation",
    "well_founded_fear_future": "well_founded_fear_future",
    "internal_relocation_addressed": "internal_relocation",
    "one_year_filing_bar_facts": "filing_bar_facts",
}


def section_heading(section_id: str) -> str:
    if section_id in SECTION_LABELS:
        return SECTION_LABELS[section_id]
    return section_id.replace("_", " ").title()


def ordered_section_ids() -> tuple[str, ...]:
    return DECLARATION_SECTION_IDS
