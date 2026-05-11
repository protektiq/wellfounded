"""organizations and users tables

Revision ID: a1b2c3d4e5f6
Revises: cc18cd30d200
Create Date: 2026-05-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "cc18cd30d200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    userrole = postgresql.ENUM(
        "admin",
        "attorney",
        "paralegal",
        "student",
        name="userrole",
        create_type=True,
    )
    userstatus = postgresql.ENUM(
        "invited",
        "active",
        "suspended",
        name="userstatus",
        create_type=True,
    )
    userrole.create(bind, checkfirst=True)
    userstatus.create(bind, checkfirst=True)

    userrole_type = postgresql.ENUM(
        "admin",
        "attorney",
        "paralegal",
        "student",
        name="userrole",
        create_type=False,
    )
    userstatus_type = postgresql.ENUM(
        "invited",
        "active",
        "suspended",
        name="userstatus",
        create_type=False,
    )

    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kms_data_key_arn", sa.String(length=512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", userrole_type, nullable=False),
        sa.Column("status", userstatus_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_users_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_users_organization_id", "users", ["organization_id"], unique=False)
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_index(
        "uq_users_organization_id_email_active",
        "users",
        ["organization_id", "email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_users_organization_id_email_active",
        table_name="users",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")

    op.execute(sa.text("DROP TYPE IF EXISTS userstatus"))
    op.execute(sa.text("DROP TYPE IF EXISTS userrole"))
