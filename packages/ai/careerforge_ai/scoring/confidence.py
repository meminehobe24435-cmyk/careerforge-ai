"""The evidence confidence engine.

This module is the trust foundation of the entire product, so it is written to
be **auditable rather than clever**:

* Every factor is a small, separately tested pure function.
* The weighted sum is mirrored *exactly* by a database ``CHECK`` constraint
  (``constraint ck_evidence_confidence_formula``), so a value that bypasses this
  module cannot be persisted.
* Inputs are rounded to three decimals before the sum, matching the
  ``numeric(4,3)`` columns the database evaluates — which is what keeps the
  Python result and the SQL constraint in agreement to within tolerance.

Formula (``confidence@1.0.0``)::

    confidence = 0.30·authority + 0.15·recency + 0.20·specificity
               + 0.20·corroboration + 0.15·extraction_quality
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
import math

from careerforge_ai.schemas.common import (
    ClaimStatus,
    EvidenceKind,
    SourceAuthority,
    Unit,
    utcnow,
)
from careerforge_ai.schemas.evidence import (
    ConfidenceBreakdown,
    ConfidenceInputs,
    EvidenceLocator,
)

__all__ = [
    "AUTHORITY_SCORES",
    "CONFIDENCE_FORMULA_VERSION",
    "CORROBORATION_BASE",
    "CORROBORATION_STEP",
    "DEFAULT_WEIGHTS",
    "EXTRACTION_QUALITY",
    "MIN_CONFIDENCE_FOR_CLAIM",
    "RECENCY_HALF_LIFE_SCALE_DAYS",
    "RECENCY_UNKNOWN",
    "authority_for_kind",
    "authority_score",
    "classify_claim_status",
    "compute_confidence",
    "corroboration_score",
    "extraction_quality_score",
    "quantified_claim_allowed",
    "recency_score",
    "specificity_score",
]

CONFIDENCE_FORMULA_VERSION = "confidence@1.0.0"

#: Weights of ``confidence@1.0.0``. Must sum to 1.0 — asserted at import time.
DEFAULT_WEIGHTS: Mapping[str, float] = {
    "authority": 0.30,
    "recency": 0.15,
    "specificity": 0.20,
    "corroboration": 0.20,
    "extraction": 0.15,
}

assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9, "confidence weights must sum to 1.0"

#: Numeric authority per source tier. Code and commits are the strongest signal
#: available; an LLM inference is the weakest and is marked as such.
AUTHORITY_SCORES: Mapping[SourceAuthority, float] = {
    SourceAuthority.CODE_OR_COMMIT: 1.00,
    SourceAuthority.README: 0.85,
    SourceAuthority.UPLOADED_DOCUMENT: 0.80,
    SourceAuthority.RESUME_SELF_REPORT: 0.55,
    SourceAuthority.LLM_INFERENCE: 0.35,
}

#: Default authority tier per evidence kind.
_KIND_AUTHORITY: Mapping[EvidenceKind, SourceAuthority] = {
    EvidenceKind.REPO_FILE: SourceAuthority.CODE_OR_COMMIT,
    EvidenceKind.COMMIT: SourceAuthority.CODE_OR_COMMIT,
    EvidenceKind.README: SourceAuthority.README,
    EvidenceKind.DOCUMENT_CHUNK: SourceAuthority.UPLOADED_DOCUMENT,
    EvidenceKind.EXPERIENCE: SourceAuthority.UPLOADED_DOCUMENT,
    EvidenceKind.PROJECT: SourceAuthority.UPLOADED_DOCUMENT,
    EvidenceKind.ACHIEVEMENT: SourceAuthority.UPLOADED_DOCUMENT,
    EvidenceKind.MANUAL: SourceAuthority.UPLOADED_DOCUMENT,
    EvidenceKind.LLM_INFERENCE: SourceAuthority.LLM_INFERENCE,
}

#: Extraction quality per method that produced the evidence.
EXTRACTION_QUALITY: Mapping[str, float] = {
    "deterministic": 1.00,
    "llm": 0.70,
    "heuristic": 0.50,
    "manual": 0.90,
}

#: Time-decay scale. ``exp(-age_days / 540)``: ~18 months to fall to 1/e.
RECENCY_HALF_LIFE_SCALE_DAYS = 540.0

#: Used when the evidence has no date at all (a README, for instance). Not 0.5:
#: undated material is not *untrustworthy*, merely less attributable.
RECENCY_UNKNOWN = 0.60

#: ``corroboration = min(1, BASE + STEP × independent_sources)``
CORROBORATION_BASE = 0.40
CORROBORATION_STEP = 0.20

#: Below this the evidence is not strong enough to carry a claim on its own.
MIN_CONFIDENCE_FOR_CLAIM = 0.45

#: Claim status thresholds (mirrored by ``CLAIM_*_THRESHOLD`` settings).
_SUPPORTED_THRESHOLD = 0.75
_PARTIAL_THRESHOLD = 0.45
_MIN_SOURCES = 2


def _round3(value: float) -> float:
    """Round like ``numeric(4,3)`` so Python and SQL agree."""
    return round(float(value), 3)


def _clamp_unit(value: float) -> Unit:
    return max(0.0, min(1.0, float(value)))


def authority_for_kind(kind: EvidenceKind) -> SourceAuthority:
    """Default authority tier for an evidence kind."""
    return _KIND_AUTHORITY.get(kind, SourceAuthority.RESUME_SELF_REPORT)


def authority_score(authority: SourceAuthority | str | None) -> float:
    """Map an authority tier to its numeric score.

    Unknown tiers fall back to the weakest *named* tier rather than raising:
    ingestion must never fail because of a novel source string.
    """
    if authority is None:
        return AUTHORITY_SCORES[SourceAuthority.RESUME_SELF_REPORT]
    if isinstance(authority, str):
        try:
            authority = SourceAuthority(authority)
        except ValueError:
            return AUTHORITY_SCORES[SourceAuthority.LLM_INFERENCE]
    return AUTHORITY_SCORES[authority]


def recency_score(occurred_at: datetime | None, *, now: datetime | None = None) -> float:
    """Exponential time decay. Future dates are clamped to a full score."""
    if occurred_at is None:
        return RECENCY_UNKNOWN
    reference = now or utcnow()
    if occurred_at.tzinfo is None:
        # Treat naive timestamps as UTC rather than raising: source systems
        # (GitHub, PDFs) are inconsistent about this and a hard failure here
        # would be a worse outcome than an assumption we document.
        occurred_at = occurred_at.replace(tzinfo=reference.tzinfo)
    age_days = (reference - occurred_at).total_seconds() / 86_400.0
    if age_days <= 0:
        return 1.0
    return _clamp_unit(math.exp(-age_days / RECENCY_HALF_LIFE_SCALE_DAYS))


def specificity_score(locator: EvidenceLocator | None) -> float:
    """How precisely the evidence can be located and re-checked.

    A file plus a line number is checkable in seconds; a whole document is not.
    """
    if locator is None:
        return 0.45
    if locator.path and locator.line:
        return 1.00
    if locator.sha:
        return 0.95
    if locator.path:
        return 0.85
    if locator.url:
        return 0.75
    if locator.page is not None or locator.char_start is not None:
        return 0.70
    if locator.section:
        return 0.60
    return 0.45


def corroboration_score(independent_sources: int) -> float:
    """Reach full corroboration once five independent sources agree."""
    count = max(0, int(independent_sources))
    return _clamp_unit(CORROBORATION_BASE + CORROBORATION_STEP * count)


def extraction_quality_score(method: str) -> float:
    """Quality tier of whatever produced the evidence."""
    key = (method or "").strip().lower()
    if key in EXTRACTION_QUALITY:
        return EXTRACTION_QUALITY[key]
    return EXTRACTION_QUALITY["heuristic"]


def compute_confidence(
    *,
    authority: SourceAuthority | str | None = None,
    kind: EvidenceKind | None = None,
    occurred_at: datetime | None = None,
    locator: EvidenceLocator | None = None,
    independent_sources: int = 1,
    extraction_method: str = "deterministic",
    weights: Mapping[str, float] | None = None,
    now: datetime | None = None,
) -> ConfidenceBreakdown:
    """Compute confidence and return the full derivation.

    The caller gets both the score and every ingredient that produced it, which
    is what allows the UI to render a genuine explanation instead of a
    post-hoc rationalisation.
    """
    resolved_authority = (
        authority if authority is not None else authority_for_kind(kind or EvidenceKind.MANUAL)
    )
    effective_weights = dict(weights or DEFAULT_WEIGHTS)

    inputs = ConfidenceInputs(
        source_authority=_round3(authority_score(resolved_authority)),
        recency=_round3(recency_score(occurred_at, now=now)),
        specificity=_round3(specificity_score(locator)),
        corroboration=_round3(corroboration_score(independent_sources)),
        extraction_quality=_round3(extraction_quality_score(extraction_method)),
        weights=effective_weights,
        formula_version=CONFIDENCE_FORMULA_VERSION,
        corroboration_sources=max(0, int(independent_sources)),
    )

    contributions = {
        "authority": _round3(inputs.source_authority * effective_weights.get("authority", 0.0)),
        "recency": _round3(inputs.recency * effective_weights.get("recency", 0.0)),
        "specificity": _round3(inputs.specificity * effective_weights.get("specificity", 0.0)),
        "corroboration": _round3(
            inputs.corroboration * effective_weights.get("corroboration", 0.0)
        ),
        "extraction": _round3(inputs.extraction_quality * effective_weights.get("extraction", 0.0)),
    }

    score = _round3(sum(contributions.values()))
    return ConfidenceBreakdown(
        inputs=inputs,
        contributions=contributions,
        score=_clamp_unit(score),
        formula_version=CONFIDENCE_FORMULA_VERSION,
    )


def classify_claim_status(
    confidence: float,
    independent_sources: int,
    *,
    supported_threshold: float = _SUPPORTED_THRESHOLD,
    partial_threshold: float = _PARTIAL_THRESHOLD,
    min_sources: int = _MIN_SOURCES,
    contradicted: bool = False,
) -> ClaimStatus:
    """Turn a confidence value into a gate decision.

    Two conditions must hold for ``SUPPORTED``: the score must clear the
    threshold **and** at least ``min_sources`` independent sources must agree.
    One confident source is still one source.
    """
    if contradicted:
        return ClaimStatus.CONTRADICTED
    if confidence >= supported_threshold and independent_sources >= min_sources:
        return ClaimStatus.SUPPORTED
    if confidence >= partial_threshold:
        return ClaimStatus.PARTIALLY_SUPPORTED
    return ClaimStatus.UNSUPPORTED


def quantified_claim_allowed(
    numeric_mentions: Iterable[object], supported_sources: int, confidence: float
) -> bool:
    """Whether a claim containing hard numbers may be accepted.

    A quantified claim needs a *quantified* source. This is the deterministic
    rule that rejects "improved performance by 70%" when nothing anywhere backs
    the number up, and it runs before the LLM is consulted at all (ADR-014).
    """
    mentions = list(numeric_mentions)
    if not mentions:
        return True
    return supported_sources > 0 and confidence >= MIN_CONFIDENCE_FOR_CLAIM
