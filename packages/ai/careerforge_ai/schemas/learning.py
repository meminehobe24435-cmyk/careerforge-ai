"""Skill gap and learning-plan schemas.

The design rule worth noting: every gap must produce a **mini project** the
candidate can build and then point at as evidence. A course link does not fix a
gap in this system — a provable artefact does.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from careerforge_ai.schemas.common import CFBaseModel, StrictModel, utcnow

__all__ = [
    "ExtractedLearningPlan",
    "ExtractedLearningWeek",
    "ExtractedMiniProject",
    "LearningPlan",
    "LearningPlanWeek",
    "MiniProject",
]


class MiniProject(CFBaseModel):
    """A small, shippable artefact that closes a skill gap *and* creates evidence."""

    title: str
    skill_canonical_id: str = ""
    description: str = ""
    deliverables: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    evidence_potential: str = Field(
        default="", description="What it will let the candidate truthfully claim afterwards"
    )
    estimated_hours: float | None = Field(default=None, ge=0)


class LearningPlanWeek(CFBaseModel):
    week: int = Field(ge=1, le=12)
    theme: str
    goals: list[str] = Field(default_factory=list)
    focus_skills: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    output: str = Field(default="", description="What must exist by the end of the week")
    verification: str = Field(default="", description="How the candidate proves the week worked")


class LearningPlan(CFBaseModel):
    """A 30-day plan derived from a skill gap matrix."""

    user_id: UUID | None = None
    job_id: UUID | None = None
    horizon_days: int = Field(default=30, ge=7, le=180)
    title: str = ""
    summary: str = ""
    weeks: list[LearningPlanWeek] = Field(default_factory=list)
    mini_projects: list[MiniProject] = Field(default_factory=list)
    priority_order: list[str] = Field(
        default_factory=list, description="Canonical skill ids, highest priority first"
    )
    source_gap_ids: list[UUID] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=utcnow)
    model: str | None = None
    prompt_version: str | None = None
    degraded: bool = False

    @property
    def total_hours(self) -> float:
        return round(sum(project.estimated_hours or 0 for project in self.mini_projects), 1)


# ── LLM-facing contracts ─────────────────────────────────────────────────────


class ExtractedMiniProject(StrictModel):
    title: str = Field(description="Concrete, buildable project title")
    skill_canonical_id: str = Field(default="", description="The gap this project closes")
    description: str = Field(default="", description="Two sentences on what to build")
    deliverables: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    evidence_potential: str = Field(
        default="",
        description="The exact claim this artefact would let the candidate prove afterwards",
    )
    estimated_hours: float | None = None


class ExtractedLearningWeek(StrictModel):
    week: int = Field(description="1-based week number")
    theme: str
    goals: list[str] = Field(default_factory=list)
    focus_skills: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    output: str = Field(default="", description="A concrete artefact, not 'understanding'")
    verification: str = Field(default="", description="How the week is verified as done")


class ExtractedLearningPlan(StrictModel):
    title: str = ""
    summary: str = ""
    weeks: list[ExtractedLearningWeek] = Field(default_factory=list)
    mini_projects: list[ExtractedMiniProject] = Field(default_factory=list)
    priority_order: list[str] = Field(
        default_factory=list, description="Canonical skill ids ordered by priority"
    )
