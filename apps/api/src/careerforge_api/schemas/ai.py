"""Request and response schemas for the AI endpoints.

The AI endpoints take text in the request body rather than a stored id, because the
tables those ids would point at (``jobs``, ``evidence``, ``documents``) arrive with
their own phases. That is a real limitation of the current slice, and the schemas say
so by making the caller supply the material explicitly instead of pretending it was
already ingested.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from careerforge_ai.schemas.common import CFBaseModel, InterviewMode
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile

__all__ = [
    "AnalyzeJobRequest",
    "AnalyzeJobResponse",
    "ValidateClaimRequest",
    "ValidateClaimResponse",
    "MatchRequest",
    "MatchResponse",
    "StartInterviewRequest",
    "InterviewAnswerRequest",
    "InterviewTurnResponse",
    "InterviewSessionResponse",
    "CapabilitiesResponse",
    "AiMeta",
]


class AiMeta(CFBaseModel):
    """What every AI response carries so the caller never guesses.

    ``degraded`` is not decoration: on the current deployment it is ``true`` for
    every run without an API key, and a UI that does not show that is misrepresenting
    the result.
    """

    provider: str
    model: str | None = None
    prompt_version: str | None = None
    degraded: bool = False
    degraded_reason: str | None = None
    workflow: str | None = None
    run_id: UUID | None = None
    latency_ms: int | None = None
    cache_hit: bool = False
    warnings: list[str] = Field(default_factory=list)


class AnalyzeJobRequest(CFBaseModel):
    text: str = Field(min_length=10, max_length=40_000, description="Raw job description")


class AnalyzeJobResponse(CFBaseModel):
    analysis: JDAnalysis
    meta: AiMeta


class ValidateClaimRequest(CFBaseModel):
    claim: str = Field(min_length=2, max_length=1000)
    evidence_text: str = Field(
        default="",
        max_length=20_000,
        description=(
            "Material to judge the claim against. Optional: with no evidence supplied "
            "the gate reports the claim as unsupported rather than assuming support."
        ),
    )
    job_context: str = Field(default="", max_length=2000)


class ValidateClaimResponse(CFBaseModel):
    status: str
    confidence: float
    allows_resume_inclusion: bool
    is_blocking: bool
    sources: list[dict[str, Any]] = Field(default_factory=list)
    reasons: list[dict[str, Any]] = Field(default_factory=list)
    safe_rewrite: dict[str, Any] | None = None
    unknowns: list[str] = Field(default_factory=list)
    independent_source_count: int = 0
    meta: AiMeta


class MatchRequest(CFBaseModel):
    job: JDAnalysis
    profile: CandidateProfile


class MatchResponse(CFBaseModel):
    score: float
    dimensions: dict[str, Any]
    strengths: list[dict[str, Any]] = Field(default_factory=list)
    gaps: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[dict[str, Any]] = Field(default_factory=list)
    why: dict[str, Any]
    narrative: str = ""
    evidence_coverage: float = 0.0
    meta: AiMeta


class StartInterviewRequest(CFBaseModel):
    mode: InterviewMode = InterviewMode.TECHNICAL
    job: JDAnalysis | None = None
    profile: CandidateProfile | None = None
    difficulty: int = Field(default=1, ge=1, le=3)


class InterviewAnswerRequest(CFBaseModel):
    answer: str = Field(min_length=1, max_length=8000)


class InterviewQuestion(CFBaseModel):
    turn_index: int
    content: str
    topic: str | None = None
    level: str | None = None


class InterviewTurnResponse(CFBaseModel):
    session_id: UUID
    status: str
    current_level: str
    evaluation: dict[str, Any] | None = None
    difficulty_change: dict[str, Any] | None = None
    next_question: InterviewQuestion | None = None
    meta: AiMeta


class InterviewSessionResponse(CFBaseModel):
    session_id: UUID
    mode: str
    status: str
    current_level: str
    plan: list[dict[str, Any]] = Field(default_factory=list)
    turns: list[dict[str, Any]] = Field(default_factory=list)
    scorecard: dict[str, Any] | None = None
    meta: AiMeta


class CapabilitiesResponse(CFBaseModel):
    """What the agent layer can do, and what it cannot yet.

    ``limitations`` is part of the payload on purpose. An endpoint catalog that only
    lists capabilities invites a caller to assume the missing half works.
    """

    agents: list[dict[str, str]]
    provider: str
    provider_chain: list[str]
    degraded: bool
    retrieval_available: bool
    session_store: str
    active_interview_sessions: int
    limitations: list[str] = Field(default_factory=list)
