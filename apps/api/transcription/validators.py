"""Audio upload validation: format, size, duration."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

_MAX_BYTES = 200 * 1024 * 1024
_MAX_DURATION_SECONDS = 3600.0

_MAGIC: dict[str, tuple[bytes, ...]] = {
    "audio/wav": (b"RIFF",),
    "audio/mpeg": (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"ID3"),
    "audio/mp4": (b"\x00\x00\x00",),  # ftyp often at offset 4
    "audio/ogg": (b"OggS",),
}

_ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg"}


@dataclass(frozen=True)
class ValidatedAudio:
    content_type: str
    duration_seconds: float
    size_bytes: int


def _detect_format(header: bytes, filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        return None
    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WAVE":
        return "audio/wav"
    if header.startswith(b"ID3") or header[:2] in (
        b"\xff\xfb",
        b"\xff\xf3",
        b"\xff\xf2",
    ):
        return "audio/mpeg"
    if header.startswith(b"OggS"):
        return "audio/ogg"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "audio/mp4"
    if ext == ".wav":
        return "audio/wav"
    if ext == ".mp3":
        return "audio/mpeg"
    if ext == ".m4a":
        return "audio/mp4"
    if ext == ".ogg":
        return "audio/ogg"
    return None


def _wav_duration_seconds(path: Path) -> float | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    # fmt chunk at 12
    if data[12:16] != b"fmt ":
        return None
    fmt_size = struct.unpack("<I", data[16:20])[0]
    if len(data) < 20 + fmt_size + 8:
        return None
    offset = 20 + fmt_size
    if data[offset : offset + 4] != b"data":
        return None
    data_size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
    byte_rate = struct.unpack("<I", data[28:32])[0]
    if byte_rate == 0:
        return None
    return float(data_size) / float(byte_rate)


def _duration_from_mutagen(path: Path) -> float | None:
    try:
        from mutagen import File as MutagenFile  # type: ignore[attr-defined]
    except ImportError:
        return _wav_duration_seconds(path)
    audio = MutagenFile(path)
    if audio is None or audio.info is None:
        return _wav_duration_seconds(path)
    length = getattr(audio.info, "length", None)
    if length is None:
        return _wav_duration_seconds(path)
    return float(length)


def validate_audio_file(
    path: Path,
    *,
    filename: str,
    size_bytes: int,
) -> ValidatedAudio:
    if size_bytes > _MAX_BYTES:
        raise ValueError(f"Audio file exceeds maximum size of {_MAX_BYTES} bytes")
    if size_bytes < 16:
        raise ValueError("Audio file is too small")
    header = path.read_bytes()[:16]
    content_type = _detect_format(header, filename)
    if content_type is None:
        raise ValueError("Unsupported audio format; use WAV, MP3, M4A, or OGG")
    duration = _duration_from_mutagen(path)
    if duration is None or duration <= 0:
        raise ValueError("Could not determine audio duration")
    if duration > _MAX_DURATION_SECONDS:
        raise ValueError(
            f"Audio exceeds maximum duration of {_MAX_DURATION_SECONDS} seconds",
        )
    return ValidatedAudio(
        content_type=content_type,
        duration_seconds=duration,
        size_bytes=size_bytes,
    )
