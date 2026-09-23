"""Deterministic scoring engines.

Nothing in this package asks a language model for a number. Every score here is
a pure function of structured inputs, which buys three things the product needs:
reproducibility (the same input always yields the same score), explainability
(each score publishes its own derivation) and testability (scores are asserted in
unit tests and tracked across releases).
"""

from __future__ import annotations

from careerforge_ai.scoring.confidence import (
    AUTHORITY_SCORES,
    CONFIDENCE_FORMULA_VERSION,
    DEFAULT_WEIGHTS,
    classify_claim_status,
    compute_confidence,
    corroboration_score,
    recency_score,
    specificity_score,
)
from careerforge_ai.scoring.match import (
    DEFAULT_MATCH_WEIGHTS,
    compute_job_match,
)
from careerforge_ai.scoring.profile_strength import compute_profile_strength
from careerforge_ai.scoring.skill_gap import compute_skill_gap_matrix

__all__ = [
    "AUTHORITY_SCORES",
    "CONFIDENCE_FORMULA_VERSION",
    "DEFAULT_MATCH_WEIGHTS",
    "DEFAULT_WEIGHTS",
    "classify_claim_status",
    "compute_confidence",
    "compute_job_match",
    "compute_profile_strength",
    "compute_skill_gap_matrix",
    "corroboration_score",
    "recency_score",
    "specificity_score",
]
