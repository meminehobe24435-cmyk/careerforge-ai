"""Job and match models: ``/jobs`` (``docs/API.md`` §2.6).

The match payload keeps the documented shape: five dimensions each with its weight and its
weighted contribution, so the arithmetic on screen adds up to the score. ``why.formula``
carries the actual formula, not a description of it — a reader can check the sum.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AnalyzeJobRequest",
    "JobDetail",
    "JobListResponse",
    "JobResponse",
    "JobSkillResponse",
    "MatchDimensionResponse",
    "MatchResponse",
    "MatchedSkillResponse",
    "MissedSkillResponse",
    "UnknownSkillResponse",
    "SkillTreeResponse",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class AnalyzeJobRequest(_CamelModel):
    """``POST /jobs/analyze`` body.

    Unknown fields are refused: this endpoint accepts a posting, and a client that sends
    something else should be told rather than have it ignored.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True, extra="forbid")

    text: str = Field(min_length=1, max_length=200_000, description="The job description")
    source: str = Field(default="paste", description="paste | upload | url | manual")
    source_url: str | None = Field(default=None, alias="sourceUrl")


class JobSkillResponse(_CamelModel):
    """One requirement, with the JD sentence that justifies it."""

    canonical_id: str | None = Field(default=None, alias="canonicalId")
    raw_text: str = Field(alias="rawText")
    requirement: str
    weight: float = 1.0
    jd_evidence: str = Field(default="", alias="jdEvidence")
    mentions: int = 1

    @classmethod
    def from_row(cls, row: Any) -> JobSkillResponse:
        return cls(
            canonical_id=row.canonical_id,
            raw_text=row.raw_text,
            requirement=row.requirement,
            weight=float(row.weight),
            jd_evidence=row.jd_evidence,
            mentions=row.mentions,
        )


class JobResponse(_CamelModel):
    """A posting in a list — the card, not the whole posting."""

    id: str
    company: str | None = None
    role: str
    level: str | None = None
    location: str | None = None
    remote_type: str | None = Field(default=None, alias="remoteType")
    employment_type: str | None = Field(default=None, alias="employmentType")
    salary_min: float | None = Field(default=None, alias="salaryMin")
    salary_max: float | None = Field(default=None, alias="salaryMax")
    salary_currency: str | None = Field(default=None, alias="salaryCurrency")
    education_requirement: str | None = Field(default=None, alias="educationRequirement")
    years_experience_min: float | None = Field(default=None, alias="yearsExperienceMin")
    parse_status: str = Field(default="parsed", alias="parseStatus")
    parse_confidence: float = Field(default=0.0, alias="parseConfidence")
    source: str = "paste"
    required_count: int = Field(default=0, alias="requiredCount")
    preferred_count: int = Field(default=0, alias="preferredCount")
    bonus_count: int = Field(default=0, alias="bonusCount")
    #: The newest match score, or ``None`` when this job has never been matched.
    match_score: float | None = Field(default=None, alias="matchScore")
    created_at: datetime | None = Field(default=None, alias="createdAt")

    @classmethod
    def from_row(cls, row: Any, *, match_score: float | None = None) -> JobResponse:
        return cls(
            id=str(row.id),
            company=row.company_name_raw,
            role=row.role,
            level=row.level,
            location=row.location,
            remote_type=row.remote_type,
            employment_type=row.employment_type,
            salary_min=float(row.salary_min) if row.salary_min is not None else None,
            salary_max=float(row.salary_max) if row.salary_max is not None else None,
            salary_currency=row.salary_currency,
            education_requirement=row.education_requirement,
            years_experience_min=(
                float(row.years_experience_min) if row.years_experience_min is not None else None
            ),
            parse_status=row.parse_status,
            parse_confidence=float(row.parse_confidence),
            source=row.source,
            required_count=len(row.skills_at("required")),
            preferred_count=len(row.skills_at("preferred")),
            bonus_count=len(row.skills_at("bonus")),
            match_score=match_score,
            created_at=row.created_at,
        )


class JobDetail(JobResponse):
    """``GET /jobs/{id}`` — adds the parsed analysis and every requirement row."""

    responsibilities: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list, alias="niceToHave")
    keywords: list[str] = Field(default_factory=list)
    skills: list[JobSkillResponse] = Field(default_factory=list)
    #: The parser's own output, verbatim — the audit record behind the normalised columns.
    analysis: dict[str, Any] = Field(default_factory=dict)
    description_chars: int = Field(default=0, alias="descriptionChars")

    @classmethod
    def from_row(
        cls, row: Any, *, match_score: float | None = None, include_raw: bool = False
    ) -> JobDetail:
        base = JobResponse.from_row(row, match_score=match_score)
        return cls(
            **base.model_dump(),
            responsibilities=[str(item) for item in row.responsibilities or []],
            nice_to_have=[str(item) for item in row.nice_to_have or []],
            keywords=[str(item) for item in row.keywords or []],
            skills=[JobSkillResponse.from_row(skill) for skill in row.skills],
            analysis=dict(row.analysis or {}) if include_raw else {},
            description_chars=len(row.description_raw or ""),
        )


class JobListResponse(_CamelModel):
    items: list[JobResponse] = Field(default_factory=list)
    total: int = 0


class SkillTreeResponse(_CamelModel):
    """``GET /jobs/{id}/skill-tree`` — the three documented levels."""

    job_id: str = Field(alias="jobId")
    role: str = ""
    company: str | None = None
    required: list[JobSkillResponse] = Field(default_factory=list)
    preferred: list[JobSkillResponse] = Field(default_factory=list)
    bonus: list[JobSkillResponse] = Field(default_factory=list)
    #: Requirements the taxonomy could not normalise. Reported so the UI can show them as
    #: raw text rather than pretending they matched nothing.
    unmatched_count: int = Field(default=0, alias="unmatchedCount")


class MatchDimensionResponse(_CamelModel):
    key: str
    label: str
    score: float
    weight: float
    weighted: float
    formula: str = ""
    notes: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")


class MatchWhyResponse(_CamelModel):
    formula: str = ""
    algorithm_version: str = Field(default="match@1.0.0", alias="algorithmVersion")
    evidence_used: list[str] = Field(default_factory=list, alias="evidenceUsed")
    notes: list[str] = Field(default_factory=list)
    explanation: str = ""
    computed_at: datetime | None = Field(default=None, alias="computedAt")


class MatchedSkillResponse(_CamelModel):
    """A requirement the candidate meets, and why the engine thinks so."""

    canonical_id: str = Field(alias="canonicalId")
    display_name: str = Field(alias="displayName")
    requirement: str
    user_level: str = Field(default="none", alias="userLevel")
    evidence_count: int = Field(default=0, alias="evidenceCount")
    confidence: float = 0.0
    reason: str = ""


class MissedSkillResponse(_CamelModel):
    """A requirement with nothing behind it — the honest part of the report."""

    canonical_id: str = Field(alias="canonicalId")
    display_name: str = Field(alias="displayName")
    requirement: str
    severity: str = "medium"
    jd_evidence: str = Field(default="", alias="jdEvidence")


class UnknownSkillResponse(_CamelModel):
    """A requirement the engine cannot place: the candidate may or may not have it, and
    the honest answer is a question rather than a guess."""

    canonical_id: str = Field(alias="canonicalId")
    display_name: str = Field(alias="displayName")
    requirement: str
    reason: str = ""
    ask_user: str = Field(default="", alias="askUser")


class MatchResponse(_CamelModel):
    """``POST /jobs/{id}/match`` and ``GET /jobs/{id}/match``.

    ``strengths``, ``gaps`` and ``unknowns`` are modelled rather than passed through as the
    engine's dicts: the engine speaks snake_case, the wire speaks camelCase, and a client
    that had to special-case three nested lists would be right to call that a bug.
    """

    job_id: str = Field(alias="jobId")
    score: float
    dimensions: dict[str, MatchDimensionResponse] = Field(default_factory=dict)
    strengths: list[MatchedSkillResponse] = Field(default_factory=list)
    gaps: list[MissedSkillResponse] = Field(default_factory=list)
    unknowns: list[UnknownSkillResponse] = Field(default_factory=list)
    why: MatchWhyResponse = Field(default_factory=MatchWhyResponse)
    evidence_coverage: float = Field(default=0.0, alias="evidenceCoverage")
    confidence: float = 0.0
    degraded: bool = False
    narrative: str = ""
    #: Set when the evidence dimension had nothing to measure — the one warning a reader
    #: must not miss, because it changes what the score means.
    warnings: list[str] = Field(default_factory=list)
