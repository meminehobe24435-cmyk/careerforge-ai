"""Shared schema primitives and domain enums.

Every enum here is mirrored by a ``CHECK`` constraint in the database
(``docs/DATABASE.md`` §1.1) and by a TypeScript union in
``packages/shared``. Tests assert the three stay in sync.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApplicationStatus",
    "CFBaseModel",
    "ClaimRuleCode",
    "ClaimStatus",
    "Confidence",
    "DegradationReason",
    "EvidenceKind",
    "EvidenceRelation",
    "EvidenceStrength",
    "GapLevel",
    "GraphNodeType",
    "InterviewMode",
    "InterviewStatus",
    "Origin",
    "RequirementLevel",
    "RetrievalChannel",
    "Score0to100",
    "SkillCategory",
    "SkillLevel",
    "SourceAuthority",
    "StrictModel",
    "Unit",
    "new_id",
    "utcnow",
]


def utcnow() -> datetime:
    """Timezone-aware UTC now.

    A single helper avoids the classic naive/aware comparison bugs that show up
    the moment a timestamp crosses a database boundary.
    """
    return datetime.now(UTC)


def new_id() -> UUID:
    return uuid4()


#: Probability-like value, strictly within [0, 1].
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
#: Human-facing score on a 0–100 scale.
Score0to100 = Annotated[float, Field(ge=0.0, le=100.0)]
#: Unit-interval weight or ratio.
Unit = Annotated[float, Field(ge=0.0, le=1.0)]


class CFBaseModel(BaseModel):
    """Base model for internal domain objects.

    ``extra="forbid"`` is used for objects *we* construct, so that a typo in an
    internal call site fails loudly instead of silently dropping data.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        frozen=False,
        str_strip_whitespace=True,
    )


class StrictModel(BaseModel):
    """Base model for *LLM-produced* structured output.

    ``extra="ignore"`` is deliberate: models occasionally add an extra key even
    under a JSON schema, and discarding it is safer than failing an otherwise
    usable response. Unknown fields are still surfaced by the observability layer
    so drift is visible rather than invisible.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


# ── Evidence ─────────────────────────────────────────────────────────────────


class EvidenceKind(StrEnum):
    """Where a piece of evidence came from."""

    REPO_FILE = "repo_file"
    COMMIT = "commit"
    README = "readme"
    DOCUMENT_CHUNK = "document_chunk"
    EXPERIENCE = "experience"
    PROJECT = "project"
    ACHIEVEMENT = "achievement"
    MANUAL = "manual"
    LLM_INFERENCE = "llm_inference"


class SourceAuthority(StrEnum):
    """Authority tier of an evidence source, mapped to a numeric score.

    Code and commits outrank prose; a self-report in a resume outranks only an
    LLM inference. See ``scoring.confidence.AUTHORITY_SCORES``.
    """

    CODE_OR_COMMIT = "code_or_commit"
    README = "readme"
    UPLOADED_DOCUMENT = "uploaded_document"
    RESUME_SELF_REPORT = "resume_self_report"
    LLM_INFERENCE = "llm_inference"


class GraphNodeType(StrEnum):
    CANDIDATE = "candidate"
    EDUCATION = "education"
    EXPERIENCE = "experience"
    PROJECT = "project"
    ACHIEVEMENT = "achievement"
    REPOSITORY = "repository"
    REPO_FILE = "repo_file"
    COMMIT = "commit"
    DOCUMENT = "document"
    SKILL = "skill"
    CLAIM = "claim"
    JOB = "job"
    INTERVIEW = "interview"


class EvidenceRelation(StrEnum):
    """Edge semantics of the evidence graph."""

    HAS = "HAS"
    DEMONSTRATES = "DEMONSTRATES"
    EVIDENCED_BY = "EVIDENCED_BY"
    SUPPORTS = "SUPPORTS"
    REQUIRES = "REQUIRES"
    MATCHES = "MATCHES"
    GAP = "GAP"
    DERIVED_FROM = "DERIVED_FROM"


class RetrievalChannel(StrEnum):
    """Which retrieval arm produced a hit — shown in the UI for explainability."""

    SEMANTIC = "semantic"
    KEYWORD = "keyword"
    BOTH = "both"
    METADATA = "metadata"
    MANUAL = "manual"


# ── Claims ───────────────────────────────────────────────────────────────────


class ClaimStatus(StrEnum):
    """Outcome of validating a resume claim against the evidence base."""

    PENDING = "pending"
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"

    @property
    def allows_resume_inclusion(self) -> bool:
        """Whether the claim may be written to a resume without user override."""
        return self in {ClaimStatus.SUPPORTED, ClaimStatus.PARTIALLY_SUPPORTED}

    @property
    def is_blocking(self) -> bool:
        return self in {ClaimStatus.UNSUPPORTED, ClaimStatus.CONTRADICTED}


class ClaimRuleCode(StrEnum):
    """Deterministic rules that run *before* the LLM (ADR-014)."""

    NUMERIC_WITHOUT_EVIDENCE = "numeric_without_evidence"
    SUPERLATIVE_LANGUAGE = "superlative_language"
    NO_EVIDENCE_MATCH = "no_evidence_match"
    SINGLE_SOURCE_ONLY = "single_source_only"
    TIMELINE_CONFLICT = "timeline_conflict"
    SKILL_NOT_IN_GRAPH = "skill_not_in_graph"
    LOW_CONFIDENCE_SOURCES = "low_confidence_sources"
    QUANTIFIED_SKILL_UNSUPPORTED = "quantified_skill_unsupported"


# ── Skills ───────────────────────────────────────────────────────────────────


class SkillLevel(StrEnum):
    NONE = "none"
    BASIC = "basic"
    MODERATE = "moderate"
    STRONG = "strong"
    EXPERT = "expert"

    @property
    def numeric(self) -> float:
        """Deterministic mapping used by scoring; never produced by an LLM."""
        return {
            SkillLevel.NONE: 0.0,
            SkillLevel.BASIC: 0.25,
            SkillLevel.MODERATE: 0.55,
            SkillLevel.STRONG: 0.8,
            SkillLevel.EXPERT: 1.0,
        }[self]


class SkillCategory(StrEnum):
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    EMBEDDED = "embedded"
    BACKEND = "backend"
    FRONTEND = "frontend"
    AI = "ai"
    DEVOPS = "devops"
    DATABASE = "database"
    TOOL = "tool"
    DOMAIN = "domain"
    SOFT = "soft"


class RequirementLevel(StrEnum):
    """How strongly a job demands a skill, with its scoring weight."""

    REQUIRED = "required"
    PREFERRED = "preferred"
    BONUS = "bonus"

    @property
    def weight(self) -> float:
        return {
            RequirementLevel.REQUIRED: 1.0,
            RequirementLevel.PREFERRED: 0.6,
            RequirementLevel.BONUS: 0.3,
        }[self]


class EvidenceStrength(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def numeric(self) -> float:
        return {
            EvidenceStrength.NONE: 0.0,
            EvidenceStrength.LOW: 0.3,
            EvidenceStrength.MEDIUM: 0.65,
            EvidenceStrength.HIGH: 1.0,
        }[self]


class GapLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def numeric(self) -> float:
        return {
            GapLevel.NONE: 0.0,
            GapLevel.LOW: 0.3,
            GapLevel.MEDIUM: 0.65,
            GapLevel.HIGH: 1.0,
        }[self]


# ── Interview ────────────────────────────────────────────────────────────────


class InterviewMode(StrEnum):
    HR = "hr"
    TECHNICAL = "technical"
    PROJECT = "project"
    STRESS = "stress"
    BEHAVIORAL = "behavioral"
    SYSTEM_DESIGN = "system_design"


class InterviewStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class DifficultyLevel(StrEnum):
    """Adaptive interview difficulty ladder (PRD FR-10.3)."""

    CONCEPT = "concept"  # L1 — definitional / why questions
    ENGINEERING = "engineering"  # L2 — how it is built, trade-offs
    DEBUGGING = "debugging"  # L3 — diagnose a failure from symptoms

    @property
    def level(self) -> int:
        return {
            DifficultyLevel.CONCEPT: 1,
            DifficultyLevel.ENGINEERING: 2,
            DifficultyLevel.DEBUGGING: 3,
        }[self]

    @classmethod
    def from_level(cls, level: int) -> DifficultyLevel:
        clamped = max(1, min(3, level))
        return {1: cls.CONCEPT, 2: cls.ENGINEERING, 3: cls.DEBUGGING}[clamped]


# ── Platform ─────────────────────────────────────────────────────────────────


class ApplicationStatus(StrEnum):
    WISHLIST = "wishlist"
    APPLIED = "applied"
    OA = "oa"
    INTERVIEW = "interview"
    FINAL = "final"
    OFFER = "offer"
    REJECTED = "rejected"

    @property
    def is_active(self) -> bool:
        return self not in {ApplicationStatus.OFFER, ApplicationStatus.REJECTED}

    @property
    def stage_index(self) -> int:
        """Position on the funnel; used by analytics and the kanban ordering."""
        return (
            [
                ApplicationStatus.WISHLIST,
                ApplicationStatus.APPLIED,
                ApplicationStatus.OA,
                ApplicationStatus.INTERVIEW,
                ApplicationStatus.FINAL,
                ApplicationStatus.OFFER,
            ].index(self)
            if self != ApplicationStatus.REJECTED
            else -1
        )


class Origin(StrEnum):
    """Provenance of a stored fact — user corrections always win."""

    LLM = "llm"
    HEURISTIC = "heuristic"
    USER_CORRECTED = "user_corrected"
    IMPORT = "import"

    @property
    def trust_rank(self) -> int:
        return {
            Origin.LLM: 0,
            Origin.HEURISTIC: 1,
            Origin.IMPORT: 2,
            Origin.USER_CORRECTED: 3,
        }[self]


class DegradationReason(StrEnum):
    """Why a result is marked ``degraded`` — always surfaced in the UI."""

    NONE = "none"
    NO_API_KEY = "no_api_key"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_TIMEOUT = "provider_timeout"
    RATE_LIMITED = "rate_limited"
    BUDGET_EXCEEDED = "budget_exceeded"
    SCHEMA_REPAIR_FAILED = "schema_repair_failed"
    GITHUB_UNAVAILABLE = "github_unavailable"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEGRADED = "degraded"


class CacheKind(StrEnum):
    LLM = "llm"
    EMBEDDING = "embedding"
    TOOL = "tool"


def truncate(text: str, limit: int = 2000, *, suffix: str = "…") -> str:
    """Clip long text for storage in a trace or snippet field."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(suffix))] + suffix


def days_ago(days: float) -> datetime:
    """Helper used by tests to build realistic recency inputs."""
    return utcnow() - timedelta(days=days)


def as_dict(model: BaseModel) -> dict[str, Any]:
    """Serialise with JSON-safe types (UUID/datetime → str)."""
    return model.model_dump(mode="json")
