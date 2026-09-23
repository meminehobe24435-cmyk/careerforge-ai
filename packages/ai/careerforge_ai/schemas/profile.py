"""Candidate profile schemas — the structured form of "who this person is"."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import Field, field_validator

from careerforge_ai.schemas.common import (
    CFBaseModel,
    Confidence,
    EvidenceStrength,
    Origin,
    Score0to100,
    SkillCategory,
    SkillLevel,
    StrictModel,
    Unit,
)

__all__ = [
    "Achievement",
    "CandidateProfile",
    "Education",
    "Experience",
    "ExtractedAchievement",
    "ExtractedEducation",
    "ExtractedExperience",
    "ExtractedProfile",
    "ExtractedProject",
    "ProfileImportResult",
    "ProfileSkill",
    "ProfileStrength",
    "ProfileStrengthDimension",
    "Project",
    "SkillRef",
]


class Education(CFBaseModel):
    id: UUID | None = None
    school: str
    degree: str | None = None
    major: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    gpa: float | None = Field(default=None, ge=0.0, le=5.0)
    highlights: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = EvidenceStrength.NONE
    origin: Origin = Origin.LLM


class Experience(CFBaseModel):
    id: UUID | None = None
    kind: str = Field(
        default="internship", description="internship | fulltime | parttime | research | campus"
    )
    company: str
    title: str
    location: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool = False
    description: str = ""
    highlights: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = EvidenceStrength.NONE
    origin: Origin = Origin.LLM
    source_document_id: UUID | None = None


class Project(CFBaseModel):
    id: UUID | None = None
    name: str
    role: str | None = None
    summary: str = ""
    description: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    repository_id: UUID | None = None
    links: dict[str, str] = Field(default_factory=dict)
    architecture_mermaid: str | None = None
    key_challenges: list[str] = Field(default_factory=list)
    technical_decisions: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    debugging_stories: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = EvidenceStrength.NONE
    origin: Origin = Origin.LLM


class Achievement(CFBaseModel):
    id: UUID | None = None
    kind: str = Field(
        default="award", description="award | cert | competition | publication | other"
    )
    title: str
    issuer: str | None = None
    #: Named ``awarded_on`` rather than ``date``: a field called ``date`` shadows
    #: the ``date`` type inside the class body, which breaks annotation
    #: evaluation. The clearer name is a bonus.
    awarded_on: date | None = None
    level: str | None = Field(default=None, description="e.g. national, provincial, school")
    description: str = ""
    evidence_strength: EvidenceStrength = EvidenceStrength.NONE
    origin: Origin = Origin.LLM


class SkillRef(CFBaseModel):
    """A canonical skill in the taxonomy."""

    id: UUID | None = None
    canonical_id: str = Field(description="Stable slug such as ``stm32`` or ``free_rtos``")
    display_name: str
    category: SkillCategory = SkillCategory.TOOL
    aliases: list[str] = Field(default_factory=list)


class ProfileSkill(CFBaseModel):
    """A skill *as possessed by a candidate*, with evidence backing its level."""

    skill: SkillRef
    level: SkillLevel = SkillLevel.NONE
    evidence_score: Confidence = 0.0
    evidence_count: int = Field(default=0, ge=0)
    is_target: bool = False
    origin: Origin = Origin.LLM

    @property
    def claimed(self) -> bool:
        """True when the candidate asserts the skill at all."""
        return self.level is not SkillLevel.NONE


class CandidateProfile(CFBaseModel):
    """Complete structured candidate knowledge base."""

    user_id: UUID | None = None
    slug: str | None = None
    headline: str = ""
    summary: str = ""
    location: str | None = None
    github_username: str | None = None
    website: str | None = None
    target_roles: list[str] = Field(default_factory=list)
    years_experience: float | None = Field(default=None, ge=0.0, le=60.0)

    educations: list[Education] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    achievements: list[Achievement] = Field(default_factory=list)
    skills: list[ProfileSkill] = Field(default_factory=list)

    def skill_by_canonical_id(self, canonical_id: str) -> ProfileSkill | None:
        lowered = canonical_id.strip().lower()
        for item in self.skills:
            if item.skill.canonical_id.lower() == lowered:
                return item
        return None

    @property
    def claimed_skill_ids(self) -> set[str]:
        return {item.skill.canonical_id for item in self.skills if item.claimed}

    @property
    def evidenced_skill_ids(self) -> set[str]:
        return {item.skill.canonical_id for item in self.skills if item.evidence_count > 0}


class ProfileStrengthDimension(CFBaseModel):
    """One dimension of the Profile Strength score, with its own explanation."""

    key: str
    label: str
    raw: Unit
    weight: Unit
    weighted: Score0to100
    hint: str | None = Field(
        default=None, description="Concrete next action to raise this dimension"
    )


class ProfileStrength(CFBaseModel):
    score: Score0to100
    dimensions: list[ProfileStrengthDimension]
    suggestions: list[dict[str, object]] = Field(default_factory=list)
    formula_version: str = "strength@1.0.0"

    def dimension(self, key: str) -> ProfileStrengthDimension | None:
        return next((dim for dim in self.dimensions if dim.key == key), None)


# ── LLM-facing extraction contracts ──────────────────────────────────────────


class ExtractedEducation(StrictModel):
    school: str = Field(description="Institution name")
    degree: str | None = Field(default=None, description="e.g. Bachelor of Engineering")
    major: str | None = Field(default=None)
    start_date: str | None = Field(default=None, description="ISO date or YYYY-MM if only partial")
    end_date: str | None = Field(default=None, description="ISO date, YYYY-MM, or null if ongoing")
    gpa: float | None = Field(default=None, description="Leave null when not stated")
    highlights: list[str] = Field(
        default_factory=list, description="Notable coursework, ranking, honours"
    )


class ExtractedExperience(StrictModel):
    kind: str = Field(
        default="internship", description="internship | fulltime | parttime | research | campus"
    )
    company: str
    title: str
    location: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False
    description: str = Field(default="", description="What the role was, in the source's own words")
    highlights: list[str] = Field(
        default_factory=list, description="Verbatim or lightly cleaned achievements"
    )


class ExtractedProject(StrictModel):
    name: str
    role: str | None = None
    summary: str = Field(default="", description="One sentence")
    description: str = Field(default="", description="What was built and how")
    tech_stack: list[str] = Field(
        default_factory=list, description="Technologies named in the source only"
    )
    start_date: str | None = None
    end_date: str | None = None
    key_challenges: list[str] = Field(default_factory=list)
    technical_decisions: list[str] = Field(default_factory=list)


class ExtractedAchievement(StrictModel):
    kind: str = Field(
        default="award", description="award | cert | competition | publication | other"
    )
    title: str
    issuer: str | None = None
    date: str | None = None
    level: str | None = None
    description: str = ""


class ExtractedProfile(StrictModel):
    """What the profile agent returns. Deliberately conservative.

    The schema description repeatedly instructs the model to leave fields empty
    rather than infer them: an empty field costs nothing, a fabricated one
    poisons every downstream score.
    """

    headline: str = Field(default="", description="One-line professional identity, or empty")
    summary: str = Field(
        default="", description="2–4 sentence summary based only on the source text"
    )
    location: str | None = None
    target_roles: list[str] = Field(default_factory=list)
    years_experience: float | None = Field(
        default=None, description="Null when it cannot be derived"
    )
    educations: list[ExtractedEducation] = Field(default_factory=list)
    experiences: list[ExtractedExperience] = Field(default_factory=list)
    projects: list[ExtractedProject] = Field(default_factory=list)
    achievements: list[ExtractedAchievement] = Field(default_factory=list)
    skills: list[str] = Field(
        default_factory=list,
        description="Skill names exactly as written in the source. Do NOT add adjacent skills.",
    )

    @field_validator("skills", "target_roles")
    @classmethod
    def _dedupe_preserving_order(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(item.strip())
        return out


class ProfileImportResult(CFBaseModel):
    """Outcome of an import run, shown to the user as a diff summary."""

    document_id: UUID | None = None
    profile: CandidateProfile
    evidence_created: int = 0
    skills_created: int = 0
    skills_normalised: dict[str, str] = Field(default_factory=dict)
    unmapped_skills: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    degraded: bool = False
