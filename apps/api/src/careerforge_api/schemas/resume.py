"""Résumé models: ``/resume`` and the Claim Validator (``docs/API.md`` §2.9, §2.5).

The validation payload keeps the documented shape — status, confidence, the reasons that fired,
the citations, and the safer rewrite when one exists — because those are what make the gate
*explainable* rather than merely strict. A rejection without its reason is indistinguishable
from a bug, to the candidate who receives it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ClaimEvidenceResponse",
    "ClaimReasonResponse",
    "ClaimValidationResponse",
    "ResumeBulletRequest",
    "ResumeClaimResponse",
    "ResumeOptimizeRequest",
    "ResumeVersionDetail",
    "ResumeVersionResponse",
    "SafeRewriteResponse",
    "ValidateClaimRequest",
    "ValidateClaimResponse",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ClaimReasonResponse(_CamelModel):
    """One rule that fired, with the sentence a human reads."""

    rule: str
    severity: str = "info"
    message: str = ""
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")


class ClaimEvidenceResponse(_CamelModel):
    """A citation: this claim rests on that evidence, found by that channel."""

    evidence_id: str = Field(alias="evidenceId")
    title: str = ""
    kind: str = ""
    relevance: float = 0.0
    channel: str = "semantic"
    locator: str = ""
    url: str | None = None
    snippet: str = ""


class SafeRewriteResponse(_CamelModel):
    text: str = ""
    removed_claims: list[str] = Field(default_factory=list, alias="removedClaims")
    rationale: str = ""


class ClaimValidationResponse(_CamelModel):
    """The gate's full verdict on one sentence."""

    claim: str
    status: str = "pending"
    confidence: float = 0.0
    reasons: list[ClaimReasonResponse] = Field(default_factory=list)
    sources: list[ClaimEvidenceResponse] = Field(default_factory=list)
    safe_rewrite: SafeRewriteResponse | None = Field(default=None, alias="safeRewrite")
    unknowns: list[str] = Field(default_factory=list)
    has_quantified_claim: bool = Field(default=False, alias="hasQuantifiedClaim")
    independent_source_count: int = Field(default=0, alias="independentSourceCount")
    rule_version: str = Field(default="claim_rules@1.0.0", alias="ruleVersion")
    model: str | None = None

    @classmethod
    def from_schema(cls, validation: Any) -> ClaimValidationResponse:
        return cls(
            claim=validation.claim,
            status=validation.status.value,
            confidence=float(validation.confidence),
            reasons=[
                ClaimReasonResponse(
                    rule=(reason.rule.value if hasattr(reason.rule, "value") else str(reason.rule)),
                    severity=reason.severity,
                    message=reason.message,
                    evidence_ids=[str(item) for item in reason.evidence_ids],
                )
                for reason in validation.reasons
            ],
            sources=[
                ClaimEvidenceResponse(
                    evidence_id=str(source.evidence_id),
                    title=source.title,
                    kind=source.kind,
                    relevance=float(source.relevance),
                    channel=(
                        source.channel.value
                        if hasattr(source.channel, "value")
                        else str(source.channel)
                    ),
                    locator=source.locator.display,
                    url=source.locator.url,
                    snippet=source.snippet,
                )
                for source in validation.sources
            ],
            safe_rewrite=(
                SafeRewriteResponse(
                    text=validation.safe_rewrite.text,
                    removed_claims=list(validation.safe_rewrite.removed_claims),
                    rationale=validation.safe_rewrite.rationale,
                )
                if validation.safe_rewrite is not None
                else None
            ),
            unknowns=list(validation.unknowns),
            has_quantified_claim=validation.has_quantified_claim,
            independent_source_count=validation.independent_source_count,
            rule_version=validation.rule_version,
            model=validation.model,
        )


class ResumeBulletRequest(_CamelModel):
    """One bullet the candidate wants rewritten."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    section: str = Field(default="summary")
    original: str = Field(min_length=1, max_length=1000)


class ResumeOptimizeRequest(_CamelModel):
    """``POST /resume/optimize`` body. Unknown fields are refused."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    bullets: list[ResumeBulletRequest] = Field(default_factory=list, max_length=40)
    job_id: str | None = Field(default=None, alias="jobId")
    label: str = Field(default="", max_length=120)


class ValidateClaimRequest(_CamelModel):
    """``POST /evidence/validate`` body."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    text: str = Field(min_length=1, max_length=1000)
    section: str = "summary"
    job_id: str | None = Field(default=None, alias="jobId")


class ValidateClaimResponse(_CamelModel):
    """The verdict, plus the stored claim's id so a client can cite it later."""

    claim_id: str = Field(alias="claimId")
    claim: ClaimValidationResponse


class ResumeClaimResponse(_CamelModel):
    """A stored claim, as ``GET /resume/versions/{id}`` returns it."""

    id: str
    section: str = "summary"
    text: str
    original_text: str = Field(default="", alias="originalText")
    status: str = "pending"
    confidence: float = 0.0
    safe_rewrite: str = Field(default="", alias="safeRewrite")
    reasons: list[dict[str, Any]] = Field(default_factory=list)
    has_quantified_claim: bool = Field(default=False, alias="hasQuantifiedClaim")
    independent_source_count: int = Field(default=0, alias="independentSourceCount")
    evidence: list[ClaimEvidenceResponse] = Field(default_factory=list)

    @classmethod
    def from_row(cls, claim: Any) -> ResumeClaimResponse:
        """Project a stored claim, including its citations.

        The citations come from ``claim_evidence``; a row there is the difference between "the
        gate approved this" and "here is what approves it".
        """
        return cls(
            id=str(claim.id),
            section=claim.section,
            text=claim.text,
            original_text=claim.original_text,
            status=claim.status,
            confidence=float(claim.confidence),
            safe_rewrite=claim.safe_rewrite,
            reasons=[dict(item) for item in claim.reasons or []],
            has_quantified_claim=claim.has_quantified_claim,
            independent_source_count=claim.independent_source_count,
            evidence=[
                ClaimEvidenceResponse(
                    evidence_id=str(link.evidence_id),
                    relevance=float(link.relevance),
                    channel=link.channel,
                )
                for link in claim.evidence or []
            ],
        )


class ResumeVersionResponse(_CamelModel):
    """A version in a list — the summary, not the content."""

    id: str
    label: str = ""
    source: str = "generated"
    target_job_id: str | None = Field(default=None, alias="targetJobId")
    integrity_score: float = Field(default=0.0, alias="integrityScore")
    claim_stats: dict[str, int] = Field(default_factory=dict, alias="claimStats")
    created_at: datetime | None = Field(default=None, alias="createdAt")

    @classmethod
    def from_row(cls, version: Any) -> ResumeVersionResponse:
        return cls(
            id=str(version.id),
            label=version.label,
            source=version.source,
            target_job_id=str(version.target_job_id) if version.target_job_id else None,
            integrity_score=float(version.integrity_score),
            claim_stats={str(k): int(v) for k, v in (version.claim_stats or {}).items()},
            created_at=version.created_at,
        )


class ResumeVersionDetail(ResumeVersionResponse):
    """``GET /resume/versions/{id}`` — the content, the bullets and every claim."""

    content_md: str = Field(default="", alias="contentMd")
    diff_summary: dict[str, Any] = Field(default_factory=dict, alias="diffSummary")
    claims: list[ResumeClaimResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    degraded: bool = False

    @classmethod
    def from_row(
        cls, version: Any, *, claims: list[ResumeClaimResponse] | None = None
    ) -> ResumeVersionDetail:
        base = ResumeVersionResponse.from_row(version)
        return cls(
            **base.model_dump(),
            content_md=version.content_md,
            diff_summary=dict(version.diff_summary or {}),
            claims=claims or [],
        )
