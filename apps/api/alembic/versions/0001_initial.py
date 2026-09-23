"""PHASE 1 baseline: users, profiles, public_profiles, skills, prompt_versions,
agent_runs, llm_calls, background_jobs, ai_caches.

Revision ID: 0001
Revises:
Create Date: 2026-02-11

Scope is exactly the PHASE 1 tables from ``docs/DATABASE.md`` §2 — the remaining 24
tables arrive with the phases that introduce their domain logic. The schema this
produces is byte-for-byte equivalent (same tables, columns, ``CHECK`` constraints,
uniques, foreign keys and indexes) to ``Base.metadata.create_all()``, which is what
``tests/test_migrations.py`` asserts; that equivalence is what lets the zero-dependency
SQLite path skip migrations without ending up on a different schema.

Two implementation notes:

* the SQLite⇄PostgreSQL type decorators come from ``careerforge_api.db.compat`` rather
  than being re-declared here. ``docs/DATABASE.md`` §5 makes that module the single
  definition of the cross-dialect mapping; duplicating it per migration is how the two
  paths would silently diverge.
* ``CHECK`` constraints are declared with their **short rule name** (``status_valid``),
  exactly like the models, because SQLAlchemy feeds that name into the
  ``ck_%(table_name)s_%(constraint_name)s`` convention from
  ``careerforge_api.db.base``. Declaring the finished name here would produce
  ``ck_agent_runs_ck_agent_runs_status_valid``; short names are what make
  ``alembic upgrade head`` and ``create_all`` agree constraint for constraint.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── identity ─────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("storage_scope", sa.Text(), nullable=False),
        sa.Column("privacy_settings", JSONType(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False),
        sa.Column("last_login_at", TimestampType(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("role IN ('user','admin')", name="role_valid"),
        sa.CheckConstraint("storage_scope IN ('cloud','local')", name="storage_scope_valid"),
        sa.CheckConstraint(
            "password_hash IS NOT NULL OR is_demo = true",
            name="demo_accounts_need_no_password",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "profiles",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("headline", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("github_username", sa.Text(), nullable=True),
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("target_roles", JSONType(), nullable=False),
        sa.Column("years_experience", NumericType(3, 1), nullable=True),
        sa.Column("profile_strength", sa.Integer(), nullable=True),
        sa.Column("strength_breakdown", JSONType(), nullable=False),
        sa.Column("stats", JSONType(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(
            "profile_strength IS NULL OR (profile_strength >= 0 AND profile_strength <= 100)",
            name="profile_strength_range",
        ),
        sa.CheckConstraint(
            "years_experience IS NULL OR (years_experience >= 0 AND years_experience <= 99.9)",
            name="years_experience_range",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_profiles_users_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_profiles"),
        sa.UniqueConstraint("slug", name="uq_profiles_slug"),
        sa.UniqueConstraint("user_id", name="uq_profiles_user_id"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])

    op.create_table(
        "public_profiles",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("sections", JSONType(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("highlights", JSONType(), nullable=False),
        sa.Column("interview_topics", JSONType(), nullable=False),
        sa.Column("view_count", sa.Integer(), nullable=False),
        sa.Column("published_at", TimestampType(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("view_count >= 0", name="view_count_non_negative"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_public_profiles_users_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_public_profiles"),
        sa.UniqueConstraint("slug", name="uq_public_profiles_slug"),
        sa.UniqueConstraint("user_id", name="uq_public_profiles_user_id"),
    )
    op.create_index("ix_public_profiles_is_published", "public_profiles", ["is_published"])

    # ── taxonomy (global, no user_id) ────────────────────────────────────────
    op.create_table(
        "skills",
        sa.Column("canonical_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("aliases", JSONType(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(
            "category IN ('language', 'framework', 'embedded', 'backend', 'frontend', "
            "'ai', 'devops', 'database', 'tool', 'domain', 'soft')",
            name="category_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_skills"),
        sa.UniqueConstraint("canonical_id", name="uq_skills_canonical_id"),
    )

    # ── prompt registry mirror ───────────────────────────────────────────────
    op.create_table(
        "prompt_versions",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("variables", JSONType(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_prompt_versions"),
        sa.UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
    )
    op.create_index("ix_prompt_versions_name_is_active", "prompt_versions", ["name", "is_active"])

    # ── observability ────────────────────────────────────────────────────────
    op.create_table(
        "agent_runs",
        sa.Column("user_id", UUIDType(), nullable=True),
        sa.Column("workflow", sa.Text(), nullable=False),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("steps", JSONType(), nullable=False),
        sa.Column("input_ref", JSONType(), nullable=False),
        sa.Column("output_ref", JSONType(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", NumericType(10, 6), nullable=False),
        sa.Column("cost_cny", NumericType(10, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("parent_run_id", UUIDType(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", TimestampType(), nullable=True),
        sa.Column("finished_at", TimestampType(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'degraded')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "trigger IN ('api', 'job', 'manual', 'seed', 'eval')",
            name="trigger_valid",
        ),
        sa.CheckConstraint(
            "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0",
            name="token_counts_non_negative",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="latency_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_agent_runs_users_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_run_id"],
            ["agent_runs.id"],
            name="fk_agent_runs_agent_runs_parent_run_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_runs"),
    )
    op.create_index("ix_agent_runs_user_id_started_at", "agent_runs", ["user_id", "started_at"])
    op.create_index("ix_agent_runs_workflow_started_at", "agent_runs", ["workflow", "started_at"])
    op.create_index("ix_agent_runs_request_id", "agent_runs", ["request_id"])

    op.create_table(
        "llm_calls",
        sa.Column("user_id", UUIDType(), nullable=True),
        sa.Column("agent_run_id", UUIDType(), nullable=True),
        sa.Column("agent", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", NumericType(10, 6), nullable=False),
        sa.Column("cost_cny", NumericType(10, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(
            "operation IN ('chat', 'stream', 'embed', 'structured')",
            name="operation_valid",
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'error', 'timeout', 'rate_limited', 'cache_hit')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0",
            name="token_counts_non_negative",
        ),
        sa.CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_non_negative"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_llm_calls_users_user_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name="fk_llm_calls_agent_runs_agent_run_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_llm_calls"),
    )
    op.create_index("ix_llm_calls_user_id_created_at", "llm_calls", ["user_id", "created_at"])
    op.create_index("ix_llm_calls_agent_created_at", "llm_calls", ["agent", "created_at"])

    # ── platform: tasks and caches ───────────────────────────────────────────
    op.create_table(
        "background_jobs",
        sa.Column("user_id", UUIDType(), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payload", JSONType(), nullable=False),
        sa.Column("result", JSONType(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.Text(), nullable=True),
        sa.Column("queued_at", TimestampType(), nullable=True),
        sa.Column("started_at", TimestampType(), nullable=True),
        sa.Column("finished_at", TimestampType(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="status_valid",
        ),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        sa.CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        sa.CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_background_jobs_users_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_background_jobs"),
        sa.UniqueConstraint("idempotency_key", name="uq_background_jobs_idempotency_key"),
    )
    op.create_index("ix_background_jobs_user_id", "background_jobs", ["user_id"])
    op.create_index(
        "ix_background_jobs_status_queued_at", "background_jobs", ["status", "queued_at"]
    )

    op.create_table(
        "ai_caches",
        sa.Column("user_id", UUIDType(), nullable=True),
        sa.Column("cache_key", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", JSONType(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", TimestampType(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint("kind IN ('llm', 'embedding', 'tool')", name="kind_valid"),
        sa.CheckConstraint("hit_count >= 0", name="hit_count_non_negative"),
        sa.CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_bytes_non_negative"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_ai_caches_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_ai_caches"),
        sa.UniqueConstraint("cache_key", name="uq_ai_caches_cache_key"),
    )
    op.create_index("ix_ai_caches_user_id", "ai_caches", ["user_id"])
    op.create_index("ix_ai_caches_kind_expires_at", "ai_caches", ["kind", "expires_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_caches_kind_expires_at", table_name="ai_caches")
    op.drop_index("ix_ai_caches_user_id", table_name="ai_caches")
    op.drop_table("ai_caches")

    op.drop_index("ix_background_jobs_status_queued_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_user_id", table_name="background_jobs")
    op.drop_table("background_jobs")

    op.drop_index("ix_llm_calls_agent_created_at", table_name="llm_calls")
    op.drop_index("ix_llm_calls_user_id_created_at", table_name="llm_calls")
    op.drop_table("llm_calls")

    op.drop_index("ix_agent_runs_request_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_workflow_started_at", table_name="agent_runs")
    op.drop_index("ix_agent_runs_user_id_started_at", table_name="agent_runs")
    op.drop_table("agent_runs")

    op.drop_index("ix_prompt_versions_name_is_active", table_name="prompt_versions")
    op.drop_table("prompt_versions")

    op.drop_table("skills")

    op.drop_index("ix_public_profiles_is_published", table_name="public_profiles")
    op.drop_table("public_profiles")

    op.drop_index("ix_profiles_user_id", table_name="profiles")
    op.drop_table("profiles")

    op.drop_table("users")
