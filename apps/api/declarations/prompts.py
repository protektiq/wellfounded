"""Prompt templates for declaration LangGraph nodes."""

from __future__ import annotations

from llm.prompts import DEFAULT_CLAUDE_MODEL, Prompt

DECL_EXTRACT_PROMPT = Prompt(
    id="declaration.extract",
    system=(
        "You extract structured asylum claim facts from an interview transcript. "
        "Only include facts the client stated or clearly confirmed. "
        "Do not infer dates or motives unless the client stated them explicitly."
    ),
    user_template=(
        "Case metadata:\n{case_metadata_json}\n\n"
        "Transcript (English segments):\n{transcript_json}\n\n"
        "Return structured claim intermediate representation."
    ),
    variables=(
        ("case_metadata_json", ""),
        ("transcript_json", ""),
    ),
    model_id=DEFAULT_CLAUDE_MODEL,
    default_max_tokens=8192,
)

DECL_INCONSISTENCY_PROMPT = Prompt(
    id="declaration.inconsistency_check",
    system=(
        "You compare a structured claim extraction to prior statements. "
        "Report factual divergences only. Include verbatim quotes from both sources."
    ),
    user_template=(
        "Extracted claim IR:\n{claim_ir_json}\n\n"
        "Prior statements:\n{prior_statements_json}\n\n"
        "List each inconsistency with transcript_quote and prior_quote."
    ),
    variables=(
        ("claim_ir_json", ""),
        ("prior_statements_json", ""),
    ),
    model_id=DEFAULT_CLAUDE_MODEL,
    default_max_tokens=4096,
)

DECL_DRAFT_PROMPT = Prompt(
    id="declaration.draft",
    system=(
        "You draft a first-person asylum declaration in the client's voice. "
        "Use six sections: identity_background, past_persecution, "
        "perpetrator_motivation, well_founded_fear_future, internal_relocation, "
        "filing_bar_facts. Each paragraph must list source_segment_ids from the transcript. "
        "Mark inference_spans for any phrase not directly supported by the IR or transcript. "
        "Also emit flags for INFERENCE, AMBIGUITY, and TRANSLATION_UNCERTAINTY where applicable."
    ),
    user_template=(
        "Case metadata:\n{case_metadata_json}\n\n"
        "Claim IR:\n{claim_ir_json}\n\n"
        "Transcript segments:\n{transcript_json}\n\n"
        "Existing gap and inconsistency flags (preserve in output flags if still valid):\n"
        "{existing_flags_json}\n\n"
        "Produce the full declaration draft."
    ),
    variables=(
        ("case_metadata_json", ""),
        ("claim_ir_json", ""),
        ("transcript_json", ""),
        ("existing_flags_json", ""),
    ),
    model_id=DEFAULT_CLAUDE_MODEL,
    default_max_tokens=16384,
)

DECL_REVISE_PROMPT = Prompt(
    id="declaration.revise",
    system=(
        "You revise a declaration draft per attorney instruction. "
        "Do not remove or soften open GAP or INCONSISTENCY flags unless the instruction "
        "explicitly resolves them. Preserve all other open flags."
    ),
    user_template=(
        "Instruction:\n{instruction}\n\n"
        "Scope paragraph_id: {paragraph_id}\n"
        "Scope section_id: {section_id}\n\n"
        "Current draft:\n{draft_json}\n\n"
        "Claim IR:\n{claim_ir_json}\n\n"
        "Open flags:\n{flags_json}\n\n"
        "Return the updated draft and any new or updated flags for the revised scope only."
    ),
    variables=(
        ("instruction", ""),
        ("paragraph_id", ""),
        ("section_id", ""),
        ("draft_json", ""),
        ("claim_ir_json", ""),
        ("flags_json", ""),
    ),
    model_id=DEFAULT_CLAUDE_MODEL,
    default_max_tokens=16384,
)
