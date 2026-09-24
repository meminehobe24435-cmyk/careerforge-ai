"""Public candidate page models (``docs/API.md`` §2.13).

The public payload is returned **as the recruiter receives it** — sections already filtered,
PII already masked — plus a small ``meta`` block that says what the shape is. There is nothing
in here a stranger should not see: if a field cannot be shown to anyone, it does not exist in
this schema rather than being blanked at render time.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "PromotePublicProfileRequest",
    "PublicEvidenceResponse",
    "PublicProfileMeta",
    "PublicProfileResponse",
    "PublicSettingsResponse",
    "PublicSkillResponse",
    "PublicProjectResponse",
    "UpdatePublicSettingsRequest",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class PublicEvidenceResponse(_CamelModel):
    """One clickable piece of evidence. ``url`` is omitted when the material is not linkable."""

    evidence_id: str = Field(alias="evidenceId")
    title: str
    kind: str
    locator: str = ""
    url: str | None = None
    confidence: float = 0.0


class PublicSkillResponse(_CamelModel):
    canonical_id: str = Field(alias="canonicalId")
    display_name: str = Field(alias="displayName")
    category: str = "unknown"
    confidence: float = 0.0
    evidence_count: int = Field(default=0, alias="evidenceCount")
    corroboration: int = 0
    evidence: list[PublicEvidenceResponse] = Field(default_factory=list)


class PublicProjectResponse(_CamelModel):
    name: str
    role: str | None = None
    summary: str = ""
    tech_stack: list[str] = Field(default_factory=list, alias="techStack")
    repository_url: str | None = Field(default=None, alias="repositoryUrl")
    highlights: list[str] = Field(default_factory=list)


class PublicProfileMeta(_CamelModel):
    """What the reader needs to interpret the page."""

    slug: str
    generated_at: datetime | None = Field(default=None, alias="generatedAt")
    #: Share of the shown skills that carry at least one piece of evidence.
    evidence_coverage: float = Field(default=0.0, alias="evidenceCoverage")
    profile_strength: float = Field(default=0.0, alias="profileStrength")
    #: Sections that are hidden right now, so the page can say "3 sections are private" instead
    #: of silently showing less.
    hidden_sections: list[str] = Field(default_factory=list, alias="hiddenSections")
    #: What was masked and why. A page that quietly removed something is indistinguishable from
    #: a page that never had it.
    redactions: list[dict[str, str]] = Field(default_factory=list)
    view_count: int = Field(default=0, alias="viewCount")


class PublicProfileResponse(_CamelModel):
    """``GET /public/candidate/{slug}`` — no authentication, no owner-only fields."""

    display_name: str = Field(alias="displayName")
    headline: str = ""
    location: str | None = None
    summary: str = ""
    target_roles: list[str] = Field(default_factory=list, alias="targetRoles")
    skills: list[PublicSkillResponse] = Field(default_factory=list)
    projects: list[PublicProjectResponse] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    interview_topics: list[str] = Field(default_factory=list, alias="interviewTopics")
    github_url: str | None = Field(default=None, alias="githubUrl")
    website_url: str | None = Field(default=None, alias="websiteUrl")
    contact: dict[str, str] = Field(default_factory=dict)
    meta: PublicProfileMeta


class PublicSettingsResponse(_CamelModel):
    """``GET /public/settings`` — the owner's view of their publish state."""

    slug: str | None = None
    url: str | None = None
    is_published: bool = Field(default=False, alias="isPublished")
    published_at: datetime | None = Field(default=None, alias="publishedAt")
    view_count: int = Field(default=0, alias="viewCount")
    sections: dict[str, bool] = Field(default_factory=dict)
    hidden_skills: list[str] = Field(default_factory=list, alias="hiddenSkills")
    can_publish: bool = Field(default=True, alias="canPublish")
    pii_findings: list[dict[str, Any]] = Field(default_factory=list, alias="piiFindings")


class PromotePublicProfileRequest(_CamelModel):
    """``POST /public/publish``. ``published=false`` un-publishes."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    published: bool = True
    sections: dict[str, bool] | None = None
    slug: str | None = Field(default=None, max_length=80)


class UpdatePublicSettingsRequest(_CamelModel):
    """``PATCH /public/settings`` — the switches, and the per-skill hide list."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    sections: dict[str, bool] | None = None
    hidden_skills: list[str] | None = Field(default=None, alias="hiddenSkills", max_length=200)
