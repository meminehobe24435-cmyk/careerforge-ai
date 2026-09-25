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

The decision policy itself lives in :mod:`careerforge_ai.agents.validator_decide`:
this module gathers inputs (rules, evidence, an optional model verdict) and that one
turns them into a verdict.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from careerforge_ai.agents.base import (
    AgentOutcome,
    merge_workflow_warnings,
    render_bullets,
)
from careerforge_ai.agents.validator_decide import decide_phase
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.parsing.claim_rules import (
    detect_missing_technical,
    detect_numeric_risk,
    detect_ownership_gap,
    detect_superlatives,
)
from careerforge_ai.schemas.claim import (
    ClaimLLMVerdict,
    ClaimReason,
    ClaimValidation,
)
from careerforge_ai.schemas.common import ClaimStatus, DegradationReason
from careerforge_ai.schemas.evidence import RetrievalHit

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
    ownership_gap = detect_ownership_gap(claim, evidence_text)

    reasons: list[ClaimReason] = [*numeric_reasons, *technical_reasons, *superlative_reasons]
    if ownership_gap is not None:
        reasons.append(ownership_gap)
    blocked = any(reason.severity == "blocker" for reason in reasons)

    return {
        "mentions": mentions,
        "reasons": reasons,
        "blocked": blocked,
        # A cap, not a block: an overstated *role* over real work is partially supported, which is
        # a different statement from "nothing here is supported". The decide phase applies it.
        "status_cap": ClaimStatus.PARTIALLY_SUPPORTED if ownership_gap is not None else None,
        "unsupported_numbers": [mention.raw for mention in mentions if not mention.supported],
        "missing_technical": [reason.message for reason in technical_reasons],
    }


async def retrieve_phase(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    """Retrieve supporting evidence, or report honestly that we could not.

    A retriever that *raises* is caught here rather than allowed to fail the step. The step is
    declared optional, and an optional step that fails is recorded as ``None`` — which then made
    the decision phase raise ``AttributeError`` on the missing dict and turned a retrieval outage
    into a 500 (found by PHASE 12's failure-injection pass). A gate that cannot retrieve must say
    so and judge on the rules, not crash.
    """
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
    try:
        result = await retriever.retrieve(
            claim, user_id=user_id, top_k=_RETRIEVAL_TOP_K, filters=filters
        )
    except Exception as exc:
        reason = f"retriever failed: {type(exc).__name__}"
        context.metadata["retrieval_unavailable"] = reason
        return {"hits": [], "degraded": True, "reason": reason}

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

    hits: list[RetrievalHit] = (inputs.get("retrieve") or {}).get("hits") or []
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

        retrieval = output.get("retrieve") or {}
        if validation is not None and retrieval.get("degraded"):
            reason = retrieval.get("reason") or "检索不可用"
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
