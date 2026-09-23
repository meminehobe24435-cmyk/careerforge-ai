"""``jobs``, ``job_skills``, ``job_matches`` — ``docs/DATABASE.md`` §2.6.

Two decisions worth knowing before reading the columns:

* **``description_sha256`` is unique per user.** Pasting the same posting twice must update
  one job, not create a second one with its own match history — the same reasoning as
  documents in §2.3.
* **``job_skills`` is a row per skill per requirement level**, not a JSON blob. The skill
  tree the UI draws and the "which requirements does this candidate miss" query are both
  graph traversals over these rows; keeping them in JSON would mean re-parsing on every
  match.

``analysis`` keeps the complete ``JDAnalysis``. The normalised columns beside it exist so
the common queries do not have to open the JSON — the JSON remains the record of what the
parser actually produced, which is what makes a correction auditable.

``company_id`` (a foreign key into a global ``companies`` table) is not declared: that
table arrives with the feature that needs a shared company directory. ``company_name_raw``
holds what the posting said in the meantime, which is what the UI shows anyway.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
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

__all__ = [
    "JOB_LEVELS",
    "JOB_PARSE_STATUSES",
    "JOB_REMOTE_TYPES",
    "JOB_SOURCES",
    "REQUIREMENT_LEVELS",
    "Job",
    "JobMatch",
    "JobSkill",
]

#: ``docs/DATABASE.md`` §2.6 — mirrors ``careerforge_ai.schemas.job`` vocabulary.
JOB_REMOTE_TYPES: tuple[str, ...] = ("onsite", "hybrid", "remote")
JOB_SOURCES: tuple[str, ...] = ("paste", "upload", "url", "manual")
JOB_PARSE_STATUSES: tuple[str, ...] = ("pending", "parsed", "heuristic_fallback", "failed")
JOB_LEVELS: tuple[str, ...] = ("intern", "junior", "mid", "senior", "lead")
REQUIREMENT_LEVELS: tuple[str, ...] = ("required", "preferred", "bonus")


def _check(column: str, values: tuple[str, ...]) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IN ({', '.join(repr(value) for value in values)})", name=f"{column}_valid"
    )


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One job posting, with its parsed analysis."""

    __tablename__ = "jobs"
    __table_args__ = (
        _check("remote_type", JOB_REMOTE_TYPES),
        _check("source", JOB_SOURCES),
        _check("parse_status", JOB_PARSE_STATUSES),
        _check("level", JOB_LEVELS),
        CheckConstraint("parse_confidence BETWEEN 0 AND 1", name="parse_confidence_unit_range"),
        CheckConstraint(
            "years_experience_min IS NULL OR years_experience_min BETWEEN 0 AND 50",
            name="years_experience_range",
        ),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="salary_range_ordered",
        ),
        # Re-pasting the same posting must update one row rather than fork its match history.
        UniqueConstraint("user_id", "description_sha256", name="uq_jobs_user_id"),
        Index("ix_jobs_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: What the posting called the company. ``company_id`` arrives with the shared
    #: company directory; until then this is the only company identity there is.
    company_name_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    level: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[Decimal | None] = mapped_column(NumericType(10, 2), nullable=True)
    salary_max: Mapped[Decimal | None] = mapped_column(NumericType(10, 2), nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    education_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    years_experience_min: Mapped[Decimal | None] = mapped_column(NumericType(4, 1), nullable=True)

    description_raw: Mapped[str] = mapped_column(Text, nullable=False)
    #: De-duplication key, and the cache key for a re-analysis of the same text.
    description_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="paste")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: The full ``JDAnalysis`` as the parser produced it — the audit record.
    analysis: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    responsibilities: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    nice_to_have: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    keywords: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    parse_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    parse_confidence: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("0.0")
    )

    skills: Mapped[list[JobSkill]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )
    matches: Mapped[list[JobMatch]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )

    def skills_at(self, requirement: str) -> list[JobSkill]:
        """Skills at one requirement level, heaviest first."""
        return sorted(
            (skill for skill in self.skills if skill.requirement == requirement),
            key=lambda skill: (-float(skill.weight), skill.raw_text),
        )

    @property
    def display_name(self) -> str:
        return f"{self.company_name_raw} · {self.role}" if self.company_name_raw else self.role


class JobSkill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One skill requirement, with the JD sentence that justifies it.

    ``jd_evidence`` is not decoration: it is the "出处" the UI shows next to a requirement,
    and it is what lets a reader check that the parser did not invent the requirement.
    """

    __tablename__ = "job_skills"
    __table_args__ = (
        _check("requirement", REQUIREMENT_LEVELS),
        CheckConstraint("weight BETWEEN 0 AND 1", name="weight_unit_range"),
        CheckConstraint("mentions >= 1", name="mentions_positive"),
        # ``skill_id`` is nullable (a skill the taxonomy could not normalise), so the
        # uniqueness key is the raw text in that case — hence the surrogate key column
        # ``dedupe_key`` rather than a plain unique constraint over a nullable column.
        UniqueConstraint("job_id", "dedupe_key", name="uq_job_skills_job_id"),
        Index("ix_job_skills_user_id_job_id", "user_id", "job_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Canonical id from the skill taxonomy, e.g. ``stm32``. ``None`` when unmatched.
    canonical_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Exactly how the posting phrased it, always present.
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    requirement: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("1.0")
    )
    jd_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mentions: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: ``canonical_id`` when it exists, otherwise the raw text — never NULL, so the unique
    #: constraint above can do its job on both backends.
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)

    job: Mapped[Job] = relationship(back_populates="skills")


class JobMatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One computed match. History is kept; the newest row is the current answer.

    Keeping every run rather than overwriting is what makes the number auditable: when a
    score changes, the previous row says what it changed *from* and which algorithm version
    produced it.
    """

    __tablename__ = "job_matches"
    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint(
            "skill_score BETWEEN 0 AND 100 AND experience_score BETWEEN 0 AND 100 "
            "AND project_score BETWEEN 0 AND 100 AND education_score BETWEEN 0 AND 100 "
            "AND evidence_score BETWEEN 0 AND 100",
            name="dimension_scores_range",
        ),
        Index("ix_job_matches_user_id_job_id_created_at", "user_id", "job_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score: Mapped[Decimal] = mapped_column(NumericType(5, 2), nullable=False)
    skill_score: Mapped[Decimal] = mapped_column(NumericType(5, 2), nullable=False)
    experience_score: Mapped[Decimal] = mapped_column(NumericType(5, 2), nullable=False)
    project_score: Mapped[Decimal] = mapped_column(NumericType(5, 2), nullable=False)
    education_score: Mapped[Decimal] = mapped_column(NumericType(5, 2), nullable=False)
    evidence_score: Mapped[Decimal] = mapped_column(NumericType(5, 2), nullable=False)
    weights: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    strengths: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    gaps: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    unknowns: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    #: The full derivation: formula, per-dimension detail, notes.
    why: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    evidence_used: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    algorithm_version: Mapped[str] = mapped_column(Text, nullable=False, default="match@1.0.0")
    #: Which provider narrated it, when one did. Scoring itself is always deterministic.
    model: Mapped[str | None] = mapped_column(Text, nullable=True)

    job: Mapped[Job] = relationship(back_populates="matches")

    @property
    def dimension_scores(self) -> dict[str, float]:
        """The five dimensions, in the order the UI and the formula both use."""
        return {
            "skill": float(self.skill_score),
            "experience": float(self.experience_score),
            "project": float(self.project_score),
            "education": float(self.education_score),
            "evidence": float(self.evidence_score),
        }
