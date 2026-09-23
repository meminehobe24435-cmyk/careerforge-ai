"""PHASE 6: resume versions, claims and the claim→evidence links.

Revision ID: 0006
Revises: 0005
Create Date: 2026-02-11

Scope is ``docs/DATABASE.md`` §2.9. Two deliberate omissions, both stated in the models:
``claim_validations`` (re-validation history) has no writer in this build — the verdict lives on
the claim row — and ``claim_evidence`` keeps no ``updated_at`` beyond the shared mixin because a
citation is immutable: re-validating a claim replaces its citations rather than editing one.

``resume_claims.resume_version_id`` is nullable on purpose, so the Validator page can store a
sentence that belongs to no version yet.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_STATUSES = "('pending','supported','partially_supported','unsupported','contradicted')"
_SECTIONS = "('summary','experience','project','skill','education')"
_CHANNELS = "('semantic','keyword','both','manual')"
_SOURCES = "('generated','uploaded','manual')"


def upgrade() -> None:
    op.create_table(
        "resume_versions",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("target_job_id", UUIDType(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("content_json", JSONType(), nullable=False),
        sa.Column("parent_version_id", UUIDType(), nullable=True),
        sa.Column("diff_summary", JSONType(), nullable=False),
        sa.Column("integrity_score", NumericType(4, 3), nullable=False),
        sa.Column("claim_stats", JSONType(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("integrity_score BETWEEN 0 AND 1", name="integrity_score_unit_range"),
        sa.CheckConstraint(f"source IN {_SOURCES}", name="source_valid"),
        sa.ForeignKeyConstraint(
            ["target_job_id"],
            ["jobs.id"],
            name="fk_resume_versions_jobs_target_job_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_resume_versions_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resume_versions"),
    )
    op.create_index("ix_resume_versions_user_id", "resume_versions", ["user_id"])
    op.create_index(
        "ix_resume_versions_user_id_created_at", "resume_versions", ["user_id", "created_at"]
    )

    op.create_table(
        "resume_claims",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("resume_version_id", UUIDType(), nullable=True),
        sa.Column("target_job_id", UUIDType(), nullable=True),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("confidence", NumericType(4, 3), nullable=False),
        sa.Column("safe_rewrite", sa.Text(), nullable=False),
        sa.Column("reasons", JSONType(), nullable=False),
        sa.Column("retrieval", JSONType(), nullable=False),
        sa.Column("has_quantified_claim", sa.Boolean(), nullable=False),
        sa.Column("independent_source_count", sa.Integer(), nullable=False),
        sa.Column("rule_version", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_unit_range"),
        sa.CheckConstraint(f"section IN {_SECTIONS}", name="section_valid"),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="status_valid"),
        sa.ForeignKeyConstraint(
            ["resume_version_id"],
            ["resume_versions.id"],
            name="fk_resume_claims_resume_versions_resume_version_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_job_id"],
            ["jobs.id"],
            name="fk_resume_claims_jobs_target_job_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_resume_claims_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_resume_claims"),
    )
    op.create_index("ix_resume_claims_resume_version_id", "resume_claims", ["resume_version_id"])
    op.create_index("ix_resume_claims_user_id", "resume_claims", ["user_id"])
    op.create_index("ix_resume_claims_user_id_status", "resume_claims", ["user_id", "status"])

    op.create_table(
        "claim_evidence",
        sa.Column("claim_id", UUIDType(), nullable=False),
        sa.Column("evidence_id", UUIDType(), nullable=False),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("relevance", NumericType(4, 3), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(f"channel IN {_CHANNELS}", name="channel_valid"),
        sa.CheckConstraint("rank >= 0", name="rank_non_negative"),
        sa.CheckConstraint("relevance BETWEEN 0 AND 1", name="relevance_unit_range"),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["resume_claims.id"],
            name="fk_claim_evidence_resume_claims_claim_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            name="fk_claim_evidence_evidence_evidence_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_claim_evidence_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claim_evidence"),
        sa.UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_claim_id"),
    )
    # No separate index on ``claim_id``: the unique constraint on (claim_id, evidence_id)
    # already serves claim→evidence lookups, and the model declares no such index.
    op.create_index("ix_claim_evidence_evidence_id", "claim_evidence", ["evidence_id"])
    op.create_index("ix_claim_evidence_user_id", "claim_evidence", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_claim_evidence_user_id", table_name="claim_evidence")
    op.drop_index("ix_claim_evidence_evidence_id", table_name="claim_evidence")
    op.drop_table("claim_evidence")
    op.drop_index("ix_resume_claims_user_id_status", table_name="resume_claims")
    op.drop_index("ix_resume_claims_user_id", table_name="resume_claims")
    op.drop_index("ix_resume_claims_resume_version_id", table_name="resume_claims")
    op.drop_table("resume_claims")
    op.drop_index("ix_resume_versions_user_id_created_at", table_name="resume_versions")
    op.drop_index("ix_resume_versions_user_id", table_name="resume_versions")
    op.drop_table("resume_versions")
