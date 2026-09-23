"""Schemas for the public candidate profile (Recruiter View).

The public page is the one surface a stranger sees, so its contract makes two
things explicit that the rest of the system keeps internal: **which sections are
visible**, and **what was redacted**. Neither is a boolean hidden in the database —
both travel with the payload so the UI cannot accidentally render something the
candidate did not publish.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from careerforge_ai.schemas.common import (
    CFBaseModel,
    Confidence,
    Score0to100,
    StrictModel,
    utcnow,
)

__all__ = [
    "PublicSectionVisibility",
    "PublicSkill",
    "PublicProject",
    "PublicEvidenceLink",
    "PublicProfileSummary",
    "ExtractedRecruiterSummary",
]


class PublicSectionVisibility(CFBaseModel):
    """Per-section publish switches. Defaults are deliberately conservative.

    Contact details default to hidden: a candidate publishing their evidence is not
    the same as a candidate publishing their phone number, and defaulting to visible
    would make the difference invisible until someone scraped it.
    """

    summary: bool = True
    skills: bool = True
    projects: bool = True
    evidence: bool = True
    highlights: bool = True
    interview_topics: bool = True
    contact: bool = False
    resume_file: bool = False

    @property
    def visible_count(self) -> int:
        return sum(
            1
            for value in (
                self.summary,
                self.skills,
                self.projects,
                self.evidence,
                self.highlights,
                self.interview_topics,
                self.contact,
                self.resume_file,
            )
            if value
        )


class PublicEvidenceLink(CFBaseModel):
    """A clickable piece of evidence behind a public skill."""

    evidence_id: UUID
    title: str
    kind: str
    locator_display: str = ""
    url: str | None = None
    confidence: Confidence = 0.0


class PublicSkill(CFBaseModel):
    """A skill as shown to a recruiter: with evidence, not just a name."""

    canonical_id: str
    display_name: str
    category: str = "unknown"
    confidence: Confidence = 0.0
    evidence_count: int = 0
    corroboration: int = Field(
        default=0, description="Number of independent source groups supporting it"
    )
    evidence: list[PublicEvidenceLink] = Field(default_factory=list)

    @property
    def is_backed(self) -> bool:
        return self.evidence_count > 0


class PublicProject(CFBaseModel):
    name: str
    role: str | None = None
    summary: str = ""
    tech_stack: list[str] = Field(default_factory=list)
    repository_url: str | None = None
    highlights: list[str] = Field(default_factory=list)


class PublicProfileSummary(CFBaseModel):
    """Everything the public page renders, already filtered and redacted."""

    slug: str
    display_name: str = Field(description="Display name or headline; never the legal name")
    headline: str = ""
    location: str | None = None
    summary: str = ""
    target_roles: list[str] = Field(default_factory=list)

    skills: list[PublicSkill] = Field(default_factory=list)
    projects: list[PublicProject] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    interview_topics: list[str] = Field(default_factory=list)

    github_url: str | None = None
    website_url: str | None = None
    contact: dict[str, str] = Field(
        default_factory=dict, description="Populated only when the candidate publishes contact"
    )

    visibility: PublicSectionVisibility = Field(default_factory=PublicSectionVisibility)
    redactions: list[dict[str, str]] = Field(
        default_factory=list, description="What was removed and why, so the page can say so"
    )

    evidence_coverage: Confidence = Field(
        default=0.0, description="Share of shown skills backed by at least one piece of evidence"
    )
    profile_strength: Score0to100 = 0.0

    generated_at: datetime = Field(default_factory=utcnow)
    degraded: bool = False

    @property
    def backed_skills(self) -> list[PublicSkill]:
        return [skill for skill in self.skills if skill.is_backed]


class ExtractedRecruiterSummary(StrictModel):
    """LLM-facing summary for the public page.

    The prompt tells the model that everything here is clickable back to its
    evidence. The schema keeps that constraint honest by offering no place to put a
    number, a ranking or an adjective about the person.
    """

    summary: str = Field(
        default="",
        description=(
            "Three to four sentences describing the work, traced to the supplied "
            "material. No adjectives about the person."
        ),
    )
    highlights: list[str] = Field(
        default_factory=list,
        description="3–5 concrete technical statements a recruiter could ask a follow-up about",
    )
    interview_topics: list[str] = Field(
        default_factory=list,
        description="Areas this candidate can genuinely be probed on, derived from the material",
    )
