"""Career entities: ``educations``, ``experiences``, ``projects``, ``achievements``, ``profile_skills``.

These are ``docs/DATABASE.md`` §2.2 — the half of the candidate profile that is *structured*
rather than quoted. Until they existed, everything downstream read a profile with no
experiences and no projects: the graph drew placeholder nodes, the match engine scored the
experience and project dimensions at 0.0, and Profile Strength's completeness dimension was
blind. The rows here are what those consumers read.

Three conventions worth knowing:

* **``origin``** records where a row came from — a model extraction, a user correction, or an
  import. An extraction a human fixed must stay distinguishable from one nobody has checked,
  which is also what ``docs/PRD.md`` §5 means by "corrections raise confidence".
* **natural keys, not surrogate ones, drive re-imports.** A résumé re-imported must update its
  rows rather than duplicate the whole profile, so each table carries a ``dedupe_key`` derived
  from what identifies the entity to a human (school + degree, company + title, project name).
* **``evidence_strength`` is stored on the row** rather than derived at read time: it is an
  input to the confidence formula (``docs/PRD.md`` §4), and a value that changes when unrelated
  code changes is not a stored fact.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType, NumericType, UUIDType
from careerforge_api.models.skill import Skill

__all__ = [
    "ACHIEVEMENT_KINDS",
    "ENTITY_ORIGINS",
    "EXPERIENCE_KINDS",
    "PROFILE_SKILL_LEVELS",
    "Achievement",
    "Education",
    "Experience",
    "ProfileSkillRow",
    "Project",
]

#: Mirrors ``careerforge_ai.schemas.profile`` vocabularies.
#:
#: ``heuristic`` is **not** in ``docs/DATABASE.md`` §2.2's list, and it has to be here: the AI
#: core's ``Origin`` enum records which extractor produced a row, and the zero-key path is a
#: first-class extractor in this product (ADR-009). Storing its output as ``llm`` would be a
#: false claim about provenance — the thing this column exists to prevent.
ENTITY_ORIGINS: tuple[str, ...] = ("llm", "heuristic", "user_corrected", "import")
EXPERIENCE_KINDS: tuple[str, ...] = (
    "internship",
    "fulltime",
    "parttime",
    "research",
    "campus",
)
ACHIEVEMENT_KINDS: tuple[str, ...] = ("award", "cert", "competition", "publication", "other")
PROFILE_SKILL_LEVELS: tuple[str, ...] = ("none", "basic", "moderate", "strong", "expert")


def _check(column: str, values: tuple[str, ...]) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IN ({', '.join(repr(value) for value in values)})", name=f"{column}_valid"
    )


def _strength_check() -> CheckConstraint:
    return CheckConstraint("evidence_strength BETWEEN 0 AND 1", name="evidence_strength_unit_range")


class Education(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One education entry."""

    __tablename__ = "educations"
    __table_args__ = (
        _check("origin", ENTITY_ORIGINS),
        _strength_check(),
        CheckConstraint("gpa IS NULL OR gpa BETWEEN 0 AND 5", name="gpa_range"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_educations_user_id"),
        Index("ix_educations_user_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    school: Mapped[str] = mapped_column(Text, nullable=False)
    degree: Mapped[str | None] = mapped_column(Text, nullable=True)
    major: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(nullable=True)
    end_date: Mapped[date | None] = mapped_column(nullable=True)
    gpa: Mapped[Decimal | None] = mapped_column(NumericType(3, 2), nullable=True)
    highlights: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    evidence_strength: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("0.0")
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="llm")
    source_document_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    #: ``school|degree`` — what identifies this entry to a human.
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)


class Experience(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One role the candidate held."""

    __tablename__ = "experiences"
    __table_args__ = (
        _check("kind", EXPERIENCE_KINDS),
        _check("origin", ENTITY_ORIGINS),
        _strength_check(),
        UniqueConstraint("user_id", "dedupe_key", name="uq_experiences_user_id"),
        Index("ix_experiences_user_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="fulltime")
    company: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(nullable=True)
    end_date: Mapped[date | None] = mapped_column(nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    highlights: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    evidence_strength: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("0.0")
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="llm")
    source_document_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One project, including the deep-dive fields WF-09 caches."""

    __tablename__ = "projects"
    __table_args__ = (
        _check("origin", ENTITY_ORIGINS),
        _strength_check(),
        UniqueConstraint("user_id", "dedupe_key", name="uq_projects_user_id"),
        Index("ix_projects_user_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tech_stack: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    start_date: Mapped[date | None] = mapped_column(nullable=True)
    end_date: Mapped[date | None] = mapped_column(nullable=True)
    #: Arrives with GitHub Intelligence (§2.4); a foreign key to a missing table cannot exist.
    repository_id: Mapped[UUID | None] = mapped_column(UUIDType, nullable=True)
    links: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    architecture_mermaid: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_challenges: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    technical_decisions: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    tradeoffs: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    debugging_stories: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    #: WF-09's generated deep dive, cached until the project changes.
    deep_dive: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    evidence_strength: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("0.0")
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="llm")
    source_document_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)


class Achievement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One award, certificate, competition result or publication."""

    __tablename__ = "achievements"
    __table_args__ = (
        _check("kind", ACHIEVEMENT_KINDS),
        _check("origin", ENTITY_ORIGINS),
        _strength_check(),
        UniqueConstraint("user_id", "dedupe_key", name="uq_achievements_user_id"),
        Index("ix_achievements_user_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="other")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    issuer: Mapped[str | None] = mapped_column(Text, nullable=True)
    awarded_on: Mapped[date | None] = mapped_column(nullable=True)
    level: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_strength: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("0.0")
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="llm")
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)


class ProfileSkillRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A skill the candidate declares, with its assessed level.

    Named ``ProfileSkillRow`` because ``ProfileSkill`` is the AI core's schema object; the two
    are deliberately different — one is a portable value, the other a row with tenancy.

    This is the table the match engine's "declared skill" concept comes from. Without it, a
    requirement with evidence in the graph and no declaration reads as a gap, and the candidate
    is told they are missing something they actually have.
    """

    __tablename__ = "profile_skills"
    __table_args__ = (
        _check("level", PROFILE_SKILL_LEVELS),
        _check("origin", ENTITY_ORIGINS),
        CheckConstraint("evidence_score BETWEEN 0 AND 1", name="evidence_score_unit_range"),
        CheckConstraint("evidence_count >= 0", name="evidence_count_non_negative"),
        UniqueConstraint("user_id", "skill_id", name="uq_profile_skills_user_id"),
        Index("ix_profile_skills_user_id", "user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False, index=True
    )
    level: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    evidence_score: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("0.0")
    )
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_used_at: Mapped[date | None] = mapped_column(nullable=True)
    #: True for a skill the candidate is actively targeting, which the gap matrix weights.
    is_target: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="llm")
    #: Canonical id, denormalised so the graph can be rebuilt without joining the dictionary.
    canonical_id: Mapped[str] = mapped_column(Text, nullable=False)

    skill: Mapped[Skill] = relationship(lazy="selectin")
