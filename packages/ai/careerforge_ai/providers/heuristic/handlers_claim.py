"""Claim adjudication without a language model.

The deterministic half of the anti-hallucination gate. Its most important rule is
about numbers: a quantified claim whose figures appear nowhere in the retrieved
evidence is rejected outright, before any model is consulted (ADR-014).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from careerforge_ai.providers.heuristic.registry import handles
from careerforge_ai.providers.heuristic.text import token_overlap
from careerforge_ai.schemas.claim import ClaimLLMVerdict

__all__ = ["validate_claim"]

_NUMERIC_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|％|倍|万|亿|k|K|ms|us|μs|fps|qps|tps)"
)

#: Token-overlap thresholds for the deterministic adjudicator. Tuned against the
#: labelled claim set in ``evals/datasets``; deliberately conservative, because a
#: false "supported" is far more damaging in this product than a false
#: "needs evidence".
SUPPORT_OVERLAP_THRESHOLD = 0.60
PARTIAL_OVERLAP_THRESHOLD = 0.25


def _has_comparable_number(claim_number: str, evidence_text: str) -> bool:
    """Does the evidence contain a number of the same flavour as the claim?"""
    match = _NUMERIC_RE.search(claim_number)
    if not match:
        return False
    unit = match.group("unit")
    return any(
        candidate.group("unit").lower() == unit.lower()
        for candidate in _NUMERIC_RE.finditer(evidence_text)
    )


@handles(ClaimLLMVerdict)
def validate_claim(text: str, context: Mapping[str, Any]) -> ClaimLLMVerdict:
    """Adjudicate a claim against the retrieved evidence."""
    evidence_pool: Sequence[Mapping[str, Any]] = context.get("evidence") or []
    evidence_text = "\n".join(
        f"{item.get('title', '')}\n{item.get('snippet', '')}" for item in evidence_pool
    )

    overlap = token_overlap(text, evidence_text)
    claim_numbers = [match.group(0) for match in _NUMERIC_RE.finditer(text)]
    unsupported_numbers = [
        number for number in claim_numbers if not _has_comparable_number(number, evidence_text)
    ]

    unsupported_parts: list[str] = []
    if overlap < SUPPORT_OVERLAP_THRESHOLD:
        unsupported_parts.append(text)
    if unsupported_numbers:
        unsupported_parts.extend(unsupported_numbers)

    contradicted = bool(unsupported_numbers)
    partially = bool(unsupported_parts) and overlap >= PARTIAL_OVERLAP_THRESHOLD
    supported = overlap >= SUPPORT_OVERLAP_THRESHOLD and not unsupported_numbers

    safer = text
    for number in unsupported_numbers:
        safer = safer.replace(number, "").strip()
    safer = re.sub(r"\s{2,}", " ", safer).rstrip("，,。;；")

    reasoning_parts: list[str] = [f"关键词覆盖度 {overlap:.0%}"]
    if unsupported_numbers:
        reasoning_parts.append(f"证据中未出现量化数据：{'、'.join(unsupported_numbers)}")

    return ClaimLLMVerdict(
        supported=supported,
        partially_supported=partially and not contradicted,
        unsupported_parts=unsupported_parts[:5],
        contradicting_evidence=[],
        reasoning="；".join(reasoning_parts),
        safer_formulation=safer if safer != text else "",
    )
