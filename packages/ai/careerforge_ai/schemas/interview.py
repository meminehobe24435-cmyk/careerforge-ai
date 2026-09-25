"""Interview simulator schemas: plans, turns, adaptive difficulty and scorecards."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import Field

from careerforge_ai.schemas.common import (
    CFBaseModel,
    DifficultyLevel,
    InterviewMode,
    InterviewStatus,
    Score0to100,
    StrictModel,
    Unit,
    utcnow,
)

__all__ = [
    "DifficultyChange",
    "EvidenceConflict",
    "ExtractedQuestion",
    "ExtractedTurnEvaluation",
    "InterviewPlanItem",
    "InterviewScorecard",
    "InterviewSession",
    "InterviewTurn",
    "QuestionReview",
    "ScorecardDimension",
    "TurnEvaluation",
]


class InterviewPlanItem(CFBaseModel):
    """One topic the interviewer intends to probe, and why."""

    topic: str
    label: str = ""
    target_level: DifficultyLevel = DifficultyLevel.CONCEPT
    reason: str = Field(
        default="", description="Which job requirement or piece of evidence motivates this topic"
    )
    source: str = Field(default="evidence", description="jt_requirement | evidence | resume | gap")
    source_ids: list[UUID] = Field(default_factory=list)
    #: Whether an interviewer turn has actually asked about this topic. **Derived, not
    #: declared**: ``mark_plan_coverage`` writes it from the turns that were asked, so it is
    #: ``False`` only while the topic is still unasked. Before PHASE 14 nothing wrote it and it
    #: read ``False`` on a topic the interview had already spent three questions on.
    covered: bool = False


class InterviewTurn(CFBaseModel):
    """A single question/answer exchange."""

    turn_index: int = Field(ge=0)
    role: str = Field(description="interviewer | candidate | system")
    content: str
    topic: str | None = None
    question_level: DifficultyLevel | None = None
    evaluation: TurnEvaluation | None = None
    #: ``None`` when the turn was built without measuring them — which is every turn today: the
    #: interviewer's question is produced inside a workflow whose real usage is recorded on the
    #: step trace. ``0`` here used to mean "we did not look", which is not a measurement.
    tokens: int | None = None
    latency_ms: int | None = None
    created_at: datetime = Field(default_factory=utcnow)


class TurnEvaluation(CFBaseModel):
    """Per-answer assessment. Shown inline so the candidate learns immediately."""

    turn_index: int
    score: Score0to100 = 0.0
    technical_accuracy: Unit = 0.0
    depth: Unit = 0.0
    communication: Unit = 0.0
    #: Measured per answer rather than derived from another dimension. Deriving a
    #: reported score from an unrelated one is quiet fabrication.
    problem_solving: Unit = 0.0
    engineering_thinking: Unit = 0.0
    confidence: Unit = 0.0

    missing_knowledge: list[str] = Field(default_factory=list)
    feedback: str = ""
    strong_points: list[str] = Field(default_factory=list)
    follow_up_topics: list[str] = Field(default_factory=list)
    suggested_answer: str = Field(default="", description="A model answer, revealed after the turn")


class DifficultyChange(CFBaseModel):
    """Why the next question is harder or easier — makes adaptivity visible."""

    from_level: DifficultyLevel
    to_level: DifficultyLevel
    reason: str


class ScorecardDimension(CFBaseModel):
    key: str
    label: str
    score: Score0to100
    comment: str = ""


class EvidenceConflict(CFBaseModel):
    """A statement made in the interview that conflicts with the evidence graph.

    This is a capability almost no interview tool has: the resume, the evidence
    base and the spoken answer are cross-checked against each other, so the
    candidate learns about a credibility risk *before* a real interviewer finds it.
    """

    statement: str
    evidence_state: str
    severity: str = Field(default="medium", description="low | medium | high")
    advice: str = ""


class QuestionReview(CFBaseModel):
    turn_index: int
    topic: str = ""
    level: DifficultyLevel | None = None
    verdict: str = Field(default="mixed", description="strong | mixed | weak")
    question: str = ""
    answer: str = ""
    suggested_answer: str = ""
    missing_knowledge: list[str] = Field(default_factory=list)
    follow_up_topics: list[str] = Field(default_factory=list)


class InterviewScorecard(CFBaseModel):
    """The seven-dimension report."""

    interview_id: UUID | None = None
    mode: InterviewMode = InterviewMode.TECHNICAL
    overall_score: Score0to100 = 0.0
    dimensions: list[ScorecardDimension] = Field(default_factory=list)

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    missing_knowledge: list[str] = Field(default_factory=list)
    follow_up_topics: list[str] = Field(default_factory=list)
    evidence_conflicts: list[EvidenceConflict] = Field(default_factory=list)
    per_question: list[QuestionReview] = Field(default_factory=list)

    difficulty_start: DifficultyLevel = DifficultyLevel.CONCEPT
    difficulty_end: DifficultyLevel = DifficultyLevel.CONCEPT
    #: Wall-clock length of the session, from ``InterviewSession.started_at`` to
    #: ``completed_at``. ``None`` when the session was never closed, because "not finished" is
    #: not "finished in zero seconds" — which is what this field reported before PHASE 14.
    duration_seconds: int | None = None
    generated_at: datetime = Field(default_factory=utcnow)
    algorithm_version: str = "scorecard@1.0.0"

    #: Canonical dimension keys, in the order shown on the radar chart.
    #: A ClassVar so it stays a class constant rather than becoming a Pydantic field.
    DIMENSION_KEYS: ClassVar[tuple[str, ...]] = (
        "technical_accuracy",
        "communication",
        "depth",
        "problem_solving",
        "engineering_thinking",
        "confidence",
        "evidence_consistency",
    )

    def dimension(self, key: str) -> ScorecardDimension | None:
        return next((dim for dim in self.dimensions if dim.key == key), None)

    @property
    def is_complete(self) -> bool:
        return len(self.dimensions) == len(self.DIMENSION_KEYS)


class InterviewSession(CFBaseModel):
    """State of an interview, enough to resume it after a reload."""

    id: UUID | None = None
    mode: InterviewMode = InterviewMode.TECHNICAL
    status: InterviewStatus = InterviewStatus.PLANNED
    job_id: UUID | None = None
    project_id: UUID | None = None
    plan: list[InterviewPlanItem] = Field(default_factory=list)
    turns: list[InterviewTurn] = Field(default_factory=list)
    current_level: DifficultyLevel = DifficultyLevel.CONCEPT
    scorecard: InterviewScorecard | None = None
    started_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = None
    model: str | None = None

    @property
    def turn_count(self) -> int:
        return len([turn for turn in self.turns if turn.role == "interviewer"])

    def next_turn_index(self) -> int:
        return len(self.turns)


# ── LLM-facing contracts ─────────────────────────────────────────────────────


class ExtractedQuestion(StrictModel):
    """One generated interview question."""

    question: str = Field(description="The question, in the interviewer's voice")
    topic: str = Field(description="Short topic label, e.g. 'freertos' or 'spi_debugging'")
    level: DifficultyLevel = Field(
        default=DifficultyLevel.CONCEPT,
        description="concept = definitional; engineering = design and trade-offs; debugging = diagnose a symptom",
    )
    rationale: str = Field(
        default="", description="Why this question, given the candidate's material"
    )
    follow_up_hints: list[str] = Field(
        default_factory=list, description="Deeper directions if the answer is strong"
    )


class ExtractedTurnEvaluation(StrictModel):
    """LLM-facing assessment of one answer.

    Note: the model supplies sub-scores on 0–100, which the engine clamps and
    aggregates deterministically. It never sets the final scorecard numbers.
    """

    technical_accuracy: float = Field(default=0.0, description="0–100")
    depth: float = Field(default=0.0, description="0–100")
    communication: float = Field(default=0.0, description="0–100")
    problem_solving: float = Field(default=0.0, description="0–100")
    engineering_thinking: float = Field(default=0.0, description="0–100")
    confidence: float = Field(
        default=0.0,
        description="0–100. How assured the delivery was, judged from hedging and self-correction, "
        "not from whether the answer was right.",
    )
    missing_knowledge: list[str] = Field(default_factory=list)
    strong_points: list[str] = Field(default_factory=list)
    feedback: str = Field(default="", description="Two sentences, addressed to the candidate")
    follow_up_topics: list[str] = Field(default_factory=list)
    suggested_answer: str = Field(default="", description="A model answer in 3–5 sentences")
    evidence_conflicts: list[str] = Field(
        default_factory=list,
        description="Any statement in the answer that contradicts the provided resume/evidence material",
    )
