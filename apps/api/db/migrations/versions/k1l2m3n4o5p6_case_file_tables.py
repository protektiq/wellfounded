"""cases, case_assignments, case_artifacts

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-05-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, None] = "j0k1l2m3n4o5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    claimbasis = postgresql.ENUM(
        "political_opinion",
        "religion",
        "particular_social_group",
        "gender_based",
        "race",
        "nationality",
        "mixed",
        name="claimbasis",
        create_type=True,
    )
    caseassignmentrole = postgresql.ENUM(
        "lead_attorney",
        "supporting_attorney",
        "paralegal",
        "supervised_student",
        name="caseassignmentrole",
        create_type=True,
    )
    caseartifacttype = postgresql.ENUM(
        "country_conditions_memo",
        "declaration_draft",
        "uploaded_file",
        "interview_audio",
        "transcript",
        name="caseartifacttype",
        create_type=True,
    )
    asylumoffice = postgresql.ENUM(
        "arlington",
        "atlanta",
        "boston",
        "chicago",
        "houston",
        "los_angeles",
        "miami",
        "newark",
        "new_york",
        "new_orleans",
        "philadelphia",
        "san_francisco",
        "seattle",
        name="asylumoffice",
        create_type=True,
    )
    claimbasis.create(bind, checkfirst=True)
    caseassignmentrole.create(bind, checkfirst=True)
    caseartifacttype.create(bind, checkfirst=True)
    asylumoffice.create(bind, checkfirst=True)

    claimbasis_type = postgresql.ENUM(
        "political_opinion",
        "religion",
        "particular_social_group",
        "gender_based",
        "race",
        "nationality",
        "mixed",
        name="claimbasis",
        create_type=False,
    )
    caseassignmentrole_type = postgresql.ENUM(
        "lead_attorney",
        "supporting_attorney",
        "paralegal",
        "supervised_student",
        name="caseassignmentrole",
        create_type=False,
    )
    caseartifacttype_type = postgresql.ENUM(
        "country_conditions_memo",
        "declaration_draft",
        "uploaded_file",
        "interview_audio",
        "transcript",
        name="caseartifacttype",
        create_type=False,
    )
    asylumoffice_type = postgresql.ENUM(
        "arlington",
        "atlanta",
        "boston",
        "chicago",
        "houston",
        "los_angeles",
        "miami",
        "newark",
        "new_york",
        "new_orleans",
        "philadelphia",
        "san_francisco",
        "seattle",
        name="asylumoffice",
        create_type=False,
    )

    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("pseudonym", sa.String(length=512), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("basis", claimbasis_type, nullable=False),
        sa.Column("group_description", sa.Text(), nullable=False),
        sa.Column("filing_deadline", sa.Date(), nullable=True),
        sa.Column("asylum_office", asylumoffice_type, nullable=True),
        sa.Column("intake_notes", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_cases_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_cases_created_by_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cases_organization_id", "cases", ["organization_id"], unique=False)
    op.create_index(
        "ix_cases_organization_id_deleted_at",
        "cases",
        ["organization_id", "deleted_at"],
        unique=False,
    )

    op.create_table(
        "case_assignments",
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("role_on_case", caseassignmentrole_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_case_assignments_case_id_cases",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_case_assignments_user_id_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("case_id", "user_id"),
    )
    op.create_index(
        "ix_case_assignments_user_id",
        "case_assignments",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "case_artifacts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("case_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("artifact_type", caseartifacttype_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["cases.id"],
            name="fk_case_artifacts_case_id_cases",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_case_artifacts_case_id", "case_artifacts", ["case_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_case_assignments_user_id", table_name="case_assignments")
    op.drop_index("ix_case_artifacts_case_id", table_name="case_artifacts")
    op.drop_table("case_artifacts")
    op.drop_table("case_assignments")
    op.drop_index("ix_cases_organization_id_deleted_at", table_name="cases")
    op.drop_index("ix_cases_organization_id", table_name="cases")
    op.drop_table("cases")

    op.execute(sa.text("DROP TYPE IF EXISTS caseartifacttype"))
    op.execute(sa.text("DROP TYPE IF EXISTS caseassignmentrole"))
    op.execute(sa.text("DROP TYPE IF EXISTS asylumoffice"))
    op.execute(sa.text("DROP TYPE IF EXISTS claimbasis"))
