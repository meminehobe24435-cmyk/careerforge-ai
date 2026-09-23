"""ResumeAgent — resume Copilot where every generated line passes the gate (WF-05).

The workflow order is the product::

    load_ctx → generate → validate → gate → assemble

``validate`` runs the *same* gate as the ValidatorAgent over every generated
bullet, and ``gate`` decides what may actually reach the resume. A rejected claim
is not silently dropped: it comes back with the reason and with a suggestion for
how to make it provable next time, because "write it better" is useless advice
compared to "put the benchmark in the repository and then this sentence is true".

The integrity score is the honest headline: the share of bullets whose claims the
evidence supports. A resume that scores 0.6 is telling the candidate they have work
to do, which is more useful than a version that reads well and falls apart in an
interview.
"""

from __future__ import annotations

from typing import Any

from careerforge_ai.agents.base import (
    AgentOutcome,
    merge_workflow_warnings,
    render_bullets,
    truncate_for_prompt,
)
from careerforge_ai.agents.validator import evaluate_claim
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.schemas.claim import (
    ClaimRuleCode,
    ClaimStatus,
    ClaimValidation,
    ExtractedResumeOptimization,
    ResumeBullet,
    ResumeOptimizationResult,
)
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile

__all__ = ["RESUME_AGENT", "ResumeAgent", "build_workflow", "optimize_resume"]

RESUME_AGENT = "resume"

#: Characters of profile material to place in the prompt.
_MATERIAL_BUDGET = 4000

#: How to make each blocked rule provable. Keyed by rule code so the advice matches
#: the actual failure rather than being generic encouragement.
_RULE_ADVICE: dict[str, str] = {
    ClaimRuleCode.NUMERIC_WITHOUT_EVIDENCE.value: (
        "补上实测记录（把 benchmark 或测试输出提交到仓库），或删掉具体数字"
    ),
    ClaimRuleCode.SKILL_NOT_IN_GRAPH.value: (
        "把用到该技术的代码推到 GitHub、补充项目文档，或从这句话里去掉它"
    ),
    ClaimRuleCode.NO_EVIDENCE_MATCH.value: (
        "在证据库中补充对应材料：项目文档、README 或可定位的代码"
    ),
    ClaimRuleCode.SUPERLATIVE_LANGUAGE.value: "把「精通/主导」改成可验证的具体动作与范围",
    ClaimRuleCode.LOW_CONFIDENCE_SOURCES.value: (
        "补充第二类来源：代码之外的 README、文档或提交记录，单来源不足以支撑断言"
    ),
    ClaimRuleCode.SINGLE_SOURCE_ONLY.value: "增加一个独立来源（不同类别的材料）",
    ClaimRuleCode.TIMELINE_CONFLICT.value: "核对时间线，确保与材料一致",
}


def build_workflow() -> Workflow:
    """The WF-05 graph."""
    return Workflow(
        name="resume_optimize",
        agent=RESUME_AGENT,
        trigger="api",
        description="Rewrite resume bullets for a target job, with every claim verified",
        steps=(
            Step(
                name="load_ctx",
                fn=_load_ctx,
                agent=RESUME_AGENT,
                description="Assemble the current bullets, target job and candidate material",
            ),
            Step(
                name="generate",
                fn=_generate,
                depends_on=("load_ctx",),
                agent=RESUME_AGENT,
                description="Bullet-level rewrite under the no-new-facts constraint",
            ),
            Step(
                name="validate",
                fn=_validate,
                depends_on=("generate",),
                agent=RESUME_AGENT,
                description="Run the claim gate over every generated bullet",
            ),
            Step(
                name="gate",
                fn=_gate,
                depends_on=("load_ctx", "generate", "validate"),
                agent=RESUME_AGENT,
                description="Decide what may reach the resume and score its integrity",
            ),
            Step(
                name="assemble",
                fn=_assemble,
                depends_on=("gate",),
                agent=RESUME_AGENT,
                description="Build the result, including advice for blocked claims",
            ),
        ),
    )


# ── steps ────────────────────────────────────────────────────────────────────


def _profile_material(profile: CandidateProfile, *, budget: int = _MATERIAL_BUDGET) -> str:
    lines: list[str] = []
    if profile.summary:
        lines.append(f"自我总结：{profile.summary}")
    for experience in profile.experiences:
        lines.append(f"实习/工作：{experience.company} · {experience.title}")
        if experience.description:
            lines.append(f"  描述：{experience.description}")
        lines.extend(f"  要点：{item}" for item in experience.highlights)
    for project in profile.projects:
        lines.append(f"项目：{project.name}")
        if project.role:
            lines.append(f"  角色：{project.role}")
        if project.summary:
            lines.append(f"  概述：{project.summary}")
        if project.description:
            lines.append(f"  描述：{project.description}")
        if project.tech_stack:
            lines.append(f"  技术栈：{'、'.join(project.tech_stack)}")
    if profile.skills:
        lines.append("技能：" + "、".join(item.skill.display_name for item in profile.skills))
    material = "\n".join(lines)
    clipped, _ = truncate_for_prompt(material, budget=budget)
    return clipped


def _default_bullets(profile: CandidateProfile) -> list[dict[str, str]]:
    """Derive current bullets when the caller has none.

    Existing highlights are the honest starting point: rewriting what the candidate
    already wrote is a much smaller claim than composing from nothing, and it keeps
    the diff meaningful.
    """
    bullets: list[dict[str, str]] = []
    for experience in profile.experiences:
        for highlight in experience.highlights:
            bullets.append({"section": "experience", "text": highlight})
        if not experience.highlights and experience.description:
            bullets.append({"section": "experience", "text": experience.description})
    for project in profile.projects:
        text = project.summary or project.description
        if text:
            bullets.append({"section": "project", "text": text})
    if not bullets and profile.summary:
        bullets.append({"section": "summary", "text": profile.summary})
    return bullets


async def _load_ctx(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    profile = context.maybe_service("profile")
    job = context.maybe_service("job")
    if not isinstance(profile, CandidateProfile):
        raise ValueError("resume_optimize requires a CandidateProfile in services['profile']")

    explicit = context.maybe_service("bullets")
    bullets = (
        [
            {"section": str(item.get("section", "project")), "text": str(item.get("text", ""))}
            for item in explicit
        ]
        if explicit
        else _default_bullets(profile)
    )
    bullets = [item for item in bullets if item["text"].strip()]

    if not bullets:
        context.metadata.setdefault("warnings", []).append(
            "没有可供改写的简历要点，请在画像中补充项目或实习描述"
        )

    material = _profile_material(profile)
    # The material also becomes the evidence text the gate reads, so a bullet making
    # a claim the profile itself does not support is caught even with no retriever.
    context.metadata["evidence_text"] = material

    return {
        "profile": profile,
        "job": job if isinstance(job, JDAnalysis) else None,
        "bullets": bullets,
        "material": material,
    }


async def _generate(context: RunContext, inputs: dict[str, Any]) -> ExtractedResumeOptimization:
    prepared = inputs["load_ctx"]
    job: JDAnalysis | None = prepared["job"]

    if not prepared["bullets"]:
        return ExtractedResumeOptimization(bullets=[])

    return await context.structured(
        "resume_optimizer",
        ExtractedResumeOptimization,
        # The bullets also travel through ``context``: that is the port's structured
        # channel, and it is what lets the deterministic provider produce a real diff
        # instead of parsing its own rendered prompt back out of prose.
        context={
            "source_text": prepared["material"],
            "bullets": prepared["bullets"],
            "job_role": job.role if job else "",
            "required_skills": [skill.raw_text for skill in job.required_skills] if job else [],
        },
        job_role=(job.role if job else "（未指定岗位）"),
        required_skills=render_bullets(
            [skill.raw_text for skill in job.required_skills] if job else []
        ),
        candidate_material=prepared["material"],
        current_bullets=render_bullets(
            [f"[{item['section']}] {item['text']}" for item in prepared["bullets"]]
        ),
        locale="zh-CN",
    )


async def _validate(context: RunContext, inputs: dict[str, Any]) -> list[ClaimValidation]:
    """Run the gate over every generated bullet."""
    generated: ExtractedResumeOptimization = inputs["generate"]
    validations: list[ClaimValidation] = []
    for bullet in generated.bullets:
        target = (bullet.optimized or bullet.original).strip()
        validation = await evaluate_claim(
            context,
            target,
            evidence_text=str(context.metadata.get("evidence_text") or ""),
        )
        validations.append(validation)
    return validations


async def _gate(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    generated: ExtractedResumeOptimization = inputs["generate"]
    validations: list[ClaimValidation] = inputs["validate"]
    prepared = inputs["load_ctx"]

    accepted: list[ResumeBullet] = []
    rejected: list[ClaimValidation] = []
    suggestions: list[str] = []

    for index, bullet in enumerate(generated.bullets):
        validation = validations[index] if index < len(validations) else None
        if validation is None or validation.status.allows_resume_inclusion:
            accepted.append(bullet)
            continue
        rejected.append(validation)
        suggestions.extend(_advice_for(validation))

    total = len(generated.bullets)
    integrity = round(len(accepted) / total, 4) if total else 0.0

    context.metadata["output_ref"] = {
        "bullets": total,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "integrity": integrity,
    }
    if rejected:
        context.metadata.setdefault("warnings", []).append(
            f"{len(rejected)} 条改写未通过证据门禁，已阻止写入简历"
        )

    return {
        "accepted": accepted,
        "rejected": rejected,
        "validations": validations,
        "integrity": integrity,
        "suggestions": suggestions,
        "original_bullets": prepared["bullets"],
    }


def _advice_for(validation: ClaimValidation) -> list[str]:
    """Turn a rejection into a concrete next action, de-duplicated and capped."""
    advice: list[str] = []
    for reason in validation.reasons:
        if reason.severity == "info":
            continue
        text = _RULE_ADVICE.get(str(reason.rule))
        if text and text not in advice:
            advice.append(text)
    if not advice and validation.status is ClaimStatus.UNSUPPORTED:
        advice.append("先补充材料，再让系统基于证据重写这句话")
    return advice[:2]


async def _assemble(context: RunContext, inputs: dict[str, Any]) -> ResumeOptimizationResult:
    gated = inputs["gate"]
    validations: list[ClaimValidation] = gated["validations"]

    stats: dict[str, int] = {}
    for validation in validations:
        stats[validation.status.value] = stats.get(validation.status.value, 0) + 1

    suggestions = gated["suggestions"]
    context.metadata["suggestions"] = suggestions
    return ResumeOptimizationResult(
        bullets=gated["accepted"],
        validations=validations,
        integrity_score=gated["integrity"],
        claim_stats=stats,
        rejected=gated["rejected"],
        degraded=context.degraded,
        new_evidence_suggestions=list(dict.fromkeys(suggestions)),
    )


# ── agent ────────────────────────────────────────────────────────────────────


class ResumeAgent:
    """Rewrites resume bullets and gates every one of them. Stateless."""

    name = RESUME_AGENT

    def workflow(self) -> Workflow:
        return build_workflow()

    async def run(
        self,
        executor: WorkflowExecutor,
        *,
        profile: CandidateProfile,
        job: JDAnalysis | None = None,
        bullets: list[dict[str, str]] | None = None,
        retriever: Any | None = None,
        user_id: Any | None = None,
    ) -> AgentOutcome:
        services: dict[str, Any] = {"profile": profile}
        if job is not None:
            services["job"] = job
        if bullets:
            services["bullets"] = bullets
        if retriever is not None:
            services["retriever"] = retriever

        output = await executor.run(
            self.workflow(), user_id=user_id, trigger="api", services=services
        )
        result: ResumeOptimizationResult | None = output.get("assemble")
        warnings = merge_workflow_warnings(output)
        warnings.extend(str(item) for item in output.metadata.get("warnings", []))

        return AgentOutcome(
            value=result,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=output.degradation_reason,
            warnings=warnings,
        )


async def optimize_resume(
    executor: WorkflowExecutor, **kwargs: Any
) -> tuple[ResumeOptimizationResult | None, AgentOutcome]:
    """Convenience wrapper returning both the optimisation and its trace."""
    outcome = await ResumeAgent().run(executor, **kwargs)
    return outcome.value, outcome
