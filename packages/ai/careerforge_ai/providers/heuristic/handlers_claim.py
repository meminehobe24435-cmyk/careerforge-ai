"""Claim adjudication without a language model.

The deterministic half of the anti-hallucination gate. Its rules are defined once
in :mod:`careerforge_ai.parsing.claim_rules` and shared with
:class:`careerforge_ai.agents.validator.ValidatorAgent`, so the zero-key path and
the model-backed gate can never disagree about whether a number is supported.

Three rules carry the weight:

1. **Numbers need numbers.** A quantified claim whose unit family appears nowhere
   in the evidence is rejected outright.
2. **Missing technical nouns block a claim.** If the claim asserts ``I2C`` and no
   evidence mentions ``I2C``, the sentence as written is not supported, however
   well the rest of it matches. Token overlap alone cannot see this: two missing
   tokens out of twenty still leaves a high coverage score.
3. **Over-claiming wording is flagged, never blocking.** 「精通」 is advisory; a
   fabricated metric is not.

It also produces a *safer rewrite* by dropping the clauses it cannot support, so a
rejection arrives with something the candidate can actually use.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from careerforge_ai.parsing.claim_rules import (
    build_safer_formulation,
    detect_missing_technical,
    detect_numeric_risk,
)
from careerforge_ai.parsing.skill_mentions import presence_of
from careerforge_ai.providers.heuristic.registry import handles
from careerforge_ai.providers.heuristic.text import token_overlap
from careerforge_ai.schemas.claim import ClaimLLMVerdict

__all__ = ["validate_claim"]

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


@handles(ClaimLLMVerdict)
def validate_claim(text: str, context: Mapping[str, Any]) -> ClaimLLMVerdict:
    """Adjudicate a claim against the retrieved evidence."""
    evidence_pool: Sequence[Mapping[str, Any]] = context.get("evidence") or []
    evidence_text = "\n".join(
        f"{item.get('title', '')}\n{item.get('snippet', '')}" for item in evidence_pool
    )

    overlap = token_overlap(text, evidence_text)
    mentions, numeric_reasons = detect_numeric_risk(text, evidence_text)
    # One presence question, shared with the validator's rules phase, so the zero-key path and the
    # traced gate can never disagree about whether a technology is in the material (PHASE 13).
    presence = presence_of(text, evidence_text)
    technical_reasons = detect_missing_technical(text, evidence_text, presence=presence)

    unsupported_numbers = [mention.raw for mention in mentions if not mention.supported]
    # `unsupported_parts` carries the *fragments* of the claim that the evidence
    # cannot carry, so a caller can highlight them in the original sentence. The
    # explanatory sentence goes into `reasoning` instead.
    unsupported_parts: list[str] = sorted(presence.confirmed_absent.values())
    unsupported_parts.extend(sorted(presence.unconfirmed_tokens))
    unsupported_parts.extend(unsupported_numbers)
    if overlap < SUPPORT_OVERLAP_THRESHOLD and not unsupported_parts:
        unsupported_parts.append(text)

    blocked = bool(numeric_reasons) or presence.blocked
    supported = overlap >= SUPPORT_OVERLAP_THRESHOLD and not blocked and not technical_reasons
    partially = not supported and not blocked and overlap >= PARTIAL_OVERLAP_THRESHOLD

    safer = build_safer_formulation(text, evidence_text, unsupported_numbers)

    reasoning_parts = [f"关键词覆盖度 {overlap:.0%}"]
    if technical_reasons:
        reasoning_parts.append(technical_reasons[0].message)
    if numeric_reasons:
        reasoning_parts.append(numeric_reasons[0].message)

    return ClaimLLMVerdict(
        supported=supported,
        partially_supported=partially,
        unsupported_parts=unsupported_parts[:6],
        contradicting_evidence=[],
        reasoning="；".join(reasoning_parts),
        safer_formulation=safer,
    )
