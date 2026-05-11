"""audit_log_entries append-only table

Revision ID: f6e5d4c3b2a1
Revises: a1b2c3d4e5f6
Create Date: 2026-05-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6e5d4c3b2a1"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log_entries",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_audit_log_entries_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_audit_log_entries_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_log_entries_organization_id_created_at",
        "audit_log_entries",
        ["organization_id", "created_at"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION audit_log_entries_prevent_mutation()
            RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'audit_log_append_only';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER audit_log_entries_prevent_update
            BEFORE UPDATE ON audit_log_entries
            FOR EACH ROW
            EXECUTE FUNCTION audit_log_entries_prevent_mutation();
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER audit_log_entries_prevent_delete
            BEFORE DELETE ON audit_log_entries
            FOR EACH ROW
            EXECUTE FUNCTION audit_log_entries_prevent_mutation();
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DROP TRIGGER IF EXISTS audit_log_entries_prevent_delete ON audit_log_entries")
    )
    op.execute(
        sa.text("DROP TRIGGER IF EXISTS audit_log_entries_prevent_update ON audit_log_entries")
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS audit_log_entries_prevent_mutation()"))
    op.drop_index(
        "ix_audit_log_entries_organization_id_created_at",
        table_name="audit_log_entries",
    )
    op.drop_table("audit_log_entries")
