"""Generate short TTS audio fixtures for transcription tests (dev-only).

Requires network and gTTS: pip install gTTS

Usage (from apps/api):
  poetry run python -m scripts.generate_tts_fixtures
"""

from __future__ import annotations

import struct
import wave
from pathlib import Path

_OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "audio"

_PHRASES: dict[str, str] = {
    "es": "Tuve que huir de mi pais por persecucion politica.",
    "zh": "我因为政治迫害不得不离开我的国家。",
    "fr": "J'ai du fuir mon pays a cause de persecutions politiques.",
    "ht": "Mwen te oblije kouri kite peyi m akoz persekisyon politik.",
    "ti": "ብሰንኪ ፖለቲካዊ ምድራሽ ሃገረይ ክሰድድ ኣለኒ።",
    "prs": "من به دلیل آزار سیاسی مجبور شدم از کشورم فرار کنم.",
}


def _write_silence_wav(path: Path, seconds: float = 1.0) -> None:
    rate = 16000
    n = int(rate * seconds)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<h", 0) * n)


def main() -> None:
    try:
        from gtts import gTTS
    except ImportError:
        print("gTTS not installed; writing silence WAV placeholders")
        for lang in _PHRASES:
            _write_silence_wav(_OUT / f"{lang}.wav", seconds=2.0)
        return

    for lang, text in _PHRASES.items():
        out = _OUT / f"{lang}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        mp3_path = out.with_suffix(".mp3")
        gTTS(text=text, lang=lang if lang != "prs" else "fa").save(str(mp3_path))
        try:
            from mutagen.mp3 import MP3

            audio = MP3(mp3_path)
            # Convert via pydub if available; else keep mp3 renamed for manual conversion
            try:
                from pydub import AudioSegment

                seg = AudioSegment.from_mp3(mp3_path)
                seg.export(out, format="wav")
                mp3_path.unlink(missing_ok=True)
            except ImportError:
                print(f"Install pydub to convert {mp3_path} to WAV; kept MP3")
        except ImportError:
            print(f"mutagen missing; kept {mp3_path}")


if __name__ == "__main__":
    main()
