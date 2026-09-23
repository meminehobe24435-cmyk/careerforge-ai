"""Job description schemas: structured JD analysis, skill tree, and skill gaps."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from careerforge_ai.schemas.common import (
    CFBaseModel,
    Confidence,
    EvidenceStrength,
    GapLevel,
    RequirementLevel,
    Score0to100,
    SkillCategory,
    SkillLevel,
    StrictModel,
    Unit,
    utcnow,
)

__all__ = [
    "ExtractedJD",
    "ExtractedJDSkill",
    "JDAnalysis",
    "JDSkill",
    "JDSkillNode",
    "JDSkillTree",
    "JobSummary",
    "SkillGapMatrix",
    "SkillGapRow",
]


class JDSkill(CFBaseModel):
    """A skill extracted from a job description, with its provenance sentence."""

    skill_id: UUID | None = None
    canonical_id: str | None = Field(
        default=None, description="Taxonomy id when normalisation succeeded, else None"
    )
    raw_text: str = Field(description="Exactly how the JD phrased it")
    requirement: RequirementLevel = RequirementLevel.REQUIRED
    weight: Unit = 1.0
    jd_evidence: str = Field(
        default="",
        description="The original JD sentence that mentions this skill — shown as 'where this came from'",
    )
    mentions: int = Field(default=1, ge=1)

    @property
    def display_name(self) -> str:
        return self.raw_text


class JDAnalysis(CFBaseModel):
    """The full structured form of a job description."""

    company: str | None = None
    role: str = Field(default="", description="Job title")
    level: str | None = Field(default=None, description="junior | mid | senior | lead | intern")
    location: str | None = None
    remote_type: str | None = Field(default=None, description="onsite | hybrid | remote")
    employment_type: str | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    salary_currency: str | None = None
    education_requirement: str | None = None
    years_experience_min: float | None = Field(default=None, ge=0, le=50)

    responsibilities: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    required_skills: list[JDSkill] = Field(default_factory=list)
    preferred_skills: list[JDSkill] = Field(default_factory=list)
    bonus_skills: list[JDSkill] = Field(default_factory=list)

    parse_confidence: Confidence = 0.0
    parse_status: str = Field(default="parsed", description="parsed | heuristic_fallback | failed")
    degraded: bool = False
    parser_version: str = "jd@1.0.0"

    @property
    def all_skills(self) -> list[JDSkill]:
        return [*self.required_skills, *self.preferred_skills, *self.bonus_skills]

    @property
    def required_canonical_ids(self) -> list[str]:
        return [s.canonical_id for s in self.required_skills if s.canonical_id]

    def skill_ids_by_requirement(self, requirement: RequirementLevel) -> list[str]:
        source = {
            RequirementLevel.REQUIRED: self.required_skills,
            RequirementLevel.PREFERRED: self.preferred_skills,
            RequirementLevel.BONUS: self.bonus_skills,
        }[requirement]
        return [s.canonical_id for s in source if s.canonical_id]


class ExtractedJDSkill(StrictModel):
    name: str = Field(description="Skill exactly as named in the job description")
    requirement: RequirementLevel = Field(
        default=RequirementLevel.REQUIRED,
        description="required = must have; preferred = nice but not mandatory; bonus = a plus",
    )
    evidence: str = Field(
        default="",
        description="The verbatim sentence or clause from the JD that mentions this skill",
    )


class ExtractedJD(StrictModel):
    """LLM-facing JD contract.

    Guidance encoded in the field descriptions is the primary defence against
    over-extraction: the model is told repeatedly to stay literal.
    """

    company: str | None = Field(default=None, description="Hiring company name, or null if absent")
    role: str = Field(default="", description="The job title")
    level: str | None = Field(
        default=None, description="junior | mid | senior | lead | intern, or null"
    )
    location: str | None = None
    remote_type: str | None = Field(default=None, description="onsite | hybrid | remote, or null")
    employment_type: str | None = Field(
        default=None, description="full-time | part-time | internship, or null"
    )
    salary_min: float | None = Field(default=None, description="Numeric only, no currency symbol")
    salary_max: float | None = None
    salary_currency: str | None = Field(default=None, description="e.g. CNY, USD, or null")
    education_requirement: str | None = Field(default=None, description="e.g. 'Bachelor', or null")
    years_experience_min: float | None = Field(
        default=None, description="Minimum years if stated, else null"
    )

    responsibilities: list[str] = Field(
        default_factory=list, description="What the person will do; keep close to the JD wording"
    )
    nice_to_have: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(
        default_factory=list,
        description="Other ATS-relevant terms (domain words, methodologies, tools)",
    )

    required_skills: list[ExtractedJDSkill] = Field(
        default_factory=list, description="Only skills the JD presents as mandatory"
    )
    preferred_skills: list[ExtractedJDSkill] = Field(default_factory=list)
    bonus_skills: list[ExtractedJDSkill] = Field(default_factory=list)

    @field_validator("required_skills", "preferred_skills", "bonus_skills")
    @classmethod
    def _dedupe_skills(cls, value: list[ExtractedJDSkill]) -> list[ExtractedJDSkill]:
        seen: set[str] = set()
        out: list[ExtractedJDSkill] = []
        for skill in value:
            key = skill.name.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(skill)
        return out


class JDSkillNode(CFBaseModel):
    """One row of the JD skill tree in the UI."""

    canonical_id: str | None = None
    raw_text: str
    category: SkillCategory = SkillCategory.TOOL
    requirement: RequirementLevel
    jd_evidence: str = ""

    user_level: SkillLevel = SkillLevel.NONE
    user_evidence_count: int = 0
    user_confidence: Confidence = 0.0
    matched: bool = False


class JDSkillTree(CFBaseModel):
    """Three-tier skill tree enriched with the candidate's current standing."""

    job_id: UUID | None = None
    required: list[JDSkillNode] = Field(default_factory=list)
    preferred: list[JDSkillNode] = Field(default_factory=list)
    bonus: list[JDSkillNode] = Field(default_factory=list)

    @property
    def all_nodes(self) -> list[JDSkillNode]:
        return [*self.required, *self.preferred, *self.bonus]

    @property
    def match_ratio(self) -> float:
        """Share of *required* skills the candidate can evidence."""
        if not self.required:
            return 0.0
        return sum(1 for node in self.required if node.matched) / len(self.required)


class SkillGapRow(CFBaseModel):
    """A row of the skill gap matrix."""

    canonical_id: str
    display_name: str
    requirement: RequirementLevel
    user_level: SkillLevel
    evidence_strength: EvidenceStrength
    gap_level: GapLevel
    priority: Score0to100 = Field(description="0–100 priority; higher means fix it first")
    rationale: str = ""
    jd_mentions: int = 0
    evidence_ids: list[UUID] = Field(default_factory=list)


class SkillGapMatrix(CFBaseModel):
    job_id: UUID | None = None
    company: str | None = None
    role: str = ""
    rows: list[SkillGapRow] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)
    algorithm_version: str = "gap@1.0.0"

    @property
    def gaps(self) -> list[SkillGapRow]:
        return [row for row in self.rows if row.gap_level is not GapLevel.NONE]

    @property
    def high_priority(self) -> list[SkillGapRow]:
        return [row for row in self.rows if row.gap_level is GapLevel.HIGH]


class JobSummary(CFBaseModel):
    """Lightweight job representation used by lists, dashboards and pickers."""

    id: UUID
    company: str | None = None
    role: str
    location: str | None = None
    status: str | None = None
    match_score: Score0to100 | None = None
    created_at: datetime | None = None
    required_skill_count: int = 0
    parse_status: str = "parsed"
