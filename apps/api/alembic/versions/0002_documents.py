"""PHASE 2: documents and document_chunks.

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-11

Scope is ``docs/DATABASE.md`` §2.3. Same rules as the baseline: the cross-dialect type
decorators come from ``careerforge_api.db.compat``, and every ``CHECK`` is declared with
its **short** rule name so the naming convention produces the same
``ck_documents_kind_valid`` here as it does from the model. ``tests/test_migrations.py``
compares this migration's output to ``Base.metadata.create_all()`` column for column,
index for index, so the two cannot drift.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from careerforge_api.db.compat import JSONType, TimestampType, UUIDType

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_KINDS = "('resume','project_doc','interview_note','jd','notes')"
_STATUSES = "('pending','parsing','parsed','failed')"


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("parse_status", sa.Text(), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("is_redacted", sa.Boolean(), nullable=False),
        sa.Column("metadata", JSONType(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(f"kind IN {_KINDS}", name="kind_valid"),
        sa.CheckConstraint(f"parse_status IN {_STATUSES}", name="parse_status_valid"),
        sa.CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        sa.CheckConstraint("page_count IS NULL OR page_count >= 0", name="page_count_non_negative"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_documents_users_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        # Re-uploading identical bytes must not fork the evidence graph.
        sa.UniqueConstraint("user_id", "sha256", name="uq_documents_user_id_sha256"),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_user_id_created_at", "documents", ["user_id", "created_at"])

    op.create_table(
        "document_chunks",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("document_id", UUIDType(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.Text(), nullable=False),
        sa.Column("page_no", sa.Integer(), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        sa.CheckConstraint("token_count >= 0", name="token_count_non_negative"),
        sa.CheckConstraint("char_start >= 0 AND char_end >= char_start", name="char_range_valid"),
        sa.CheckConstraint("page_no IS NULL OR page_no >= 1", name="page_no_positive"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_document_chunks_documents_document_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_document_chunks_users_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_id"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_user_id", "document_chunks", ["user_id"])
    op.create_index(
        "ix_document_chunks_user_id_document_id_chunk_index",
        "document_chunks",
        ["user_id", "document_id", "chunk_index"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_chunks_user_id_document_id_chunk_index", table_name="document_chunks"
    )
    op.drop_index("ix_document_chunks_user_id", table_name="document_chunks")
    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_documents_user_id_created_at", table_name="documents")
    op.drop_index("ix_documents_user_id", table_name="documents")
    op.drop_table("documents")
