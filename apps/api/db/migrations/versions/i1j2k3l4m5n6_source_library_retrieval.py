"""source_documents, source_passages, pgvector HNSW on halfvec cast

Revision ID: i1j2k3l4m5n6
Revises: h2b3c4d5e6f7
Create Date: 2026-05-11

HNSW on plain vector(3072) exceeds pgvector's per-index dimension limit for
type vector; the ANN index uses halfvec(3072) via expression cast (pgvector
documented pattern for text-embedding-3-large-sized vectors).

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "i1j2k3l4m5n6"
down_revision: Union[str, None] = "h2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    bind = op.get_bind()
    sourcefamily = postgresql.ENUM(
        "state_dept_human_rights",
        "uscirf",
        "unhcr",
        "hrc_upr",
        "hrw",
        "amnesty",
        "freedom_house",
        "cpj",
        "euaa_coi",
        "academic",
        name="sourcefamily",
        create_type=True,
    )
    sourcefamily.create(bind, checkfirst=True)

    sourcefamily_type = postgresql.ENUM(
        "state_dept_human_rights",
        "uscirf",
        "unhcr",
        "hrc_upr",
        "hrw",
        "amnesty",
        "freedom_house",
        "cpj",
        "euaa_coi",
        "academic",
        name="sourcefamily",
        create_type=False,
    )

    op.create_table(
        "source_documents",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_family", sourcefamily_type, nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=False),
        sa.Column("country_codes", postgresql.ARRAY(sa.String(length=2)), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_family",
            "content_hash",
            name="uq_source_documents_source_family_content_hash",
        ),
    )
    op.create_index(
        "ix_source_documents_source_family",
        "source_documents",
        ["source_family"],
        unique=False,
    )

    op.create_table(
        "source_passages",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("source_document_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("section_anchor", sa.String(length=1024), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(3072), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["source_documents.id"],
            name="fk_source_passages_source_document_id_source_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_passages_source_document_id",
        "source_passages",
        ["source_document_id"],
        unique=False,
    )

    op.execute(
        sa.text(
            """
            CREATE INDEX ix_source_passages_embedding_hnsw
            ON source_passages
            USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """
        ),
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_source_passages_embedding_hnsw"))
    op.drop_index("ix_source_passages_source_document_id", table_name="source_passages")
    op.drop_table("source_passages")
    op.drop_index("ix_source_documents_source_family", table_name="source_documents")
    op.drop_table("source_documents")
    op.execute(sa.text("DROP TYPE IF EXISTS sourcefamily"))
