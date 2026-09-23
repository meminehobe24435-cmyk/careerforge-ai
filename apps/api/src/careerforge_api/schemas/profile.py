"""Profile models: ``/profile`` (``docs/API.md`` §2.2).

The response is the *assembled* profile — the same object the graph builder, the match engine
and the dashboard read — so what a client shows and what the system scores cannot diverge.

Another rule lives here: ``origin`` and ``evidence_strength`` are returned on every entity.
A row a model extracted and nobody has checked must be visibly different from one a candidate
corrected, which is what ``docs/PRD.md`` §5 means by corrections raising confidence.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ProfileAchievementResponse",
    "ProfileEducationResponse",
    "ProfileExperienceResponse",
    "ProfileImportAccepted",
    "ProfileProjectResponse",
    "ProfileResponse",
    "ProfileSkillResponse",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ProfileEducationResponse(_CamelModel):
    id: str | None = None
    school: str
    degree: str | None = None
    major: str | None = None
    start_date: date | None = Field(default=None, alias="startDate")
    end_date: date | None = Field(default=None, alias="endDate")
    gpa: float | None = None
    highlights: list[str] = Field(default_factory=list)
    evidence_strength: float = Field(default=0.0, alias="evidenceStrength")
    origin: str = "llm"


class ProfileExperienceResponse(_CamelModel):
    id: str | None = None
    kind: str = "fulltime"
    company: str
    title: str
    location: str | None = None
    start_date: date | None = Field(default=None, alias="startDate")
    end_date: date | None = Field(default=None, alias="endDate")
    is_current: bool = Field(default=False, alias="isCurrent")
    description: str = ""
    highlights: list[str] = Field(default_factory=list)
    evidence_strength: float = Field(default=0.0, alias="evidenceStrength")
    origin: str = "llm"


class ProfileProjectResponse(_CamelModel):
    id: str | None = None
    name: str
    role: str | None = None
    summary: str = ""
    description: str = ""
    tech_stack: list[str] = Field(default_factory=list, alias="techStack")
    start_date: date | None = Field(default=None, alias="startDate")
    end_date: date | None = Field(default=None, alias="endDate")
    links: dict[str, str] = Field(default_factory=dict)
    key_challenges: list[str] = Field(default_factory=list, alias="keyChallenges")
    evidence_strength: float = Field(default=0.0, alias="evidenceStrength")
    origin: str = "llm"


class ProfileAchievementResponse(_CamelModel):
    id: str | None = None
    kind: str = "other"
    title: str
    issuer: str | None = None
    awarded_on: date | None = Field(default=None, alias="awardedOn")
    level: str | None = None
    description: str = ""
    evidence_strength: float = Field(default=0.0, alias="evidenceStrength")
    origin: str = "llm"


class ProfileSkillResponse(_CamelModel):
    canonical_id: str = Field(alias="canonicalId")
    display_name: str = Field(alias="displayName")
    category: str = "tool"
    level: str = "none"
    evidence_count: int = Field(default=0, alias="evidenceCount")
    evidence_score: float = Field(default=0.0, alias="evidenceScore")
    is_target: bool = Field(default=False, alias="isTarget")
    origin: str = "llm"


class ProfileResponse(_CamelModel):
    """``data`` of ``GET /profile`` and of ``POST /profile/import``."""

    id: str | None = None
    slug: str | None = None
    headline: str = ""
    summary: str = ""
    location: str | None = None
    github_username: str | None = Field(default=None, alias="githubUsername")
    website: str | None = None
    target_roles: list[str] = Field(default_factory=list, alias="targetRoles")
    years_experience: float | None = Field(default=None, alias="yearsExperience")
    educations: list[ProfileEducationResponse] = Field(default_factory=list)
    experiences: list[ProfileExperienceResponse] = Field(default_factory=list)
    projects: list[ProfileProjectResponse] = Field(default_factory=list)
    achievements: list[ProfileAchievementResponse] = Field(default_factory=list)
    skills: list[ProfileSkillResponse] = Field(default_factory=list)

    @classmethod
    def from_schema(
        cls, profile: Any, *, declared_skills: list[Any] | None = None
    ) -> ProfileResponse:
        """Project the assembled ``CandidateProfile``.

        ``origin`` is carried through per entity because an unchecked extraction and a
        human correction must stay distinguishable on screen, not only in the database.
        """
        return cls(
            id=str(profile.user_id) if profile.user_id else None,
            slug=profile.slug,
            headline=profile.headline,
            summary=profile.summary,
            location=profile.location,
            github_username=profile.github_username,
            website=profile.website,
            target_roles=list(profile.target_roles),
            years_experience=profile.years_experience,
            educations=[
                ProfileEducationResponse(
                    id=str(item.id) if item.id else None,
                    school=item.school,
                    degree=item.degree,
                    major=item.major,
                    start_date=item.start_date,
                    end_date=item.end_date,
                    gpa=item.gpa,
                    highlights=list(item.highlights),
                    evidence_strength=item.evidence_strength.numeric,
                    origin=item.origin.value,
                )
                for item in profile.educations
            ],
            experiences=[
                ProfileExperienceResponse(
                    id=str(item.id) if item.id else None,
                    kind=item.kind,
                    company=item.company,
                    title=item.title,
                    location=item.location,
                    start_date=item.start_date,
                    end_date=item.end_date,
                    is_current=item.is_current,
                    description=item.description,
                    highlights=list(item.highlights),
                    evidence_strength=item.evidence_strength.numeric,
                    origin=item.origin.value,
                )
                for item in profile.experiences
            ],
            projects=[
                ProfileProjectResponse(
                    id=str(item.id) if item.id else None,
                    name=item.name,
                    role=item.role,
                    summary=item.summary,
                    description=item.description,
                    tech_stack=list(item.tech_stack),
                    start_date=item.start_date,
                    end_date=item.end_date,
                    links=dict(item.links),
                    key_challenges=list(item.key_challenges),
                    evidence_strength=item.evidence_strength.numeric,
                    origin=item.origin.value,
                )
                for item in profile.projects
            ],
            achievements=[
                ProfileAchievementResponse(
                    id=str(item.id) if item.id else None,
                    kind=item.kind,
                    title=item.title,
                    issuer=item.issuer,
                    awarded_on=item.awarded_on,
                    level=item.level,
                    description=item.description,
                    evidence_strength=item.evidence_strength.numeric,
                    origin=item.origin.value,
                )
                for item in profile.achievements
            ],
            skills=[
                ProfileSkillResponse(
                    canonical_id=item.skill.canonical_id,
                    display_name=item.skill.display_name,
                    category=item.skill.category.value,
                    level=item.level.value,
                    evidence_count=item.evidence_count,
                    evidence_score=float(item.evidence_score),
                    is_target=item.is_target,
                    origin=item.origin.value,
                )
                for item in (declared_skills or [])
            ],
        )


class ProfileImportAccepted(_CamelModel):
    """``data`` of ``POST /profile/import`` — what the extraction stored."""

    counts: dict[str, int] = Field(default_factory=dict)
    skills_normalised: dict[str, str] = Field(default_factory=dict, alias="skillsNormalised")
    #: Skill names the taxonomy does not know. Reported rather than stored as free text:
    #: a declaration that cannot be joined to the graph is a declaration nothing can check.
    unmapped_skills: list[str] = Field(default_factory=list, alias="unmappedSkills")
    warnings: list[str] = Field(default_factory=list)
    degraded: bool = False
    document_id: str | None = Field(default=None, alias="documentId")
    profile: ProfileResponse
