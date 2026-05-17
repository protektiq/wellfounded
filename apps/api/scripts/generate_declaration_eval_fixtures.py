#!/usr/bin/env python3
"""Generate declaration_quality eval fixtures (engineering-seeded)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OUT_DIR = _REPO_ROOT / "evals" / "fixtures" / "declaration_quality"

_SECTION_IDS = (
    "identity_background",
    "past_persecution",
    "perpetrator_motivation",
    "well_founded_fear_future",
    "internal_relocation",
    "filing_bar_facts",
)


def _segments(items: list[tuple[str, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    start = 0.0
    for source, english in items:
        end = start + 30.0
        out.append(
            {
                "start": start,
                "end": end,
                "speaker": "client",
                "source_text": source,
                "english_text": english,
            },
        )
        start = end
    full_source = " ".join(s for s, _ in items)
    full_english = " ".join(e for _, e in items)
    return out, full_source, full_english


def _gold(
    paragraphs: dict[str, list[str]],
    *,
    notes: str,
) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for sid in _SECTION_IDS:
        texts = paragraphs.get(sid, [f"Substantive {sid} content for eval reference."])
        sections[sid] = {
            "section_id": sid,
            "paragraphs": [
                {
                    "id": f"{sid}:p{i}",
                    "text": text,
                    "source_segment_ids": [f"seg-{min(i, 2)}"],
                    "inference_spans": [],
                }
                for i, text in enumerate(texts)
            ],
        }
    return {"sections": sections, "notes": notes}


def _fixture(
    *,
    fixture_id: str,
    tags: list[str],
    lang: str,
    transcript: dict[str, Any],
    case_metadata: dict[str, Any],
    gold_paragraphs: dict[str, list[str]],
    gold_notes: str,
    prior_statements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": fixture_id,
        "category": "declaration_quality",
        "scorer": "declaration_quality_live",
        "tags": tags,
        "input": {
            "transcript": transcript,
            "prior_statements": prior_statements or [],
            "case_metadata": case_metadata,
        },
        "expected": {
            "rubric_path": "declaration_v1.md",
            "min_score": 4,
            "min_criteria": {"faithfulness_to_source": 4.5},
            "gold_declaration": _gold(gold_paragraphs, notes=gold_notes),
        },
    }


def _transcript(lang: str, items: list[tuple[str, str]]) -> dict[str, Any]:
    segs, full_s, full_e = _segments(items)
    return {
        "source_language": lang,
        "segments": segs,
        "full_source_text": full_s,
        "full_english_text": full_e,
    }


def _meta(
    pseudonym: str,
    country: str,
    basis: str,
    group: str,
) -> dict[str, Any]:
    return {
        "pseudonym": pseudonym,
        "country_code": country,
        "basis": basis,
        "group_description": group,
    }


def _all_fixtures() -> list[dict[str, Any]]:
    prior_cf_id = "bbbbbbbb-bbbb-cccc-dddd-eeeeeeee0001"
    fixtures: list[dict[str, Any]] = []

    fixtures.append(
        _fixture(
            fixture_id="ti-er-journalist-01",
            tags=["ti", "calibration", "er"],
            lang="ti",
            transcript=_transcript(
                "ti",
                [
                    ("እየ ስምየ M.A.", "My name is M.A."),
                    (
                        "ብሓደሮ ሰነይ 2023 ኣርባዕተ ሰባት",
                        "In March 2023 four men in plain clothes detained me at my office.",
                    ),
                    (
                        "ስለ ዘካየድኩዎም ዜና",
                        "They said it was because of my reporting on the government.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "M.A. — Eritrea",
                "ER",
                "political_opinion",
                "Eritrean journalists",
            ),
            prior_statements=[
                {
                    "id": prior_cf_id,
                    "statement_type": "credible_fear_interview",
                    "source_language": "ti",
                    "source_text": "ሰለስተ ሰባት",
                    "english_text": (
                        "Three men in plain clothes grabbed me at my office in March 2023."
                    ),
                },
            ],
            gold_paragraphs={
                "identity_background": [
                    "I am M.A., a journalist from Eritrea.",
                ],
                "past_persecution": [
                    "In March 2023, four men in plain clothes detained me at my office.",
                ],
                "perpetrator_motivation": [
                    "They targeted me because of my reporting critical of the government.",
                ],
                "well_founded_fear_future": [
                    "I fear arrest and indefinite detention if I am returned.",
                ],
                "internal_relocation": [
                    "I cannot live safely elsewhere in Eritrea because of surveillance.",
                ],
                "filing_bar_facts": [
                    "I entered the United States in April 2023.",
                ],
            },
            gold_notes="PIR reference — Eritrean journalist canonical demo.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="ti-er-teacher-02",
            tags=["ti", "calibration", "er"],
            lang="ti",
            transcript=_transcript(
                "ti",
                [
                    ("ኣነ መምህር ነበርኩ", "I was a teacher in Asmara."),
                    (
                        "ኣብ 2022 ብሓደሮ ሰነይ ተኣሲረ",
                        "In June 2022 security agents detained me for refusing propaganda lessons.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "T.B. — Eritrea",
                "ER",
                "political_opinion",
                "Eritrean educators who resist state curriculum",
            ),
            gold_paragraphs={
                "identity_background": ["I am T.B., a teacher from Eritrea."],
                "past_persecution": [
                    "In June 2022, security agents detained me for refusing propaganda lessons.",
                ],
                "perpetrator_motivation": [
                    "They punished me because I refused to teach government propaganda.",
                ],
                "well_founded_fear_future": [
                    "I fear detention if returned because the state monitors educators.",
                ],
                "internal_relocation": [
                    "Relocation within Eritrea would not protect me from national surveillance.",
                ],
                "filing_bar_facts": ["I arrived in the United States in January 2024."],
            },
            gold_notes="PIR reference — Eritrean teacher political opinion.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="ti-er-conscript-03",
            tags=["ti", "calibration", "er"],
            lang="ti",
            transcript=_transcript(
                "ti",
                [
                    ("ካብ ምዕራፍ ስደት", "I fled indefinite national service."),
                    (
                        "ብሓደሮ ሰነይ 2021 ተሓዝኩ",
                        "In 2021 military police beat me when I tried to leave a camp.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "S.K. — Eritrea",
                "ER",
                "particular_social_group",
                "Eritreans who fled indefinite national service",
            ),
            gold_paragraphs={
                "identity_background": ["I am S.K. from Eritrea."],
                "past_persecution": [
                    "In 2021, military police beat me when I tried to leave a service camp.",
                ],
                "perpetrator_motivation": [
                    "They punished me for attempting to escape indefinite conscription.",
                ],
                "well_founded_fear_future": [
                    "I fear forced return to military service and punishment.",
                ],
                "internal_relocation": [
                    "There is no safe place in Eritrea outside state control.",
                ],
                "filing_bar_facts": ["I entered the United States in March 2022."],
            },
            gold_notes="PIR reference — Eritrean national service.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="es-mx-political-01",
            tags=["es", "calibration", "mx"],
            lang="es",
            transcript=_transcript(
                "es",
                [
                    ("Soy M.R. de Mexico", "I am M.R. from Mexico."),
                    (
                        "En 2023 amenazaron a mi familia",
                        "In 2023 local officials threatened my family after I reported corruption.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "M.R. — Mexico",
                "MX",
                "political_opinion",
                "Mexican community organizers opposing local corruption",
            ),
            gold_paragraphs={
                "identity_background": ["I am M.R. from Mexico."],
                "past_persecution": [
                    "In 2023, officials threatened my family after I reported corruption.",
                ],
                "perpetrator_motivation": [
                    "They targeted me for opposing corrupt local officials.",
                ],
                "well_founded_fear_future": [
                    "I fear violence if returned because those officials still control the area.",
                ],
                "internal_relocation": [
                    "Moving within Mexico would not protect my family from these officials.",
                ],
                "filing_bar_facts": ["I entered the United States in August 2023."],
            },
            gold_notes="PIR reference — Mexico political opinion.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="zh-cn-religious-01",
            tags=["zh", "calibration", "cn"],
            lang="zh",
            transcript=_transcript(
                "zh",
                [
                    ("我是来自中国的L.W.", "I am L.W. from China."),
                    (
                        "2022年因为家庭教会被拘留",
                        "In 2022 police detained me for attending a house church.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "L.W. — China",
                "CN",
                "religion",
                "Chinese Christians targeted for house church participation",
            ),
            gold_paragraphs={
                "identity_background": ["I am L.W. from China."],
                "past_persecution": [
                    "In 2022, police detained me for attending a house church.",
                ],
                "perpetrator_motivation": [
                    "They punished me because of my Christian faith outside state control.",
                ],
                "well_founded_fear_future": [
                    "I fear detention if returned for continuing religious practice.",
                ],
                "internal_relocation": [
                    "Police can locate house church members across provinces.",
                ],
                "filing_bar_facts": ["I entered the United States in June 2023."],
            },
            gold_notes="PIR reference — China religion.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="es-ve-gang-01",
            tags=["es", "ve"],
            lang="es",
            transcript=_transcript(
                "es",
                [
                    ("Soy de Venezuela", "I am from Venezuela."),
                    (
                        "Una pandilla exigio vacuna",
                        "A gang demanded extortion payments from my shop in 2023.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "C.P. — Venezuela",
                "VE",
                "particular_social_group",
                "Venezuelan small business owners targeted by gangs",
            ),
            gold_paragraphs={
                "identity_background": ["I am C.P. from Venezuela."],
                "past_persecution": [
                    "In 2023, a gang demanded extortion payments from my shop.",
                ],
                "perpetrator_motivation": [
                    "They targeted me as a shop owner who refused to pay.",
                ],
                "well_founded_fear_future": [
                    "I fear killing if returned because the gang controls my neighborhood.",
                ],
                "internal_relocation": [
                    "The gang operates across the city; relocation would not help.",
                ],
                "filing_bar_facts": ["I entered the United States in October 2023."],
            },
            gold_notes="PIR reference — Venezuela gang targeting.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="es-hn-gender-01",
            tags=["es", "hn"],
            lang="es",
            transcript=_transcript(
                "es",
                [
                    ("Soy de Honduras", "I am from Honduras."),
                    (
                        "Mi pareja me golpeo",
                        "My partner beat me and police refused to help in 2023.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "A.G. — Honduras",
                "HN",
                "particular_social_group",
                "Honduran women unable to obtain state protection from domestic violence",
            ),
            gold_paragraphs={
                "identity_background": ["I am A.G. from Honduras."],
                "past_persecution": [
                    "In 2023, my partner beat me and police refused to intervene.",
                ],
                "perpetrator_motivation": [
                    "He targeted me as a woman he controlled; authorities offered no protection.",
                ],
                "well_founded_fear_future": [
                    "I fear he will kill me if I am returned.",
                ],
                "internal_relocation": [
                    "He has family across the country and can find me.",
                ],
                "filing_bar_facts": ["I entered the United States in May 2023."],
            },
            gold_notes="PIR reference — Honduras gender-based harm.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="zh-cn-political-02",
            tags=["zh", "cn"],
            lang="zh",
            transcript=_transcript(
                "zh",
                [
                    ("我参与了对政府的抗议", "I joined protests against government policies."),
                    (
                        "2023年被国安约谈",
                        "In 2023 state security questioned me and warned me to stop.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "H.Z. — China",
                "CN",
                "political_opinion",
                "Chinese activists targeted after protest participation",
            ),
            gold_paragraphs={
                "identity_background": ["I am H.Z. from China."],
                "past_persecution": [
                    "In 2023, state security questioned me and warned me to stop protesting.",
                ],
                "perpetrator_motivation": [
                    "They targeted me for political opinions expressed in protests.",
                ],
                "well_founded_fear_future": [
                    "I fear detention if returned for continued dissent.",
                ],
                "internal_relocation": [
                    "National security can track activists across provinces.",
                ],
                "filing_bar_facts": ["I entered the United States in April 2024."],
            },
            gold_notes="PIR reference — China political opinion.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="zh-tw-cf-prior-01",
            tags=["zh", "tw"],
            lang="zh",
            transcript=_transcript(
                "zh",
                [
                    ("我来自台湾", "I am from Taiwan."),
                    (
                        "2024年3月有两名男子威胁我",
                        "In March 2024 two men threatened me at my workplace.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "K.L. — Taiwan",
                "TW",
                "political_opinion",
                "Taiwanese civil society members threatened for activism",
            ),
            prior_statements=[
                {
                    "id": "cccccccc-cccc-dddd-eeee-ffffffff0002",
                    "statement_type": "credible_fear_interview",
                    "source_language": "zh",
                    "source_text": "2024年1月有三个人",
                    "english_text": (
                        "In January 2024 three men threatened me at my workplace."
                    ),
                },
            ],
            gold_paragraphs={
                "identity_background": ["I am K.L. from Taiwan."],
                "past_persecution": [
                    "In March 2024, two men threatened me at my workplace.",
                ],
                "perpetrator_motivation": [
                    "They targeted me because of my political activism.",
                ],
                "well_founded_fear_future": [
                    "I fear further threats if returned.",
                ],
                "internal_relocation": [
                    "The same networks operate in other cities.",
                ],
                "filing_bar_facts": ["I entered the United States in June 2024."],
            },
            gold_notes="PIR reference — Taiwan with prior statement inconsistency.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="fr-cm-francophone-01",
            tags=["fr", "cm"],
            lang="fr",
            transcript=_transcript(
                "fr",
                [
                    ("Je suis du Cameroun", "I am from Cameroon."),
                    (
                        "En 2023 les forces gouvernementales ont attaque mon quartier",
                        "In 2023 government forces attacked my neighborhood.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "P.N. — Cameroon",
                "CM",
                "political_opinion",
                "Cameroonian francophone activists targeted by government forces",
            ),
            gold_paragraphs={
                "identity_background": ["I am P.N. from Cameroon."],
                "past_persecution": [
                    "In 2023, government forces attacked my neighborhood.",
                ],
                "perpetrator_motivation": [
                    "They targeted supporters of the opposition in my area.",
                ],
                "well_founded_fear_future": [
                    "I fear arrest if returned for my political activities.",
                ],
                "internal_relocation": [
                    "Government forces operate nationwide.",
                ],
                "filing_bar_facts": ["I entered the United States in February 2024."],
            },
            gold_notes="PIR reference — Cameroon francophone.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="fr-ht-political-01",
            tags=["fr", "ht"],
            lang="fr",
            transcript=_transcript(
                "fr",
                [
                    ("Je suis de Haiti", "I am from Haiti."),
                    (
                        "En 2024 des hommes armes ont cherche ma famille",
                        "In 2024 armed men searched for my family because of my activism.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "J.D. — Haiti",
                "HT",
                "political_opinion",
                "Haitian community organizers targeted by armed groups",
            ),
            gold_paragraphs={
                "identity_background": ["I am J.D. from Haiti."],
                "past_persecution": [
                    "In 2024, armed men searched for my family because of my activism.",
                ],
                "perpetrator_motivation": [
                    "They targeted me for organizing against local armed control.",
                ],
                "well_founded_fear_future": [
                    "I fear killing if returned.",
                ],
                "internal_relocation": [
                    "Armed groups control movement across Port-au-Prince.",
                ],
                "filing_bar_facts": ["I entered the United States in July 2024."],
            },
            gold_notes="PIR reference — Haiti political French.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="ht-gang-01",
            tags=["ht", "ht"],
            lang="ht",
            transcript=_transcript(
                "ht",
                [
                    ("Mwen soti Ayiti", "I am from Haiti."),
                    (
                        "Yon gang te fe m peye",
                        "A gang forced me to pay them money in 2023.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "R.M. — Haiti",
                "HT",
                "particular_social_group",
                "Haitians targeted by gangs for refusing extortion",
            ),
            gold_paragraphs={
                "identity_background": ["I am R.M. from Haiti."],
                "past_persecution": [
                    "In 2023, a gang forced me to pay extortion money.",
                ],
                "perpetrator_motivation": [
                    "They targeted me for refusing to continue payments.",
                ],
                "well_founded_fear_future": [
                    "I fear the gang will kill me if I return.",
                ],
                "internal_relocation": [
                    "The gang controls my neighborhood.",
                ],
                "filing_bar_facts": ["I entered the United States in September 2023."],
            },
            gold_notes="PIR reference — Haiti Creole gang.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="ht-political-02",
            tags=["ht", "ht"],
            lang="ht",
            transcript=_transcript(
                "ht",
                [
                    ("Mwen te pwoteje vwazen yo", "I helped neighbors escape violence."),
                    (
                        "Gang yo te menase m",
                        "Gangs threatened me in 2024 for helping neighbors.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "N.S. — Haiti",
                "HT",
                "political_opinion",
                "Haitians targeted for resisting gang control in their community",
            ),
            gold_paragraphs={
                "identity_background": ["I am N.S. from Haiti."],
                "past_persecution": [
                    "In 2024, gangs threatened me for helping neighbors escape violence.",
                ],
                "perpetrator_motivation": [
                    "They targeted me for resisting their control.",
                ],
                "well_founded_fear_future": [
                    "I fear retaliation if returned.",
                ],
                "internal_relocation": [
                    "Gangs operate throughout the capital.",
                ],
                "filing_bar_facts": ["I entered the United States in March 2024."],
            },
            gold_notes="PIR reference — Haiti Creole political.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="prs-af-taliban-01",
            tags=["prs", "af"],
            lang="prs",
            transcript=_transcript(
                "prs",
                [
                    ("من از افغانستان هستم", "I am from Afghanistan."),
                    (
                        "طالبان مرا تهدید کردند",
                        "The Taliban threatened me in 2023 for working with a NGO.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "F.H. — Afghanistan",
                "AF",
                "political_opinion",
                "Afghans targeted by the Taliban for NGO affiliation",
            ),
            gold_paragraphs={
                "identity_background": ["I am F.H. from Afghanistan."],
                "past_persecution": [
                    "In 2023, the Taliban threatened me for working with an NGO.",
                ],
                "perpetrator_motivation": [
                    "They targeted me for perceived opposition to their rule.",
                ],
                "well_founded_fear_future": [
                    "I fear detention or execution if returned.",
                ],
                "internal_relocation": [
                    "The Taliban controls the country.",
                ],
                "filing_bar_facts": ["I entered the United States in January 2024."],
            },
            gold_notes="PIR reference — Afghanistan Taliban.",
        ),
    )

    fixtures.append(
        _fixture(
            fixture_id="prs-af-interpreter-01",
            tags=["prs", "af"],
            lang="prs",
            transcript=_transcript(
                "prs",
                [
                    ("من مترجم بودم", "I was an interpreter for foreign forces."),
                    (
                        "طالبان به دنبال مترجمین است",
                        "The Taliban searches for former interpreters.",
                    ),
                ],
            ),
            case_metadata=_meta(
                "W.A. — Afghanistan",
                "AF",
                "particular_social_group",
                "Afghans who interpreted for foreign military forces",
            ),
            prior_statements=[
                {
                    "id": "dddddddd-dddd-eeee-ffff-000000000003",
                    "statement_type": "airport_statement",
                    "source_language": "prs",
                    "source_text": "من کارگر بودم",
                    "english_text": "I said I was a laborer at the airport interview.",
                },
            ],
            gold_paragraphs={
                "identity_background": [
                    "I am W.A. from Afghanistan. I was an interpreter for foreign forces.",
                ],
                "past_persecution": [
                    "After the Taliban returned, they searched for former interpreters.",
                ],
                "perpetrator_motivation": [
                    "They target interpreters as collaborators.",
                ],
                "well_founded_fear_future": [
                    "I fear execution if returned.",
                ],
                "internal_relocation": [
                    "The Taliban operates nationwide.",
                ],
                "filing_bar_facts": ["I entered the United States in August 2021."],
            },
            gold_notes="PIR reference — Afghanistan interpreter with prior statement.",
        ),
    )

    return fixtures


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    for fx in _all_fixtures():
        path = _OUT_DIR / f"{fx['id']}.json"
        path.write_text(
            json.dumps(fx, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
