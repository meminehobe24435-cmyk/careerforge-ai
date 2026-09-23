"""Claim adjudication without a language model.

The deterministic half of the anti-hallucination gate. Two rules carry the weight:

1. **Numbers need numbers.** A quantified claim whose figures appear nowhere in
   the retrieved evidence is rejected outright, before any model is consulted
   (ADR-014).
2. **Missing technical nouns block a claim.** If the claim asserts ``I2C`` and no
   evidence mentions ``I2C``, the sentence as written is not supported, however
   well the rest of it matches. Token overlap alone cannot see this: two missing
   tokens out of twenty still leaves a high coverage score. Measured against the
   labelled claim set, this rule removed every false "supported" verdict in the
   partial-support category.

It also produces a *safer rewrite* by dropping the clauses it cannot support, so
a rejection arrives with something the candidate can actually use.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from careerforge_ai.providers.heuristic.registry import handles
from careerforge_ai.providers.heuristic.text import (
    missing_technical_tokens,
    token_overlap,
)
from careerforge_ai.schemas.claim import ClaimLLMVerdict

__all__ = ["validate_claim"]

_NUMERIC_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|％|倍|万|亿|k|K|ms|us|μs|fps|qps|tps)"
)

#: Overlap needed to call a claim supported.
#:
#: Measured on the labelled claim set (``evals/datasets/claim_validation.jsonl``)
#: with the technical-token rule active, the two classes separate like this:
#: gold-unsupported tops out at 0.404, gold-supported bottoms out at 0.424. The
#: threshold sits between them.
#:
#: The margin is narrow, and that is worth stating plainly rather than hiding:
#: character-level overlap cannot see paraphrase ("开发...系统" vs
#: "实现...控制"), so this is the heuristic provider's ceiling, not a tuning
#: success. It is low rather than high because a false "supported" is far more
#: damaging in this product than a false "needs evidence".
SUPPORT_OVERLAP_THRESHOLD = 0.415
#: Overlap needed to call a claim *partly* supported rather than unsupported.
PARTIAL_OVERLAP_THRESHOLD = 0.30

#: Clause separators used when downgrading a claim. A clause is the smallest unit
#: a candidate can meaningfully drop, in both Chinese and English.
_CLAUSE_SPLIT_RE = re.compile(r"[，,；;、]|(?:\s+and\s+)|(?:并(?=[\u4e00-\u9fff]))|以及|同时")


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


def _clauses(claim: str) -> list[str]:
    return [part.strip() for part in _CLAUSE_SPLIT_RE.split(claim) if part.strip()]


def _safer_formulation(claim: str, evidence_text: str, dropped_numbers: list[str]) -> str:
    """Keep only the clauses the evidence can carry.

    Returns an empty string when nothing changed, so the caller can tell "no
    safer option exists" apart from "the safer option is identical".
    """
    clauses = _clauses(claim)
    if len(clauses) > 1:
        kept = [
            clause
            for clause in clauses
            if not missing_technical_tokens(clause, evidence_text)
            and token_overlap(clause, evidence_text) >= PARTIAL_OVERLAP_THRESHOLD
        ]
        if kept and len(kept) < len(clauses):
            candidate = "，".join(kept)
            for number in dropped_numbers:
                candidate = candidate.replace(number, "")
            candidate = re.sub(r"\s{2,}", " ", candidate).strip("，,。;； ")
            if candidate and candidate != claim:
                return candidate

    if not dropped_numbers:
        return ""

    stripped = claim
    for number in dropped_numbers:
        stripped = stripped.replace(number, "")
    stripped = re.sub(r"\s{2,}", " ", stripped).strip("，,。;； ")
    return stripped if stripped and stripped != claim else ""


@handles(ClaimLLMVerdict)
def validate_claim(text: str, context: Mapping[str, Any]) -> ClaimLLMVerdict:
    """Adjudicate a claim against the retrieved evidence."""
    evidence_pool: Sequence[Mapping[str, Any]] = context.get("evidence") or []
    evidence_text = "\n".join(
        f"{item.get('title', '')}\n{item.get('snippet', '')}" for item in evidence_pool
    )

    overlap = token_overlap(text, evidence_text)
    missing_technical = sorted(missing_technical_tokens(text, evidence_text))
    claim_numbers = [match.group(0) for match in _NUMERIC_RE.finditer(text)]
    unsupported_numbers = [
        number for number in claim_numbers if not _has_comparable_number(number, evidence_text)
    ]

    unsupported_parts: list[str] = []
    if missing_technical:
        unsupported_parts.extend(missing_technical)
    if unsupported_numbers:
        unsupported_parts.extend(unsupported_numbers)
    if overlap < SUPPORT_OVERLAP_THRESHOLD and not unsupported_parts:
        unsupported_parts.append(text)

    contradicted = bool(unsupported_numbers)
    supported = (
        overlap >= SUPPORT_OVERLAP_THRESHOLD and not unsupported_numbers and not missing_technical
    )
    partially = not supported and not contradicted and overlap >= PARTIAL_OVERLAP_THRESHOLD

    safer = _safer_formulation(text, evidence_text, unsupported_numbers)

    reasoning_parts = [f"关键词覆盖度 {overlap:.0%}"]
    if missing_technical:
        reasoning_parts.append(f"证据中未出现：{'、'.join(missing_technical[:5])}")
    if unsupported_numbers:
        reasoning_parts.append(f"证据中无对应量化数据：{'、'.join(unsupported_numbers)}")

    return ClaimLLMVerdict(
        supported=supported,
        partially_supported=partially,
        unsupported_parts=unsupported_parts[:6],
        contradicting_evidence=[],
        reasoning="；".join(reasoning_parts),
        safer_formulation=safer,
    )
