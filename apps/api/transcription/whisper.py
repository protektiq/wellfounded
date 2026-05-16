"""faster-whisper wrapper for interview transcription."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

_DEFAULT_SPEAKER = "Speaker 1"
_MODEL_SIZE = "large-v3"


@dataclass(frozen=True)
class WhisperSegment:
    start: float
    end: float
    text: str
    language: str
    avg_logprob: float


@dataclass(frozen=True)
class WhisperResult:
    segments: list[WhisperSegment]
    language: str
    language_probability: float
    model_version: str


@lru_cache(maxsize=1)
def _load_model() -> WhisperModel:
    from faster_whisper import WhisperModel

    return WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")


def transcribe_audio_file(path: Path) -> WhisperResult:
    model = _load_model()
    segments_iter, info = model.transcribe(
        str(path),
        vad_filter=True,
        word_timestamps=False,
    )
    segments: list[WhisperSegment] = []
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        segments.append(
            WhisperSegment(
                start=float(seg.start),
                end=float(seg.end),
                text=text,
                language=str(info.language or "unknown"),
                avg_logprob=float(seg.avg_logprob),
            ),
        )
    try:
        import faster_whisper

        version = getattr(faster_whisper, "__version__", "unknown")
    except ImportError:
        version = "unknown"
    model_version = f"whisper-{_MODEL_SIZE}@faster-whisper-{version}"
    return WhisperResult(
        segments=segments,
        language=str(info.language or "unknown"),
        language_probability=float(info.language_probability or 0.0),
        model_version=model_version,
    )


def whisper_segments_to_transcript_segments(
    whisper_segments: list[WhisperSegment],
    *,
    english_texts: list[str] | None = None,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for i, seg in enumerate(whisper_segments):
        english = (
            english_texts[i]
            if english_texts is not None and i < len(english_texts)
            else seg.text
        )
        out.append(
            {
                "start": seg.start,
                "end": seg.end,
                "speaker": _DEFAULT_SPEAKER,
                "source_text": seg.text,
                "english_text": english,
            },
        )
    return out
