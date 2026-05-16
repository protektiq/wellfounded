"""interview_audio and transcript pipeline status

Revision ID: o5p6q7r8s9t0
Revises: n3o4p5q6r7s8
Create Date: 2026-05-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "o5p6q7r8s9t0"
down_revision: Union[str, None] = "n3o4p5q6r7s8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "organizations",
        sa.Column("data_key_revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    transcriptionstatus = postgresql.ENUM(
        "pending",
        "processing",
        "complete",
        "failed",
        name="transcriptionstatus",
        create_type=True,
    )
    transcriptionstatus.create(bind, checkfirst=True)
    transcriptionstatus_type = postgresql.ENUM(
        "pending",
        "processing",
        "complete",
        "failed",
        name="transcriptionstatus",
        create_type=False,
    )

    transcriptstatus = postgresql.ENUM(
        "pending",
        "processing",
        "complete",
        "failed",
        name="transcriptstatus",
        create_type=True,
    )
    transcriptstatus.create(bind, checkfirst=True)
    transcriptstatus_type = postgresql.ENUM(
        "pending",
        "processing",
        "complete",
        "failed",
        name="transcriptstatus",
        create_type=False,
    )

    sourcelanguage_type = postgresql.ENUM(
        "es",
        "zh",
        "fr",
        "ht",
        "ti",
        "prs",
        name="sourcelanguage",
        create_type=False,
    )

    op.create_table(
        "interview_audio",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_artifact_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("source_language", sourcelanguage_type, nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("encryption_key_id", sa.String(length=512), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("transcription_status", transcriptionstatus_type, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("correlation_request_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["case_artifact_id"],
            ["case_artifacts.id"],
            name="fk_interview_audio_case_artifact_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_interview_audio_case_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_interview_audio_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_interview_audio_uploaded_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_audio_organization_id",
        "interview_audio",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_interview_audio_case_id",
        "interview_audio",
        ["case_id"],
        unique=False,
    )

    op.add_column(
        "transcripts",
        sa.Column(
            "status",
            transcriptstatus_type,
            nullable=False,
            server_default="complete",
        ),
    )
    op.alter_column("transcripts", "segments", nullable=True)
    op.alter_column("transcripts", "full_source_text", nullable=True)
    op.alter_column("transcripts", "full_english_text", nullable=True)
    op.alter_column("transcripts", "model_version", nullable=True)
    op.alter_column("transcripts", "completed_at", nullable=True)

    op.create_foreign_key(
        "fk_transcripts_interview_audio_id",
        "transcripts",
        "interview_audio",
        ["interview_audio_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_transcripts_interview_audio_id",
        "transcripts",
        type_="foreignkey",
    )
    op.alter_column("transcripts", "completed_at", nullable=False)
    op.alter_column("transcripts", "model_version", nullable=False)
    op.alter_column("transcripts", "full_english_text", nullable=False)
    op.alter_column("transcripts", "full_source_text", nullable=False)
    op.alter_column("transcripts", "segments", nullable=False)
    op.drop_column("transcripts", "status")

    op.drop_index("ix_interview_audio_case_id", table_name="interview_audio")
    op.drop_index(
        "ix_interview_audio_organization_id",
        table_name="interview_audio",
    )
    op.drop_table("interview_audio")

    op.drop_column("organizations", "data_key_revoked_at")

    bind = op.get_bind()
    postgresql.ENUM(name="transcriptstatus").drop(bind, checkfirst=True)
    postgresql.ENUM(name="transcriptionstatus").drop(bind, checkfirst=True)
