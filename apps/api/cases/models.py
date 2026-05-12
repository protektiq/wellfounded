"""SQLAlchemy models for case files, assignments, and artifact stubs."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class ClaimBasis(str, enum.Enum):
    political_opinion = "political_opinion"
    religion = "religion"
    particular_social_group = "particular_social_group"
    gender_based = "gender_based"
    race = "race"
    nationality = "nationality"
    mixed = "mixed"


class CaseAssignmentRole(str, enum.Enum):
    lead_attorney = "lead_attorney"
    supporting_attorney = "supporting_attorney"
    paralegal = "paralegal"
    supervised_student = "supervised_student"


class CaseArtifactType(str, enum.Enum):
    country_conditions_memo = "country_conditions_memo"
    declaration_draft = "declaration_draft"
    uploaded_file = "uploaded_file"
    interview_audio = "interview_audio"
    transcript = "transcript"


class CaseQueryStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    deleted = "deleted"
    all = "all"


class AsylumOffice(str, enum.Enum):
    arlington = "arlington"
    atlanta = "atlanta"
    boston = "boston"
    chicago = "chicago"
    houston = "houston"
    los_angeles = "los_angeles"
    miami = "miami"
    newark = "newark"
    new_york = "new_york"
    new_orleans = "new_orleans"
    philadelphia = "philadelphia"
    san_francisco = "san_francisco"
    seattle = "seattle"


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_organization_id", "organization_id"),
        Index("ix_cases_organization_id_deleted_at", "organization_id", "deleted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pseudonym: Mapped[str] = mapped_column(String(512), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    basis: Mapped[ClaimBasis] = mapped_column(
        SAEnum(ClaimBasis, name="claimbasis", native_enum=True),
        nullable=False,
    )
    group_description: Mapped[str] = mapped_column(Text, nullable=False)
    filing_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    asylum_office: Mapped[AsylumOffice | None] = mapped_column(
        SAEnum(AsylumOffice, name="asylumoffice", native_enum=True),
        nullable=True,
    )
    intake_notes: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    assignments: Mapped[list[CaseAssignment]] = relationship(
        "CaseAssignment",
        back_populates="case",
        cascade="all, delete-orphan",
    )
    artifacts: Mapped[list[CaseArtifact]] = relationship(
        "CaseArtifact",
        back_populates="case",
        cascade="all, delete-orphan",
    )


class CaseAssignment(Base):
    __tablename__ = "case_assignments"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role_on_case: Mapped[CaseAssignmentRole] = mapped_column(
        SAEnum(CaseAssignmentRole, name="caseassignmentrole", native_enum=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    case: Mapped[Case] = relationship("Case", back_populates="assignments")


class CaseArtifact(Base):
    __tablename__ = "case_artifacts"
    __table_args__ = (Index("ix_case_artifacts_case_id", "case_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[CaseArtifactType] = mapped_column(
        SAEnum(CaseArtifactType, name="caseartifacttype", native_enum=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    case: Mapped[Case] = relationship("Case", back_populates="artifacts")
