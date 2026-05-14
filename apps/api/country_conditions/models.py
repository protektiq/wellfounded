"""ORM for country conditions memo artifacts."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, Uuid, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class CountryConditionsMemoStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    complete = "complete"
    failed = "failed"


class CountryConditionsMemo(Base):
    __tablename__ = "country_conditions_memos"
    __table_args__ = (
        Index("ix_country_conditions_memos_organization_id", "organization_id"),
        Index("ix_country_conditions_memos_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    case_artifact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("case_artifacts.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[CountryConditionsMemoStatus] = mapped_column(
        SAEnum(
            CountryConditionsMemoStatus,
            name="countryconditionsmemostatus",
            native_enum=True,
        ),
        nullable=False,
    )
    inputs: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    model_versions: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
