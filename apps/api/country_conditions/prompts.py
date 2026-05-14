"""Prompt templates for country conditions LangGraph nodes."""

from __future__ import annotations

from llm.prompts import DEFAULT_CLAUDE_MODEL, Prompt

CC_PLAN_PROMPT = Prompt(
    id="country_conditions.plan.outline",
    system=(
        "You are a legal researcher planning a US asylum country conditions memo. "
        "Output structured data only via the tool. The memo has exactly five "
        "sections with these ids: general_conditions, treatment_of_group, "
        "state_actor_involvement, internal_relocation, recent_trends. For each "
        "section provide a short display title and one focused retrieval query "
        "for a vector search over official human rights sources."
    ),
    user_template=(
        "Case inputs (JSON):\n{inputs_json}\n\n"
        "Produce section_queries and section_titles with exactly those five keys "
        "each. Queries must be specific to the country, claim basis, and group "
        "described."
    ),
    variables=(("inputs_json", ""),),
    model_id=DEFAULT_CLAUDE_MODEL,
    default_max_tokens=8192,
    default_temperature=0.0,
)

CC_DRAFT_PROMPT = Prompt(
    id="country_conditions.draft.section",
    system=(
        "You draft a single section of a country conditions memo for US "
        "affirmative asylum. Use only the provided passages as evidence.\n\n"
        "Citation rules (strict):\n"
        "- Every factual sentence MUST end with one or more inline citation "
        'tokens in this exact form: <cite passage_id="UUID"/> where UUID is '
        "one of the passage_id values listed in the context.\n"
        "- Do not invent passage_id values.\n"
        "- Do not cite a passage that does not support the sentence.\n"
        "- If evidence is thin, write a shorter section rather than guessing.\n"
        "- Use neutral, precise legal tone."
    ),
    user_template=(
        "Section id: {section_id}\n"
        "Section retrieval query used: {section_query}\n\n"
        "Outline context:\n{outline}\n\n"
        "Retrieved passages (JSON array of objects with passage_id, "
        "document_title, publication_date, url, section_anchor, text):\n"
        "{passages_json}\n\n"
        "Draft the section prose only (structured output field prose). "
        "Include citation tokens as specified."
    ),
    variables=(
        ("section_id", ""),
        ("section_query", ""),
        ("outline", ""),
        ("passages_json", ""),
    ),
    model_id=DEFAULT_CLAUDE_MODEL,
    default_max_tokens=12_288,
    default_temperature=0.0,
)

CC_VERIFY_PROMPT = Prompt(
    id="country_conditions.verify.section",
    system=(
        "You verify citations in a country conditions memo section. Given the "
        'draft prose (with <cite passage_id="..."/> tokens) and the same '
        "retrieved passages, classify each factual claim you can identify as "
        "supported, partially_supported, or unsupported by the cited passage "
        "text.\n\n"
        "Then produce revised_prose: rewrite or remove unsupported claims. "
        "The revised prose must still follow the same citation token rules and "
        "only use passage_id values from the provided passages."
    ),
    user_template=(
        "Section id: {section_id}\n\n"
        "Draft prose:\n{draft_prose}\n\n"
        "Retrieved passages (JSON):\n{passages_json}\n"
    ),
    variables=(
        ("section_id", ""),
        ("draft_prose", ""),
        ("passages_json", ""),
    ),
    model_id=DEFAULT_CLAUDE_MODEL,
    default_max_tokens=12_288,
    default_temperature=0.0,
)

CC_SYNTHESIZE_PROMPT = Prompt(
    id="country_conditions.synthesize.memo",
    system=(
        "You assemble the final structured memo JSON. You are given verified "
        "section bodies (with valid citation tokens). Produce one entry per "
        "section in fixed order: general_conditions, treatment_of_group, "
        "state_actor_involvement, internal_relocation, recent_trends. "
        "Preserve citation tokens exactly as provided in the bodies. "
        "Titles should be concise and professional."
    ),
    user_template=(
        "Verified sections (JSON map section_id to body prose):\n"
        "{verified_json}\n\n"
        "Optional short titles from planner (JSON map section_id to title):\n"
        "{titles_json}\n"
    ),
    variables=(("verified_json", ""), ("titles_json", "")),
    model_id=DEFAULT_CLAUDE_MODEL,
    default_max_tokens=16_384,
    default_temperature=0.0,
)
