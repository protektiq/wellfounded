"""WebAuthn credentials, challenges, and session MFA timestamp

Revision ID: h2b3c4d5e6f7
Revises: g7h8i9j0k1l2
Create Date: 2026-05-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "h2b3c4d5e6f7"
down_revision: Union[str, None] = "g7h8i9j0k1l2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    purpose_enum = postgresql.ENUM(
        "registration",
        "authentication",
        name="webauthnchallengepurpose",
        create_type=True,
    )
    purpose_enum.create(bind, checkfirst=True)
    purpose_type = postgresql.ENUM(
        "registration",
        "authentication",
        name="webauthnchallengepurpose",
        create_type=False,
    )

    op.add_column(
        "sessions",
        sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "webauthn_credentials",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("transports", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("friendly_name", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_webauthn_credentials_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_webauthn_credentials_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "credential_id",
            name="uq_webauthn_credentials_credential_id",
        ),
    )
    op.create_index(
        "ix_webauthn_credentials_organization_id",
        "webauthn_credentials",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_webauthn_credentials_organization_id_user_id",
        "webauthn_credentials",
        ["organization_id", "user_id"],
        unique=False,
    )

    op.create_table(
        "webauthn_challenges",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("purpose", purpose_type, nullable=False),
        sa.Column("challenge", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_webauthn_challenges_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_webauthn_challenges_session_id_sessions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webauthn_challenges_organization_id_session_id_purpose",
        "webauthn_challenges",
        ["organization_id", "session_id", "purpose"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_webauthn_challenges_organization_id_session_id_purpose",
        table_name="webauthn_challenges",
    )
    op.drop_table("webauthn_challenges")

    op.drop_index(
        "ix_webauthn_credentials_organization_id_user_id",
        table_name="webauthn_credentials",
    )
    op.drop_index(
        "ix_webauthn_credentials_organization_id",
        table_name="webauthn_credentials",
    )
    op.drop_table("webauthn_credentials")

    op.drop_column("sessions", "mfa_verified_at")

    purpose_enum = postgresql.ENUM(
        "registration",
        "authentication",
        name="webauthnchallengepurpose",
        create_type=False,
    )
    purpose_enum.drop(op.get_bind(), checkfirst=True)
