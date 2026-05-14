"""Shared retrieval result types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
class RetrievedPassage:
    passage_id: UUID
    document_id: UUID
    source_family: str
    document_title: str
    publication_date: date
    url: str
    section_anchor: str
    text: str
    similarity_score: float
