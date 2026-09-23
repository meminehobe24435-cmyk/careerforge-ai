"""PHASE 8: the application tracker, its event log and the career timeline.

Revision ID: 0007
Revises: 0006
Create Date: 2026-02-12

Scope is ``docs/DATABASE.md`` §2.7 and §2.11. Column names match the ORM models
exactly, because ``tests/test_schema_inventory.py`` compares them and a mismatch is a
hard failure rather than silent drift.

Two foreign keys are deliberately weaker than they could be:

* ``applications.job_id`` is ``SET NULL``. Deleting a posting must not delete the fact
  that you applied to it; the card keeps its own snapshot of the company and role.
* ``career_events.ref_id`` has no foreign key at all. The timeline outlives the rows it
  describes — a milestone is a historical fact, not a reference that should cascade away.

``career_events.metadata`` carries a unique ``(user_id, dedupe_key)`` constraint so a card
dragged back and forth does not write the same milestone twice.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_STATUSES = "('wishlist','applied','oa','interview','final','offer','rejected')"
_KINDS = "('project','internship','application','interview','offer','skill','education')"


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("job_id", UUIDType(), nullable=True),
        sa.Column("resume_version_id", UUIDType(), nullable=True),
        sa.Column("company_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("match_score_snapshot", NumericType(5, 2), nullable=True),
        sa.Column("applied_at", TimestampType(), nullable=True),
        sa.Column("next_action_at", TimestampType(), nullable=True),
        sa.Column("salary_expectation", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("archived_at", TimestampType(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="status_valid"),
        sa.CheckConstraint(
            "match_score_snapshot IS NULL OR match_score_snapshot BETWEEN 0 AND 100",
            name="match_score_snapshot_range",
        ),
        sa.CheckConstraint("position >= 0", name="position_non_negative"),
        sa.ForeignKeyConstraint(
            ["job_id"], ["jobs.id"], name="fk_applications_jobs_job_id", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["resume_version_id"],
            ["resume_versions.id"],
            name="fk_applications_resume_versions_resume_version_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_applications_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_applications"),
    )
    op.create_index("ix_applications_user_id", "applications", ["user_id"])
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_resume_version_id", "applications", ["resume_version_id"])
    op.create_index(
        "ix_applications_user_id_status_position", "applications", ["user_id", "status", "position"]
    )
    op.create_index(
        "ix_applications_user_id_next_action_at", "applications", ["user_id", "next_action_at"]
    )

    op.create_table(
        "application_events",
        sa.Column("application_id", UUIDType(), nullable=False),
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("occurred_at", TimestampType(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(f"to_status IN {_STATUSES}", name="to_status_valid"),
        sa.CheckConstraint(
            f"from_status IS NULL OR from_status IN {_STATUSES}", name="from_status_valid"
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
            name="fk_application_events_applications_application_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_application_events_users_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_application_events"),
    )
    op.create_index(
        "ix_application_events_application_id", "application_events", ["application_id"]
    )
    op.create_index("ix_application_events_user_id", "application_events", ["user_id"])
    op.create_index(
        "ix_application_events_application_id_occurred_at",
        "application_events",
        ["application_id", "occurred_at"],
    )

    op.create_table(
        "career_events",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ref_type", sa.Text(), nullable=True),
        sa.Column("ref_id", UUIDType(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("occurred_at", TimestampType(), nullable=False),
        sa.Column("metadata", JSONType(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(f"kind IN {_KINDS}", name="kind_valid"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_career_events_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_career_events"),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_career_events_user_id"),
    )
    op.create_index("ix_career_events_user_id", "career_events", ["user_id"])
    op.create_index(
        "ix_career_events_user_id_occurred_at", "career_events", ["user_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_career_events_user_id_occurred_at", table_name="career_events")
    op.drop_index("ix_career_events_user_id", table_name="career_events")
    op.drop_table("career_events")
    op.drop_index(
        "ix_application_events_application_id_occurred_at", table_name="application_events"
    )
    op.drop_index("ix_application_events_user_id", table_name="application_events")
    op.drop_index("ix_application_events_application_id", table_name="application_events")
    op.drop_table("application_events")
    op.drop_index("ix_applications_user_id_next_action_at", table_name="applications")
    op.drop_index("ix_applications_user_id_status_position", table_name="applications")
    op.drop_index("ix_applications_resume_version_id", table_name="applications")
    op.drop_index("ix_applications_job_id", table_name="applications")
    op.drop_index("ix_applications_user_id", table_name="applications")
    op.drop_table("applications")
