"""ORM models for the global country-conditions source library."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class SourceFamily(str, enum.Enum):
    state_dept_human_rights = "state_dept_human_rights"
    uscirf = "uscirf"
    unhcr = "unhcr"
    hrc_upr = "hrc_upr"
    hrw = "hrw"
    amnesty = "amnesty"
    freedom_house = "freedom_house"
    cpj = "cpj"
    euaa_coi = "euaa_coi"
    academic = "academic"


class SourceDocument(Base):
    __tablename__ = "source_documents"
    __table_args__ = (
        Index("ix_source_documents_source_family", "source_family"),
        UniqueConstraint(
            "source_family",
            "content_hash",
            name="uq_source_documents_source_family_content_hash",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_family: Mapped[SourceFamily] = mapped_column(
        SAEnum(SourceFamily, name="sourcefamily", native_enum=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    publication_date: Mapped[date] = mapped_column(Date, nullable=False)
    country_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(2)),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    passages: Mapped[list[SourcePassage]] = relationship(
        "SourcePassage",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class SourcePassage(Base):
    __tablename__ = "source_passages"
    __table_args__ = (
        Index("ix_source_passages_source_document_id", "source_document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_anchor: Mapped[str] = mapped_column(String(1024), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(3072), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    document: Mapped[SourceDocument] = relationship(
        "SourceDocument",
        back_populates="passages",
    )
