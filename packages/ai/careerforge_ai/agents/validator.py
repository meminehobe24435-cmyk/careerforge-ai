"""ValidatorAgent — the hallucination gate (WF-06).

This is the agent the whole product's promise rests on: a sentence is allowed onto
a resume only when the evidence supports it. The order of work is fixed and is the
entire design (ADR-014)::

    rules  →  retrieve  →  verdict  →  decide
    (free)    (cheap)      (costly)    (arithmetic)

A quantified claim whose unit family appears nowhere in the evidence is rejected by
the rule layer, before a single token is spent. That ordering is what makes the
gate affordable *and* reliable: the cheapest check catches the most dangerous
error, and no model is ever asked to adjudicate a number it cannot verify.

The final status is computed by the same deterministic function the rest of the
codebase uses (:func:`careerforge_ai.scoring.confidence.classify_claim_status`), so
a claim cannot pass here and fail in the graph, or vice versa.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from careerforge_ai.agents.base import (
    AgentOutcome,
    merge_workflow_warnings,
    render_bullets,
)
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.parsing.claim_rules import (
    build_safer_formulation,
    detect_missing_technical,
    detect_numeric_risk,
    detect_superlatives,
)
from careerforge_ai.schemas.claim import (
    ClaimLLMVerdict,
    ClaimReason,
    ClaimSource,
    ClaimValidation,
    SafeRewrite,
)
from careerforge_ai.schemas.common import (
    ClaimRuleCode,
    ClaimStatus,
    DegradationReason,
    EvidenceKind,
)
from careerforge_ai.schemas.evidence import EvidenceLocator, RetrievalHit
from careerforge_ai.scoring.confidence import classify_claim_status, compute_confidence

__all__ = [
    "VALIDATOR_AGENT",
    "ValidatorAgent",
    "build_workflow",
    "decide_phase",
    "evaluate_claim",
    "retrieve_phase",
    "rules_phase",
    "validate_claim_text",
    "verdict_phase",
]

VALIDATOR_AGENT = "validator"

#: Retrieval depth for the evidence arm. Larger than the default because a claim
#: needs *corroboration*, not just one hit: the gate requires two independent
#: sources, so the retriever has to be given the chance to find a second one.
_RETRIEVAL_TOP_K = 8

#: Distinct evidence kinds required before a claim may be called supported. A file
#: and a commit are independent; two files in one repository are not.
_MIN_INDEPENDENT_SOURCES = 2


def build_workflow() -> Workflow:
    """The WF-06 graph."""
    return Workflow(
        name="claim_validate",
        agent=VALIDATOR_AGENT,
        trigger="api",
        description="Verify a resume claim against the evidence base",
        steps=(
            Step(
                name="rules",
                fn=rules_phase,
                agent=VALIDATOR_AGENT,
                description="Deterministic rule layer: numbers, technical nouns, over-claiming",
            ),
            Step(
                name="retrieve",
                fn=retrieve_phase,
                depends_on=("rules",),
                agent=VALIDATOR_AGENT,
                optional=True,
                description="Hybrid retrieval over the evidence base",
            ),
            Step(
                name="verdict",
                fn=verdict_phase,
                depends_on=("rules", "retrieve"),
                agent=VALIDATOR_AGENT,
                optional=True,
                description="Model judgement on what the retrieval actually supports",
            ),
            Step(
                name="decide",
                fn=decide_phase,
                depends_on=("rules", "retrieve", "verdict"),
                agent=VALIDATOR_AGENT,
                description="Deterministic gate: status, confidence and safe rewrite",
            ),
        ),
    )


# ── steps ────────────────────────────────────────────────────────────────────


async def rules_phase(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    claim = str(context.metadata.get("claim") or "")
    evidence_text = str(context.metadata.get("evidence_text") or "")

    mentions, numeric_reasons = detect_numeric_risk(claim, evidence_text)
    technical_reasons = detect_missing_technical(claim, evidence_text)
    superlative_reasons = detect_superlatives(claim)

    reasons: list[ClaimReason] = [*numeric_reasons, *technical_reasons, *superlative_reasons]
    blocked = any(reason.severity == "blocker" for reason in reasons)

    return {
        "mentions": mentions,
        "reasons": reasons,
        "blocked": blocked,
        "unsupported_numbers": [mention.raw for mention in mentions if not mention.supported],
        "missing_technical": [reason.message for reason in technical_reasons],
    }


async def retrieve_phase(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    """Retrieve supporting evidence, or report honestly that we could not."""
    retriever = context.maybe_service("retriever")
    claim = str(context.metadata.get("claim") or "")
    if retriever is None:
        context.metadata["retrieval_unavailable"] = "no retriever configured"
        return {"hits": [], "degraded": True, "reason": "no retriever configured"}

    user_id = context.user_id
    if user_id is None:
        context.metadata["retrieval_unavailable"] = "no user scope"
        return {"hits": [], "degraded": True, "reason": "no user scope"}

    filters = context.metadata.get("retrieval_filters") or None
    result = await retriever.retrieve(
        claim, user_id=user_id, top_k=_RETRIEVAL_TOP_K, filters=filters
    )

    hits = list(result.hits)
    evidence_text = "\n".join(f"{hit.title}\n{hit.snippet}" for hit in hits)
    context.metadata["evidence_text"] = evidence_text
    context.metadata["retrieval"] = {
        "semantic_candidates": result.semantic_candidates,
        "keyword_candidates": result.keyword_candidates,
        "fused_candidates": result.fused_candidates,
        "rrf_k": result.rrf_k,
        "took_ms": result.took_ms,
    }
    return {"hits": hits, "degraded": result.degraded, "reason": None}


async def verdict_phase(context: RunContext, inputs: dict[str, Any]) -> ClaimLLMVerdict | None:
    """Ask the model only when the rules have not already decided."""
    rules = inputs["rules"]
    if rules["blocked"]:
        return None

    hits: list[RetrievalHit] = inputs.get("retrieve", {}).get("hits") or []
    claim = str(context.metadata.get("claim") or "")

    evidence_payload = [{"title": hit.title, "snippet": hit.snippet} for hit in hits]
    evidence_blocks = [f"[{hit.kind.value}] {hit.title} — {hit.snippet[:200]}" for hit in hits]

    # No hits does not mean no evidence. The resume workflow supplies the
    # candidate's material directly, and judging a bullet against an empty pool
    # rejected everything the candidate had actually done.
    supplied = str(context.metadata.get("evidence_text") or "").strip()
    if not evidence_payload and supplied:
        evidence_payload = [{"title": "候选人材料（自述）", "snippet": supplied[:4000]}]
        evidence_blocks = [f"[self_report] 候选人材料 — {supplied[:400]}"]

    return await context.structured(
        "evidence_validator",
        ClaimLLMVerdict,
        context={"source_text": claim, "evidence": evidence_payload},
        claim=claim,
        evidence_blocks=render_bullets(evidence_blocks),
        job_context=str(context.metadata.get("job_context") or "（未指定目标岗位）"),
    )


async def decide_phase(context: RunContext, inputs: dict[str, Any]) -> ClaimValidation:
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

    # A contradiction can come from the rules (a number nothing supports) or from
    # the model (evidence that actively conflicts). Both must force CONTRADICTED,
    # which is the one status the gate never lets through with a rewrite.
    contradiction = bool(rules["blocked"])
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

    if rules["blocked"] or contradiction:
        status = classify_claim_status(evidence_confidence, independent_sources, contradicted=True)
    elif not model_supported:
        status = ClaimStatus.UNSUPPORTED if not hits else ClaimStatus.PARTIALLY_SUPPORTED
    else:
        status = classify_claim_status(evidence_confidence, independent_sources)

    if (
        status is ClaimStatus.SUPPORTED and independent_sources < _MIN_INDEPENDENT_SOURCES
    ):  # pragma: no cover - classify_claim_status already enforces this
        status = ClaimStatus.PARTIALLY_SUPPORTED

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
    """Prefer the model's reformulation; fall back to dropping unsupported clauses."""
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


# ── agent ────────────────────────────────────────────────────────────────────


class ValidatorAgent:
    """Verifies claim text. Stateless; dependencies arrive via RunContext."""

    name = VALIDATOR_AGENT

    def workflow(self) -> Workflow:
        return build_workflow()

    async def run(
        self,
        executor: WorkflowExecutor,
        *,
        claim: str,
        evidence_text: str = "",
        job_context: str = "",
        retrieval_filters: dict[str, Any] | None = None,
        retriever: Any | None = None,
        user_id: UUID | None = None,
    ) -> AgentOutcome:
        # The retriever arrives as an injected service rather than an import: the
        # gate must be runnable with a real hybrid retriever, with a fake, or with
        # none at all -- and the "none" case has to report itself, because an empty
        # evidence set that silently looks like a genuine miss is the worst of the
        # three outcomes.
        services = {"retriever": retriever} if retriever is not None else {}
        output = await executor.run(
            self.workflow(),
            user_id=user_id,
            trigger="api",
            services=services,
            metadata={
                "claim": claim,
                "evidence_text": evidence_text,
                "job_context": job_context,
                "retrieval_filters": retrieval_filters or {},
            },
        )
        validation: ClaimValidation | None = output.get("decide")
        warnings = merge_workflow_warnings(output)
        warnings.extend(str(item) for item in output.metadata.get("warnings", []))

        if validation is not None and output.get("retrieve", {}).get("degraded"):
            reason = output.get("retrieve", {}).get("reason") or "检索不可用"
            warnings.append(f"证据检索降级：{reason}")

        return AgentOutcome(
            value=validation,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=(
                output.degradation_reason if output.degraded else DegradationReason.NONE
            ),
            warnings=warnings,
        )


async def validate_claim_text(
    executor: WorkflowExecutor, claim: str, **kwargs: Any
) -> tuple[ClaimValidation | None, AgentOutcome]:
    """Convenience wrapper returning both the validation and its trace."""
    outcome = await ValidatorAgent().run(executor, claim=claim, **kwargs)
    return outcome.value, outcome


# ── reusable entry point ─────────────────────────────────────────────────────

#: Metadata keys the phases read. Saved and restored around a batch call so a loop
#: over many claims cannot leak state between iterations.
_PHASE_KEYS = ("claim", "evidence_text", "job_context", "retrieval_filters")


async def evaluate_claim(
    context: RunContext,
    claim: str,
    *,
    evidence_text: str = "",
    job_context: str = "",
    retrieval_filters: dict[str, Any] | None = None,
) -> ClaimValidation:
    """Run the full gate for one claim, outside a workflow.

    Used by the resume workflow, which validates every bullet and would otherwise
    duplicate the gate. The phases are the same objects the traced workflow runs, so
    a claim cannot pass here and fail there.
    """
    saved = {key: context.metadata.get(key) for key in _PHASE_KEYS}
    try:
        context.metadata["claim"] = claim
        context.metadata["evidence_text"] = evidence_text
        context.metadata["job_context"] = job_context
        context.metadata["retrieval_filters"] = retrieval_filters or {}

        rules = await rules_phase(context, {})
        retrieval = await retrieve_phase(context, {"rules": rules})
        verdict = await verdict_phase(
            context,
            {
                "rules": rules,
                "retrieve": {
                    **retrieval,
                    "evidence_text": context.metadata.get("evidence_text", ""),
                },
            },
        )
        return await decide_phase(
            context,
            {
                "rules": rules,
                "retrieve": {
                    **retrieval,
                    "evidence_text": context.metadata.get("evidence_text", ""),
                },
                "verdict": verdict,
            },
        )
    finally:
        for key, value in saved.items():
            if value is None:
                context.metadata.pop(key, None)
            else:
                context.metadata[key] = value
