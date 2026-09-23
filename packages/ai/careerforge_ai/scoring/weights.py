"""The one place scoring weights are defined.

Two formulas drive every number the product shows, and both are weight-sensitive:
a small change silently shifts every score. Keeping them in a single importable
module means the API can expose them, the docs can quote them, and a test can
assert they still sum to 1.0.

* :data:`MATCH_WEIGHTS` — job match dimensions (``match@1.0.0``)
* :data:`CONFIDENCE_WEIGHTS` — evidence confidence factors (``confidence@1.0.0``)
"""

from __future__ import annotations

from collections.abc import Mapping

__all__ = [
    "CONFIDENCE_FORMULA",
    "CONFIDENCE_WEIGHTS",
    "MATCH_FORMULA",
    "MATCH_WEIGHTS",
]

#: Job match: skill · experience · project · education · evidence
MATCH_WEIGHTS: Mapping[str, float] = {
    "skill": 0.40,
    "experience": 0.25,
    "project": 0.20,
    "education": 0.05,
    "evidence": 0.10,
}

MATCH_FORMULA = "0.40·skill + 0.25·experience + 0.20·project + 0.05·education + 0.10·evidence"

#: Evidence confidence: authority · recency · specificity · corroboration ·
#: extraction quality. Mirrored exactly by
#: ``ck_evidence_confidence_formula`` in the database.
CONFIDENCE_WEIGHTS: Mapping[str, float] = {
    "authority": 0.30,
    "recency": 0.15,
    "specificity": 0.20,
    "corroboration": 0.20,
    "extraction": 0.15,
}

CONFIDENCE_FORMULA = (
    "0.30·authority + 0.15·recency + 0.20·specificity + 0.20·corroboration + 0.15·extraction"
)

assert abs(sum(MATCH_WEIGHTS.values()) - 1.0) < 1e-9, "match weights must sum to 1.0"
assert abs(sum(CONFIDENCE_WEIGHTS.values()) - 1.0) < 1e-9, "confidence weights must sum to 1.0"
