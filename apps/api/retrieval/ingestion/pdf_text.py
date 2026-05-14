"""Extract plain text from PDF bytes for ingestion pipelines."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader


def extract_pdf_text(raw: bytes) -> str:
    reader = PdfReader(BytesIO(raw))
    parts: list[str] = []
    for page in reader.pages:
        t = page.extract_text() or ""
        if t.strip():
            parts.append(t)
    return "\n\n".join(parts)
