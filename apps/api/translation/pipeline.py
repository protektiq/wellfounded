"""Orchestrate NLLB translation and LLM review per segment."""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from declarations.models import SourceLanguage
from transcription.whisper import WhisperSegment
from translation.nllb import translate_texts
from translation.review import review_translations


async def translate_whisper_segments(
    session: AsyncSession,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    whisper_segments: list[WhisperSegment],
    source_language: SourceLanguage,
) -> tuple[list[dict[str, object]], str]:
    source_texts = [s.text for s in whisper_segments]
    nllb_english, nllb_version = translate_texts(source_texts, source_language)
    payload_segments = [
        {
            "source_text": src,
            "nllb_english": eng,
        }
        for src, eng in zip(source_texts, nllb_english, strict=True)
    ]
    reviewed, review_version = await review_translations(
        session,
        organization_id,
        user_id,
        source_language=source_language.value,
        segments_json=json.dumps(payload_segments, ensure_ascii=False),
    )
    if len(reviewed) != len(whisper_segments):
        raise ValueError("translation review returned wrong segment count")
    model_version = f"{nllb_version};{review_version}"
    out: list[dict[str, object]] = []
    for seg, eng in zip(whisper_segments, reviewed, strict=True):
        out.append(
            {
                "start": seg.start,
                "end": seg.end,
                "speaker": "Speaker 1",
                "source_text": seg.text,
                "english_text": eng,
            },
        )
    return out, model_version
