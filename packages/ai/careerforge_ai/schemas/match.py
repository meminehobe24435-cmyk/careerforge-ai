"""Explainable job match scoring schemas.

The score is produced by a **deterministic** engine (ADR-006). These models
carry not just the number but the full derivation, because a number a user
cannot interrogate is a number they cannot act on.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from careerforge_ai.schemas.common import (
    CFBaseModel,
    Confidence,
    GapLevel,
    RequirementLevel,
    Score0to100,
    SkillLevel,
    StrictModel,
    Unit,
    utcnow,
)

__all__ = [
    "JobMatchResult",
    "MatchDimension",
    "MatchDimensionKey",
    "MatchWhy",
    "MatchedSkill",
    "MissedSkill",
    "UnknownSkill",
]


class MatchDimensionKey:
    """Dimension identifiers — stable strings persisted with every score."""

    SKILL = "skill"
    EXPERIENCE = "experience"
    PROJECT = "project"
    EDUCATION = "education"
    EVIDENCE = "evidence"

    ALL: tuple[str, ...] = (SKILL, EXPERIENCE, PROJECT, EDUCATION, EVIDENCE)
    LABELS: dict[str, str] = {
        SKILL: "技能匹配",
        EXPERIENCE: "经历匹配",
        PROJECT: "项目匹配",
        EDUCATION: "学历匹配",
        EVIDENCE: "证据强度",
    }


class MatchedSkill(CFBaseModel):
    canonical_id: str
    display_name: str
    requirement: RequirementLevel
    user_level: SkillLevel
    evidence_count: int = 0
    confidence: Confidence = 0.0
    reason: str = ""


class MissedSkill(CFBaseModel):
    """A skill the job requires and the candidate does not have."""

    canonical_id: str
    display_name: str
    requirement: RequirementLevel
    severity: GapLevel
    jd_evidence: str = ""


class UnknownSkill(CFBaseModel):
    """A skill we genuinely cannot judge.

    Kept strictly separate from :class:`MissedSkill`: "the resume never mentions
    it" is not the same fact as "the candidate cannot do it", and conflating the
    two is one of the most user-hostile mistakes an automated screener can make.
    """

    canonical_id: str
    display_name: str
    requirement: RequirementLevel
    reason: str
    ask_user: str = Field(description="Question shown to the user to resolve the ambiguity")


class MatchDimension(CFBaseModel):
    """One scored dimension of the match, with its inputs and provenance."""

    key: str
    label: str
    score: Score0to100
    weight: Unit
    weighted: Score0to100 = Field(description="score × weight, i.e. its contribution to the total")
    formula: str = Field(description="Human-readable formula actually used")
    notes: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class MatchWhy(CFBaseModel):
    """The payload behind the UI's ``Why 86?`` expansion."""

    formula: str = Field(
        default="0.40·skill + 0.25·experience + 0.20·project + 0.05·education + 0.10·evidence"
    )
    dimensions: list[MatchDimension] = Field(default_factory=list)
    evidence_used: list[UUID] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    algorithm_version: str = "match@1.0.0"
    computed_at: datetime = Field(default_factory=utcnow)
    explanation: str = Field(default="", description="Plain-language summary of the derivation")

    def dimension(self, key: str) -> MatchDimension | None:
        return next((dim for dim in self.dimensions if dim.key == key), None)

    def contribution_total(self) -> float:
        return round(sum(dim.weighted for dim in self.dimensions), 4)


class JobMatchResult(CFBaseModel):
    """Complete, explainable match outcome."""

    job_id: UUID | None = None
    user_id: UUID | None = None
    score: Score0to100
    dimensions: dict[str, MatchDimension] = Field(
        default_factory=dict, description="Keyed by :class:`MatchDimensionKey`"
    )

    strengths: list[MatchedSkill] = Field(default_factory=list)
    gaps: list[MissedSkill] = Field(default_factory=list)
    unknowns: list[UnknownSkill] = Field(default_factory=list)

    why: MatchWhy
    evidence_coverage: Unit = Field(
        default=0.0, description="Share of required skills backed by at least one piece of evidence"
    )
    confidence: Confidence = Field(
        default=0.0, description="How much we trust this score, given evidence density"
    )
    degraded: bool = False
    narrative: str = Field(default="", description="LLM-written summary; never contains numbers")

    def dimension_score(self, key: str) -> float:
        dim = self.dimensions.get(key)
        return dim.score if dim else 0.0

    @property
    def top_gaps(self) -> list[MissedSkill]:
        order = {GapLevel.HIGH: 0, GapLevel.MEDIUM: 1, GapLevel.LOW: 2, GapLevel.NONE: 3}
        return sorted(self.gaps, key=lambda gap: order.get(gap.severity, 9))


class ExtractedMatchNarrative(StrictModel):
    """LLM-facing narrative about a score that has **already been computed**.

    There is deliberately no numeric field. The score and every dimension score come
    from a deterministic engine, and a real model asked to "summarise 86" will round
    it, restate it wrongly, or invent a nearby number. Removing the possibility from
    the schema is more reliable than instructing the model not to do it.
    """

    summary: str = Field(
        default="",
        description=(
            "Two to four sentences on where the candidate stands and the single most "
            "valuable next action. Do not state, restate or recompute any number."
        ),
    )
    caveats: list[str] = Field(
        default_factory=list,
        description=(
            "Interpretation caveats worth showing, e.g. a required skill that carries "
            "no supporting evidence"
        ),
    )
