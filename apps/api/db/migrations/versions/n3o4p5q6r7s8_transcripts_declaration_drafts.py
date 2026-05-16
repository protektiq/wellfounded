"""transcripts prior_statements declaration_drafts

Revision ID: n3o4p5q6r7s8
Revises: m1n2o3p4q5r6
Create Date: 2026-05-16

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "n3o4p5q6r7s8"
down_revision: Union[str, None] = "m1n2o3p4q5r6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    sourcelanguage = postgresql.ENUM(
        "es",
        "zh",
        "fr",
        "ht",
        "ti",
        "prs",
        name="sourcelanguage",
        create_type=True,
    )
    sourcelanguage.create(bind, checkfirst=True)
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

    priorstatementtype = postgresql.ENUM(
        "credible_fear_interview",
        "airport_statement",
        "prior_filing",
        name="priorstatementtype",
        create_type=True,
    )
    priorstatementtype.create(bind, checkfirst=True)
    priorstatementtype_type = postgresql.ENUM(
        "credible_fear_interview",
        "airport_statement",
        "prior_filing",
        name="priorstatementtype",
        create_type=False,
    )

    declarationdraftstatus = postgresql.ENUM(
        "pending",
        "generating",
        "draft_ready",
        "flags_unresolved",
        "ready_for_review",
        "finalized",
        "failed",
        name="declarationdraftstatus",
        create_type=True,
    )
    declarationdraftstatus.create(bind, checkfirst=True)
    draftstatus_type = postgresql.ENUM(
        "pending",
        "generating",
        "draft_ready",
        "flags_unresolved",
        "ready_for_review",
        "finalized",
        "failed",
        name="declarationdraftstatus",
        create_type=False,
    )

    op.create_table(
        "transcripts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_artifact_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("interview_audio_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("source_language", sourcelanguage_type, nullable=False),
        sa.Column(
            "segments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("full_source_text", sa.Text(), nullable=False),
        sa.Column("full_english_text", sa.Text(), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_artifact_id"],
            ["case_artifacts.id"],
            name="fk_transcripts_case_artifact_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_transcripts_case_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_transcripts_created_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_transcripts_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transcripts_organization_id",
        "transcripts",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_transcripts_case_id",
        "transcripts",
        ["case_id"],
        unique=False,
    )

    op.create_table(
        "prior_statements",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_artifact_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("statement_type", priorstatementtype_type, nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("english_text", sa.Text(), nullable=False),
        sa.Column("source_language", sourcelanguage_type, nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_artifact_id"],
            ["case_artifacts.id"],
            name="fk_prior_statements_case_artifact_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_prior_statements_case_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_prior_statements_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            name="fk_prior_statements_uploaded_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prior_statements_organization_id",
        "prior_statements",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_prior_statements_case_id",
        "prior_statements",
        ["case_id"],
        unique=False,
    )

    op.create_table(
        "declaration_drafts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_artifact_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("transcript_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("interview_audio_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", draftstatus_type, nullable=False),
        sa.Column("draft", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "flags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "prior_statement_ids",
            postgresql.ARRAY(sa.Uuid(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("claim_ir", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "model_versions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("correlation_request_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["case_artifact_id"],
            ["case_artifacts.id"],
            name="fk_declaration_drafts_case_artifact_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_declaration_drafts_case_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_declaration_drafts_created_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_declaration_drafts_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["transcript_id"],
            ["transcripts.id"],
            name="fk_declaration_drafts_transcript_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "case_id",
            "version",
            name="uq_declaration_drafts_org_case_version",
        ),
    )
    op.create_index(
        "ix_declaration_drafts_organization_id",
        "declaration_drafts",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_declaration_drafts_case_id",
        "declaration_drafts",
        ["case_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_declaration_drafts_case_id", table_name="declaration_drafts")
    op.drop_index(
        "ix_declaration_drafts_organization_id",
        table_name="declaration_drafts",
    )
    op.drop_table("declaration_drafts")
    op.drop_index("ix_prior_statements_case_id", table_name="prior_statements")
    op.drop_index(
        "ix_prior_statements_organization_id",
        table_name="prior_statements",
    )
    op.drop_table("prior_statements")
    op.drop_index("ix_transcripts_case_id", table_name="transcripts")
    op.drop_index("ix_transcripts_organization_id", table_name="transcripts")
    op.drop_table("transcripts")

    bind = op.get_bind()
    postgresql.ENUM(name="declarationdraftstatus").drop(bind, checkfirst=True)
    postgresql.ENUM(name="priorstatementtype").drop(bind, checkfirst=True)
    postgresql.ENUM(name="sourcelanguage").drop(bind, checkfirst=True)
