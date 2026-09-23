"""Claim validation schemas — the anti-hallucination gate.

A *claim* is one sentence a candidate wants on their resume. The validator
answers a single question: **does the evidence actually support this?**

The verdict order is fixed and non-negotiable (ADR-014):
deterministic rules → retrieval → LLM → gate.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from careerforge_ai.schemas.common import (
    CFBaseModel,
    ClaimRuleCode,
    ClaimStatus,
    Confidence,
    RetrievalChannel,
    StrictModel,
    Unit,
    utcnow,
)
from careerforge_ai.schemas.evidence import EvidenceLocator, RetrievalResult

__all__ = [
    "ClaimLLMVerdict",
    "ClaimReason",
    # Re-exported because they are part of this module's public vocabulary: a caller
    # reading a validation result should not have to know they are declared in
    # ``schemas.common``.
    "ClaimRuleCode",
    "ClaimSource",
    "ClaimStatus",
    "ClaimValidation",
    "ClaimValidationRequest",
    "ExtractedClaim",
    "NumericMention",
    "ResumeBullet",
    "ResumeIntegrity",
    "ResumeOptimizationResult",
    "SafeRewrite",
]


class ClaimReason(CFBaseModel):
    """A rule or judgement that influenced the verdict, with severity."""

    rule: ClaimRuleCode | str
    severity: str = Field(default="info", description="info | warning | blocker")
    message: str
    evidence_ids: list[UUID] = Field(default_factory=list)

    @property
    def is_blocking(self) -> bool:
        return self.severity == "blocker"


class ClaimSource(CFBaseModel):
    """An evidence hit that was considered, with its retrieval provenance."""

    evidence_id: UUID
    title: str
    kind: str
    relevance: Confidence
    channel: RetrievalChannel = RetrievalChannel.SEMANTIC
    locator: EvidenceLocator = Field(default_factory=EvidenceLocator)
    url: str | None = None
    snippet: str = ""


class SafeRewrite(CFBaseModel):
    """A downgraded formulation that *is* supported by the available evidence.

    Refusing a claim without offering a compliant alternative just pushes the
    user back to writing it by hand. This is the constructive half of the gate.
    """

    text: str
    removed_claims: list[str] = Field(
        default_factory=list, description="Parts dropped because they had no evidence"
    )
    rationale: str = ""
    confidence: Confidence = 0.0


class NumericMention(CFBaseModel):
    """A quantified fragment detected in a claim — the highest-risk hallucination type."""

    raw: str = Field(description="The literal matched text, e.g. '70%' or '3 倍'")
    kind: str = Field(
        default="percentage", description="percentage | multiple | absolute | duration"
    )
    value: float | None = None
    supported: bool = Field(
        default=False, description="Whether any retrieved evidence contains a comparable figure"
    )


class ClaimValidationRequest(CFBaseModel):
    text: str = Field(min_length=1, max_length=1000)
    job_id: UUID | None = None
    project_id: UUID | None = None
    resume_version_id: UUID | None = None
    max_sources: int = Field(default=8, ge=1, le=20)


class ClaimValidation(CFBaseModel):
    """The validator's full answer — everything the UI needs to justify itself."""

    claim: str
    status: ClaimStatus = ClaimStatus.PENDING
    confidence: Confidence = 0.0

    sources: list[ClaimSource] = Field(default_factory=list)
    reasons: list[ClaimReason] = Field(default_factory=list)
    safe_rewrite: SafeRewrite | None = None
    unknowns: list[str] = Field(default_factory=list)

    has_quantified_claim: bool = False
    numeric_mentions: list[NumericMention] = Field(default_factory=list)

    retrieval: RetrievalResult | None = None
    independent_source_count: int = Field(default=0, ge=0)
    rule_version: str = "claim_rules@1.0.0"
    model: str | None = None
    prompt_version: str | None = None
    latency_ms: int = 0
    validated_at: datetime = Field(default_factory=utcnow)

    @property
    def is_blocking(self) -> bool:
        return self.status.is_blocking

    @property
    def allows_resume_inclusion(self) -> bool:
        return self.status.allows_resume_inclusion

    def blocking_reasons(self) -> list[ClaimReason]:
        return [reason for reason in self.reasons if reason.is_blocking]


class ExtractedClaim(StrictModel):
    """LLM-facing: the atomic assertions contained in a bullet."""

    assertions: list[str] = Field(
        default_factory=list,
        description="Each independently checkable factual assertion in the text, one per item",
    )
    entities: list[str] = Field(
        default_factory=list, description="Named technologies, systems or artefacts mentioned"
    )
    numeric_claims: list[str] = Field(
        default_factory=list, description="Quantified statements, quoted verbatim"
    )


class ClaimLLMVerdict(StrictModel):
    """LLM-facing verdict. Note the absence of any confidence field.

    The model judges *support*, never *confidence*: confidence is arithmetic
    (ADR-013) and letting a language model set it would break reproducibility.
    """

    supported: bool = Field(
        description="True only if the retrieved evidence directly supports the claim"
    )
    partially_supported: bool = Field(
        default=False, description="True if some but not all of the claim is supported"
    )
    unsupported_parts: list[str] = Field(
        default_factory=list,
        description="The specific fragments that the evidence does NOT support",
    )
    contradicting_evidence: list[str] = Field(
        default_factory=list, description="Evidence that actively conflicts with the claim"
    )
    reasoning: str = Field(default="", description="Two sentences maximum")
    safer_formulation: str = Field(
        default="", description="A version of the claim that the evidence does support, or empty"
    )


class ResumeBullet(StrictModel):
    """One resume bullet, before and after optimisation."""

    section: str = Field(description="summary | experience | project | skill | education")
    original: str = Field(description="The candidate's existing wording, verbatim")
    optimized: str = Field(
        default="",
        description="Improved wording. Every fact in it MUST already exist in the source material.",
    )
    rationale: str = Field(
        default="", description="What was improved: clarity, specificity, keywords"
    )
    keywords_added: list[str] = Field(default_factory=list)


class ResumeOptimizationResult(CFBaseModel):
    """Output of the resume workflow, after the gate has run on every bullet."""

    version_id: UUID | None = None
    job_id: UUID | None = None
    bullets: list[ResumeBullet] = Field(default_factory=list)
    validations: list[ClaimValidation] = Field(default_factory=list)
    integrity_score: Unit = Field(
        default=0.0, description="Share of bullets whose claims passed the gate"
    )
    claim_stats: dict[str, int] = Field(default_factory=dict)
    rejected: list[ClaimValidation] = Field(default_factory=list)
    degraded: bool = False
    new_evidence_suggestions: list[str] = Field(
        default_factory=list, description="How to make a rejected claim provable next time"
    )

    def validation_for(self, bullet_index: int) -> ClaimValidation | None:
        if 0 <= bullet_index < len(self.validations):
            return self.validations[bullet_index]
        return None


class ResumeIntegrity(CFBaseModel):
    """Aggregate honesty metric for a resume version."""

    total_bullets: int = 0
    supported: int = 0
    partially_supported: int = 0
    unsupported: int = 0
    contradicted: int = 0
    integrity_score: Unit = 0.0

    @property
    def blocked(self) -> int:
        return self.unsupported + self.contradicted


class ExtractedResumeOptimization(StrictModel):
    """LLM-facing wrapper around the rewritten bullets.

    A bare list cannot carry prompt-level guidance, and the schema is where the
    no-new-facts constraint is restated for the model one last time — closer to the
    generation than the prompt's prose is.
    """

    bullets: list[ResumeBullet] = Field(
        default_factory=list,
        description=(
            "One entry per input bullet, in the same order. Every fact in `optimized` "
            "must already appear in the candidate material. If a bullet cannot be "
            "improved without inventing something, improve only its clarity or repeat "
            "the original text."
        ),
    )
