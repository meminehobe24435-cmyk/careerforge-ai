"""The claim gate's decision policy.

Split out of :mod:`careerforge_ai.agents.validator` because it has a single reason to
change — *what makes a claim acceptable* — while the workflow module changes when the
gate learns a new place to look for evidence. The phases in ``validator`` gather three
kinds of input (rule findings, retrieval hits, an optional model verdict); everything
in *this* module is the arithmetic that turns them into one verdict and the sentence
explaining it.

The policy has three rules worth stating plainly, because each one is a decision made
about honesty rather than about code:

1. **A blocker is not a contradiction.** ``contradicted`` is reserved for evidence that
   actively conflicts with the claim. A fabricated number that nothing anywhere
   measures is ``unsupported`` — refused, but not accused of being refuted.
2. **A downgrade must explain itself.** A status the reader cannot account for is
   indistinguishable from a bug, so a partially-supported verdict that rests on too few
   independent sources says so.
3. **No rewrite that still asserts something unsupported.** Deleting a number while
   keeping a technology name the evidence cannot carry states the same unsupportable
   thing with the evidence of the edit removed.
"""

from __future__ import annotations

from typing import Any

from careerforge_ai.orchestrator import RunContext
from careerforge_ai.parsing.claim_rules import build_safer_formulation
from careerforge_ai.schemas.claim import (
    ClaimLLMVerdict,
    ClaimReason,
    ClaimSource,
    ClaimValidation,
    SafeRewrite,
)
from careerforge_ai.schemas.common import ClaimRuleCode, ClaimStatus, EvidenceKind
from careerforge_ai.schemas.evidence import EvidenceLocator, RetrievalHit
from careerforge_ai.scoring.confidence import classify_claim_status, compute_confidence

__all__ = ["decide_phase"]

#: Distinct evidence kinds required before a claim may be called supported. A file
#: and a commit are independent; two files in one repository are not.
_MIN_INDEPENDENT_SOURCES = 2


async def decide_phase(context: RunContext, inputs: dict[str, Any]) -> ClaimValidation:
    """Turn the gathered inputs into the final verdict.

    ``inputs`` carries ``rules`` (always), ``retrieve`` and ``verdict`` (when those
    phases ran or were skipped). The status is produced by the same deterministic
    function the rest of the codebase uses, so a claim cannot pass here and fail in
    the graph, or vice versa.
    """
    claim = str(context.metadata.get("claim") or "")
    rules = inputs["rules"]
    retrieval = inputs.get("retrieve") or {"hits": [], "degraded": True}
    hits: list[RetrievalHit] = list(retrieval.get("hits") or [])
    verdict: ClaimLLMVerdict | None = inputs.get("verdict")

    reasons: list[ClaimReason] = list(rules["reasons"])
    sources = [
        ClaimSource(
            evidence_id=hit.evidence_id,
            title=hit.title,
            kind=hit.kind.value,
            relevance=hit.relevance,
            channel=hit.channel,
            locator=hit.locator,
            snippet=hit.snippet[:300],
        )
        for hit in hits
    ]

    independent_sources = len({hit.kind.value for hit in hits})
    evidence_confidence = (
        round(sum(hit.confidence for hit in hits[:5]) / len(hits[:5]), 4) if hits else 0.0
    )

    # No retrieval hits but the caller supplied material directly: that material is
    # one *self-report* source. Scoring it through the same formula is what keeps
    # the answer honest -- it lands around 0.65, which is a PARTIALLY_SUPPORTED
    # verdict ("weak evidence"), never SUPPORTED, because one uncorroborated source
    # is one source by design.
    if not hits and str(context.metadata.get("evidence_text") or "").strip():
        self_report = compute_confidence(
            kind=EvidenceKind.PROJECT,
            locator=EvidenceLocator(section="profile"),
            independent_sources=1,
            extraction_method="heuristic",
        )
        evidence_confidence = self_report.score
        independent_sources = 1
        reasons.append(
            ClaimReason(
                rule=ClaimRuleCode.SINGLE_SOURCE_ONLY,
                severity="info",
                message=(
                    "当前只有候选人自述材料作为证据，属于单来源自述；"
                    "补充代码、提交或文档后才能升级为可信证据"
                ),
            )
        )

    # A contradiction is a claim the evidence *conflicts with* — a timeline that does not line up,
    # or a model reporting evidence that actively disagrees. A blocked rule is not a contradiction:
    # "300% with no comparable measurement anywhere" is unsupported, not disproven, and calling it
    # contradicted tells the candidate their own evidence says otherwise when it says nothing.
    # The distinction also decides whether a safer rewrite is offered: a contradiction never gets
    # one (there is no honest way to reword a sentence the evidence refutes), while a blocked
    # number can be fixed by removing the number.
    contradiction = any(reason.rule == ClaimRuleCode.TIMELINE_CONFLICT for reason in reasons)
    if verdict is not None:
        if verdict.contradicting_evidence:
            contradiction = True
            reasons.append(
                ClaimReason(
                    rule=ClaimRuleCode.LOW_CONFIDENCE_SOURCES,
                    severity="blocker",
                    message="证据与断言冲突：" + "；".join(verdict.contradicting_evidence[:2]),
                )
            )
        if verdict.unsupported_parts:
            reasons.append(
                ClaimReason(
                    rule=ClaimRuleCode.NO_EVIDENCE_MATCH,
                    severity="warning" if verdict.supported else "blocker",
                    message="模型判定以下部分缺乏支撑：" + "；".join(verdict.unsupported_parts[:3]),
                )
            )

    model_supported = verdict.supported if verdict is not None else False
    if verdict is None and not rules["blocked"]:
        # The model step degraded. Fall back to the retrieval signal alone and say
        # so in the reasons rather than pretending the judgement was made.
        model_supported = not rules["missing_technical"] and evidence_confidence >= 0.75
        reasons.append(
            ClaimReason(
                rule=ClaimRuleCode.LOW_CONFIDENCE_SOURCES,
                severity="info",
                message="模型判定不可用，本次结论仅基于确定性规则与证据检索",
            )
        )
    elif verdict is not None and not verdict.supported and not verdict.partially_supported:
        model_supported = False

    if contradiction:
        status = classify_claim_status(evidence_confidence, independent_sources, contradicted=True)
    elif rules["blocked"]:
        # A blocker is the rule layer stating that the evidence cannot carry this claim: an
        # unsupported number, a technology nothing mentions. That is ``UNSUPPORTED`` regardless of
        # how many hits retrieval returned — "partially supported" would soften precisely the
        # claims the gate exists to stop, and ``claim.numeric_rejection_rate`` targets 1.00.
        status = ClaimStatus.UNSUPPORTED
    elif not model_supported:
        status = ClaimStatus.UNSUPPORTED if not hits else ClaimStatus.PARTIALLY_SUPPORTED
    else:
        status = classify_claim_status(evidence_confidence, independent_sources)

    # Say why a claim that looks strong is still only partially supported. One source is not
    # corroboration, and without this note the status reads as an unexplained downgrade — a
    # reader cannot tell it apart from a bug, which is how a gate loses trust.
    already_explained = any(reason.rule == ClaimRuleCode.SINGLE_SOURCE_ONLY for reason in reasons)
    if (
        status is ClaimStatus.PARTIALLY_SUPPORTED
        and independent_sources < _MIN_INDEPENDENT_SOURCES
        and not already_explained
    ):
        reasons.append(
            ClaimReason(
                rule=ClaimRuleCode.SINGLE_SOURCE_ONLY,
                severity="info",
                message=(
                    f"目前只有 {independent_sources} 条独立来源；"
                    f"达到 {_MIN_INDEPENDENT_SOURCES} 条独立来源才能判为 supported。"
                ),
            )
        )

    safe_rewrite = _safe_rewrite(claim, rules, verdict, inputs)

    unknowns: list[str] = []
    if not hits:
        unknowns.append("证据库中没有与这句描述相关的内容")
    if verdict is not None and verdict.unsupported_parts:
        unknowns.extend(verdict.unsupported_parts[:3])

    context.metadata["output_ref"] = {
        "status": status.value,
        "confidence": evidence_confidence,
        "sources": len(sources),
    }

    return ClaimValidation(
        claim=claim,
        status=status,
        confidence=evidence_confidence,
        sources=sources,
        reasons=reasons,
        safe_rewrite=safe_rewrite,
        unknowns=unknowns,
        has_quantified_claim=bool(rules["mentions"]),
        numeric_mentions=list(rules["mentions"]),
        independent_source_count=independent_sources,
        model=context.provider.name if verdict is not None else None,
        prompt_version="evidence_validator@v1" if verdict is not None else None,
    )


def _safe_rewrite(
    claim: str,
    rules: dict[str, Any],
    verdict: ClaimLLMVerdict | None,
    inputs: dict[str, Any],
) -> SafeRewrite | None:
    """Prefer the model's reformulation; fall back to dropping unsupported clauses.

    The number-dropping fallback declines on its own when the sentence would still
    assert something the evidence cannot carry; see
    :func:`careerforge_ai.parsing.claim_rules.build_safer_formulation`.
    """
    evidence_text = str(inputs.get("retrieve", {}).get("evidence_text") or "")
    if not evidence_text:
        evidence_text = str(
            "\n".join(
                f"{hit.title}\n{hit.snippet}"
                for hit in (inputs.get("retrieve", {}).get("hits") or [])
            )
        )

    if verdict is not None and verdict.safer_formulation.strip():
        return SafeRewrite(
            text=verdict.safer_formulation.strip(),
            removed_claims=list(verdict.unsupported_parts[:4]),
            rationale="由证据验证模型给出的降级表述",
            confidence=0.7,
        )

    dropped = list(rules.get("unsupported_numbers") or [])
    candidate = build_safer_formulation(claim, evidence_text, dropped)
    if not candidate:
        return None
    return SafeRewrite(
        text=candidate,
        removed_claims=dropped,
        rationale="移除了证据无法支撑的量化表述与小句",
        confidence=0.5,
    )
