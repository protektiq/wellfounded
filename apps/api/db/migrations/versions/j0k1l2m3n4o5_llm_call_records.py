"""llm_call_records for LLM usage audit (hashed inputs only)

Revision ID: j0k1l2m3n4o5
Revises: i1j2k3l4m5n6
Create Date: 2026-05-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "j0k1l2m3n4o5"
down_revision: Union[str, None] = "i1j2k3l4m5n6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_call_records",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("prompt_id", sa.String(length=256), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column(
            "usage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_llm_call_records_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_llm_call_records_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_call_records_created_at",
        "llm_call_records",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_llm_call_records_organization_id_created_at",
        "llm_call_records",
        ["organization_id", "created_at"],
        unique=False,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llm_call_records_organization_id_created_at",
        table_name="llm_call_records",
    )
    op.drop_index(
        "ix_llm_call_records_created_at",
        table_name="llm_call_records",
    )
    op.drop_table("llm_call_records")
