"""PHASE 4: jobs, job_skills and job_matches.

Revision ID: 0004
Revises: 0003
Create Date: 2026-02-11

Scope is ``docs/DATABASE.md`` §2.6, with one documented deviation: ``user_id`` is NOT NULL,
because this build has no public job library yet and a nullable tenant key makes every read
harder to reason about. Relaxing it later is a one-line ``ALTER COLUMN DROP NOT NULL``.
``company_id`` is likewise absent — its ``companies`` table arrives with the feature that
needs a shared company directory, and a foreign key to a missing table cannot be created.

``job_skills`` carries a generated-in-application ``dedupe_key`` (canonical id, or the raw
text when the taxonomy could not normalise it) because the documented uniqueness is over a
**nullable** column, and ``NULL`` never compares equal in a unique index on either backend:
the constraint would silently stop working for exactly the unmatched skills.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_REMOTE_TYPES = "('onsite','hybrid','remote')"
_SOURCES = "('paste','upload','url','manual')"
_PARSE_STATUSES = "('pending','parsed','heuristic_fallback','failed')"
_LEVELS = "('intern','junior','mid','senior','lead')"
_REQUIREMENTS = "('required','preferred','bonus')"


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("company_name_raw", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("level", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("remote_type", sa.Text(), nullable=True),
        sa.Column("employment_type", sa.Text(), nullable=True),
        sa.Column("salary_min", NumericType(10, 2), nullable=True),
        sa.Column("salary_max", NumericType(10, 2), nullable=True),
        sa.Column("salary_currency", sa.Text(), nullable=True),
        sa.Column("education_requirement", sa.Text(), nullable=True),
        sa.Column("years_experience_min", NumericType(4, 1), nullable=True),
        sa.Column("description_raw", sa.Text(), nullable=False),
        sa.Column("description_sha256", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("analysis", JSONType(), nullable=False),
        sa.Column("responsibilities", JSONType(), nullable=False),
        sa.Column("nice_to_have", JSONType(), nullable=False),
        sa.Column("keywords", JSONType(), nullable=False),
        sa.Column("parse_status", sa.Text(), nullable=False),
        sa.Column("parse_confidence", NumericType(4, 3), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("parse_confidence BETWEEN 0 AND 1", name="parse_confidence_unit_range"),
        sa.CheckConstraint(
            "years_experience_min IS NULL OR years_experience_min BETWEEN 0 AND 50",
            name="years_experience_range",
        ),
        sa.CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="salary_range_ordered",
        ),
        sa.CheckConstraint(f"remote_type IN {_REMOTE_TYPES}", name="remote_type_valid"),
        sa.CheckConstraint(f"source IN {_SOURCES}", name="source_valid"),
        sa.CheckConstraint(f"parse_status IN {_PARSE_STATUSES}", name="parse_status_valid"),
        sa.CheckConstraint(f"level IN {_LEVELS}", name="level_valid"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_jobs_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("user_id", "description_sha256", name="uq_jobs_user_id"),
    )
    op.create_index("ix_jobs_user_id", "jobs", ["user_id"])
    op.create_index("ix_jobs_user_id_created_at", "jobs", ["user_id", "created_at"])

    op.create_table(
        "job_skills",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("job_id", UUIDType(), nullable=False),
        sa.Column("canonical_id", sa.Text(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("requirement", sa.Text(), nullable=False),
        sa.Column("weight", NumericType(4, 3), nullable=False),
        sa.Column("jd_evidence", sa.Text(), nullable=False),
        sa.Column("mentions", sa.Integer(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("weight BETWEEN 0 AND 1", name="weight_unit_range"),
        sa.CheckConstraint("mentions >= 1", name="mentions_positive"),
        sa.CheckConstraint(f"requirement IN {_REQUIREMENTS}", name="requirement_valid"),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_job_skills_jobs_job_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_job_skills_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_skills"),
        sa.UniqueConstraint("job_id", "dedupe_key", name="uq_job_skills_job_id"),
    )
    op.create_index("ix_job_skills_job_id", "job_skills", ["job_id"])
    op.create_index("ix_job_skills_user_id", "job_skills", ["user_id"])
    op.create_index("ix_job_skills_user_id_job_id", "job_skills", ["user_id", "job_id"])

    op.create_table(
        "job_matches",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("job_id", UUIDType(), nullable=False),
        sa.Column("score", NumericType(5, 2), nullable=False),
        sa.Column("skill_score", NumericType(5, 2), nullable=False),
        sa.Column("experience_score", NumericType(5, 2), nullable=False),
        sa.Column("project_score", NumericType(5, 2), nullable=False),
        sa.Column("education_score", NumericType(5, 2), nullable=False),
        sa.Column("evidence_score", NumericType(5, 2), nullable=False),
        sa.Column("weights", JSONType(), nullable=False),
        sa.Column("strengths", JSONType(), nullable=False),
        sa.Column("gaps", JSONType(), nullable=False),
        sa.Column("unknowns", JSONType(), nullable=False),
        sa.Column("why", JSONType(), nullable=False),
        sa.Column("evidence_used", JSONType(), nullable=False),
        sa.Column("algorithm_version", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
        sa.CheckConstraint(
            "skill_score BETWEEN 0 AND 100 AND experience_score BETWEEN 0 AND 100 "
            "AND project_score BETWEEN 0 AND 100 AND education_score BETWEEN 0 AND 100 "
            "AND evidence_score BETWEEN 0 AND 100",
            name="dimension_scores_range",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_job_matches_jobs_job_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_job_matches_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_job_matches"),
    )
    op.create_index("ix_job_matches_job_id", "job_matches", ["job_id"])
    op.create_index("ix_job_matches_user_id", "job_matches", ["user_id"])
    op.create_index(
        "ix_job_matches_user_id_job_id_created_at",
        "job_matches",
        ["user_id", "job_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_job_matches_user_id_job_id_created_at", table_name="job_matches")
    op.drop_index("ix_job_matches_user_id", table_name="job_matches")
    op.drop_index("ix_job_matches_job_id", table_name="job_matches")
    op.drop_table("job_matches")
    op.drop_index("ix_job_skills_user_id_job_id", table_name="job_skills")
    op.drop_index("ix_job_skills_user_id", table_name="job_skills")
    op.drop_index("ix_job_skills_job_id", table_name="job_skills")
    op.drop_table("job_skills")
    op.drop_index("ix_jobs_user_id_created_at", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    op.drop_table("jobs")
