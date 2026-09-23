"""PHASE 2b: the structured career entities.

Revision ID: 0005
Revises: 0004
Create Date: 2026-02-11

Scope is ``docs/DATABASE.md`` §2.2: ``educations``, ``experiences``, ``projects``,
``achievements`` and ``profile_skills``.

Two notes on the schema. Each entity carries an application-generated ``dedupe_key`` (school +
degree, company + title, project name) so re-importing a résumé updates its rows instead of
duplicating the profile — the uniqueness has to be enforced by the database, not by a
read-before-write in the importer. And ``projects.repository_id`` is a bare uuid with no
foreign key: it references §2.4's ``repositories``, which arrives with GitHub Intelligence, and
a foreign key to a table that does not exist cannot be created.

``project_skills`` / ``experience_skills`` (§2.2) are deliberately not here yet. Their only
consumer is the WF-09 project deep dive, and the graph derives project→skill edges from
``projects.tech_stack`` text today; adding join tables nothing reads would be scaffolding.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

_ORIGINS = "('llm','heuristic','user_corrected','import')"
_EXPERIENCE_KINDS = "('internship','fulltime','parttime','research','campus')"
_ACHIEVEMENT_KINDS = "('award','cert','competition','publication','other')"
_SKILL_LEVELS = "('none','basic','moderate','strong','expert')"


def _entity_columns(extra: list[sa.Column], *, with_source: bool = True) -> list[sa.Column]:
    """The columns every entity table shares, in the order the models declare them.

    Order is part of the model/migration equivalence the test suite asserts, so the shared
    tail is written once here rather than remembered per table.
    """
    tail = [
        sa.Column("evidence_strength", NumericType(4, 3), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
    ]
    if with_source:
        tail.append(sa.Column("source_document_id", UUIDType(), nullable=True))
    return [
        sa.Column("user_id", UUIDType(), nullable=False),
        *extra,
        *tail,
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
    ]


def _shared_constraints(table: str) -> list[sa.schema.constraints.Constraint]:
    return [
        sa.CheckConstraint(f"origin IN {_ORIGINS}", name="origin_valid"),
        sa.CheckConstraint(
            "evidence_strength BETWEEN 0 AND 1", name="evidence_strength_unit_range"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=f"fk_{table}_users_user_id", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        sa.UniqueConstraint("user_id", "dedupe_key", name=f"uq_{table}_user_id"),
    ]


def upgrade() -> None:
    op.create_table(
        "educations",
        *_entity_columns(
            [
                sa.Column("school", sa.Text(), nullable=False),
                sa.Column("degree", sa.Text(), nullable=True),
                sa.Column("major", sa.Text(), nullable=True),
                sa.Column("start_date", sa.Date(), nullable=True),
                sa.Column("end_date", sa.Date(), nullable=True),
                sa.Column("gpa", NumericType(3, 2), nullable=True),
                sa.Column("highlights", JSONType(), nullable=False),
            ]
        ),
        sa.CheckConstraint("gpa IS NULL OR gpa BETWEEN 0 AND 5", name="gpa_range"),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            name="fk_educations_documents_source_document_id",
            ondelete="SET NULL",
        ),
        *_shared_constraints("educations"),
    )
    op.create_index("ix_educations_user_id", "educations", ["user_id"])

    op.create_table(
        "experiences",
        *_entity_columns(
            [
                sa.Column("kind", sa.Text(), nullable=False),
                sa.Column("company", sa.Text(), nullable=False),
                sa.Column("title", sa.Text(), nullable=False),
                sa.Column("location", sa.Text(), nullable=True),
                sa.Column("start_date", sa.Date(), nullable=True),
                sa.Column("end_date", sa.Date(), nullable=True),
                sa.Column("is_current", sa.Boolean(), nullable=False),
                sa.Column("description", sa.Text(), nullable=False),
                sa.Column("highlights", JSONType(), nullable=False),
            ]
        ),
        sa.CheckConstraint(f"kind IN {_EXPERIENCE_KINDS}", name="kind_valid"),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            name="fk_experiences_documents_source_document_id",
            ondelete="SET NULL",
        ),
        *_shared_constraints("experiences"),
    )
    op.create_index("ix_experiences_user_id", "experiences", ["user_id"])

    op.create_table(
        "projects",
        *_entity_columns(
            [
                sa.Column("name", sa.Text(), nullable=False),
                sa.Column("role", sa.Text(), nullable=True),
                sa.Column("summary", sa.Text(), nullable=False),
                sa.Column("description", sa.Text(), nullable=False),
                sa.Column("tech_stack", JSONType(), nullable=False),
                sa.Column("start_date", sa.Date(), nullable=True),
                sa.Column("end_date", sa.Date(), nullable=True),
                # No foreign key: §2.4's repositories table does not exist yet.
                sa.Column("repository_id", UUIDType(), nullable=True),
                sa.Column("links", JSONType(), nullable=False),
                sa.Column("architecture_mermaid", sa.Text(), nullable=True),
                sa.Column("key_challenges", JSONType(), nullable=False),
                sa.Column("technical_decisions", JSONType(), nullable=False),
                sa.Column("tradeoffs", JSONType(), nullable=False),
                sa.Column("debugging_stories", JSONType(), nullable=False),
                sa.Column("deep_dive", JSONType(), nullable=False),
            ]
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["documents.id"],
            name="fk_projects_documents_source_document_id",
            ondelete="SET NULL",
        ),
        *_shared_constraints("projects"),
    )
    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    op.create_table(
        "achievements",
        *_entity_columns(
            [
                sa.Column("kind", sa.Text(), nullable=False),
                sa.Column("title", sa.Text(), nullable=False),
                sa.Column("issuer", sa.Text(), nullable=True),
                sa.Column("awarded_on", sa.Date(), nullable=True),
                sa.Column("level", sa.Text(), nullable=True),
                sa.Column("description", sa.Text(), nullable=False),
            ],
            # §2.2 gives achievements no source document: an award is evidenced by a
            # certificate rather than by the résumé being parsed, so the column would be
            # empty for every row this build can produce.
            with_source=False,
        ),
        sa.CheckConstraint(f"kind IN {_ACHIEVEMENT_KINDS}", name="kind_valid"),
        *_shared_constraints("achievements"),
    )
    op.create_index("ix_achievements_user_id", "achievements", ["user_id"])

    op.create_table(
        "profile_skills",
        sa.Column("user_id", UUIDType(), nullable=False),
        sa.Column("skill_id", UUIDType(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("evidence_score", NumericType(4, 3), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.Date(), nullable=True),
        sa.Column("is_target", sa.Boolean(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("canonical_id", sa.Text(), nullable=False),
        sa.Column("id", UUIDType(), nullable=False),
        sa.Column("created_at", TimestampType(), nullable=False),
        sa.Column("updated_at", TimestampType(), nullable=False),
        sa.CheckConstraint(f"level IN {_SKILL_LEVELS}", name="level_valid"),
        sa.CheckConstraint(f"origin IN {_ORIGINS}", name="origin_valid"),
        sa.CheckConstraint("evidence_score BETWEEN 0 AND 1", name="evidence_score_unit_range"),
        sa.CheckConstraint("evidence_count >= 0", name="evidence_count_non_negative"),
        sa.ForeignKeyConstraint(
            ["skill_id"],
            ["skills.id"],
            name="fk_profile_skills_skills_skill_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_profile_skills_users_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_profile_skills"),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_profile_skills_user_id"),
    )
    op.create_index("ix_profile_skills_skill_id", "profile_skills", ["skill_id"])
    op.create_index("ix_profile_skills_user_id", "profile_skills", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_profile_skills_user_id", table_name="profile_skills")
    op.drop_index("ix_profile_skills_skill_id", table_name="profile_skills")
    op.drop_table("profile_skills")
    op.drop_index("ix_achievements_user_id", table_name="achievements")
    op.drop_table("achievements")
    op.drop_index("ix_projects_user_id", table_name="projects")
    op.drop_table("projects")
    op.drop_index("ix_experiences_user_id", table_name="experiences")
    op.drop_table("experiences")
    op.drop_index("ix_educations_user_id", table_name="educations")
    op.drop_table("educations")
