"""country_conditions_memos

Revision ID: m1n2o3p4q5r6
Revises: k1l2m3n4o5p6
Create Date: 2026-05-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    memostatus = postgresql.ENUM(
        "pending",
        "generating",
        "complete",
        "failed",
        name="countryconditionsmemostatus",
        create_type=True,
    )
    memostatus.create(bind, checkfirst=True)

    memostatus_type = postgresql.ENUM(
        "pending",
        "generating",
        "complete",
        "failed",
        name="countryconditionsmemostatus",
        create_type=False,
    )

    op.create_table(
        "country_conditions_memos",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_artifact_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("status", memostatus_type, nullable=False),
        sa.Column("inputs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("generated_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
            name="fk_country_conditions_memos_case_artifact_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_country_conditions_memos_case_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["generated_by_user_id"],
            ["users.id"],
            name="fk_country_conditions_memos_generated_by_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_country_conditions_memos_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "case_id",
            "version",
            name="uq_country_conditions_memos_org_case_version",
        ),
    )
    op.create_index(
        "ix_country_conditions_memos_organization_id",
        "country_conditions_memos",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_country_conditions_memos_case_id",
        "country_conditions_memos",
        ["case_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_country_conditions_memos_case_id",
        table_name="country_conditions_memos",
    )
    op.drop_index(
        "ix_country_conditions_memos_organization_id",
        table_name="country_conditions_memos",
    )
    op.drop_table("country_conditions_memos")
    memostatus = postgresql.ENUM(name="countryconditionsmemostatus")
    memostatus.drop(op.get_bind(), checkfirst=True)
