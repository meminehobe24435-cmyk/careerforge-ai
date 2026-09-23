"""PHASE 3: evidence and evidence_links.

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-11

Scope is ``docs/DATABASE.md`` §2.5. The one part worth reading closely is the confidence
``CHECK``: it pins ``confidence`` to the five stored factors, so the number the UI shows
can be recomputed from the row itself. The expression is written with ``CASE`` instead of
PostgreSQL's ``least()`` (which ``docs/DATABASE.md`` §3 shows) because SQLite spells the
scalar two-argument form ``min()`` — and this constraint has to mean the same thing on
both backends (ADR-004).

``repo_file_id`` / ``repo_commit_id`` are deliberately absent: they reference §2.4 tables
that do not exist yet. A column whose foreign key points at a missing table cannot be
created, and one without its key would accept dangling ids.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType
from careerforge_api.models.evidence import confidence_formula_sql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_KINDS = (
    "('repo_file','commit','readme','document_chunk','experience','project',"
    "'achievement','manual','llm_inference')"
)
_RELATIONS = (
    "('HAS','DEMONSTRATES','EVIDENCED_BY','SUPPORTS','REQUIRES','MATCHES','GAP','DERIVED_FROM')"
)

_UNIT_COLUMNS = ("source_authority", "specificity", "extraction_quality", "recency_score")

#: The five scored columns are declared in the documented order: the four independent
#: factors, then corroboration, then the score they produce (``docs/DATABASE.md`` §3).
#: Column order is part of the model/migration equivalence the test suite asserts, so it
#: is written out explicitly rather than generated.
_FACTOR_COLUMNS = (
    *[sa.Column(column, NumericType(4, 3), nullable=False) for column in _UNIT_COLUMNS],
    sa.Column("corroboration_count", sa.Integer(), nullable=False),
    sa.Column("confidence", NumericType(4, 3), nullable=False),
)


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("locator", JSONType(), nullable=False),
        *_FACTOR_COLUMNS,
        sa.Column("occurred_at", TimestampType(), nullable=True),
        sa.Column("document_chunk_id", UUIDType(), nullable=True),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("metadata", JSONType(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(f"kind IN {_KINDS}", name="kind_valid"),
        sa.CheckConstraint("corroboration_count >= 0", name="corroboration_non_negative"),
        *[
            sa.CheckConstraint(f"{column} BETWEEN 0 AND 1", name=f"{column}_unit_range")
            for column in (*_UNIT_COLUMNS, "confidence")
        ],
        sa.CheckConstraint(
            "abs(confidence - (" + confidence_formula_sql() + ")) < 0.002",
            name="confidence_formula",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_evidence_users_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_chunk_id"],
            ["document_chunks.id"],
            name="fk_evidence_document_chunks_document_chunk_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence"),
        sa.UniqueConstraint("user_id", "kind", "content_hash", name="uq_evidence_user_id"),
    )
    op.create_index("ix_evidence_user_id", "evidence", ["user_id"])
    op.create_index("ix_evidence_user_id_kind", "evidence", ["user_id", "kind"])
    op.create_index("ix_evidence_user_id_confidence", "evidence", ["user_id", "confidence"])
    op.create_index("ix_evidence_user_id_occurred_at", "evidence", ["user_id", "occurred_at"])

    op.create_table(
        "evidence_links",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("from_type", sa.Text(), nullable=False),
        sa.Column("from_id", UUIDType(), nullable=False),
        sa.Column("to_type", sa.Text(), nullable=False),
        sa.Column("to_id", UUIDType(), nullable=False),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("weight", NumericType(4, 3), nullable=False),
        sa.Column("confidence", NumericType(4, 3), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(f"relation IN {_RELATIONS}", name="relation_valid"),
        sa.CheckConstraint("weight BETWEEN 0 AND 1", name="weight_unit_range"),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_unit_range"
        ),
        sa.CheckConstraint("from_id <> to_id", name="no_self_loops"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_evidence_links_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_links"),
        sa.UniqueConstraint(
            "user_id",
            "from_type",
            "from_id",
            "to_type",
            "to_id",
            "relation",
            name="uq_evidence_links_user_id",
        ),
    )
    op.create_index("ix_evidence_links_user_id", "evidence_links", ["user_id"])
    op.create_index(
        "ix_evidence_links_user_id_from", "evidence_links", ["user_id", "from_type", "from_id"]
    )
    op.create_index(
        "ix_evidence_links_user_id_to", "evidence_links", ["user_id", "to_type", "to_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_links_user_id_to", table_name="evidence_links")
    op.drop_index("ix_evidence_links_user_id_from", table_name="evidence_links")
    op.drop_index("ix_evidence_links_user_id", table_name="evidence_links")
    op.drop_table("evidence_links")
    op.drop_index("ix_evidence_user_id_occurred_at", table_name="evidence")
    op.drop_index("ix_evidence_user_id_confidence", table_name="evidence")
    op.drop_index("ix_evidence_user_id_kind", table_name="evidence")
    op.drop_index("ix_evidence_user_id", table_name="evidence")
    op.drop_table("evidence")
