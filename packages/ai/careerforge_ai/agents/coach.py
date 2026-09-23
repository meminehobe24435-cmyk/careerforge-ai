"""CoachAgent — skill gaps to a 30-day plan whose outputs are provable (WF-08).

The rule that defines this agent: **every gap ends in an artefact**. A course link
does not close a gap in this system, because the product's entire premise is that
unverifiable claims are worthless. A working repository, a commit history and a
README are outputs; "understanding" is not.

Priority is computed, not narrated. ``compute_skill_gap_matrix`` blends requirement
weight, gap severity and how often the skill appears across the user's own tracked
jobs; the model is then told to order the plan by that priority rather than by its
own sense of what is interesting to learn.
"""

from __future__ import annotations

from typing import Any

from careerforge_ai.agents.base import AgentOutcome, merge_workflow_warnings, render_bullets
from careerforge_ai.graph import GraphBuildResult
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.parsing.skill_taxonomy import skill_categories
from careerforge_ai.schemas.job import JDAnalysis, SkillGapMatrix
from careerforge_ai.schemas.learning import (
    ExtractedLearningPlan,
    LearningPlan,
    LearningPlanWeek,
    MiniProject,
)
from careerforge_ai.schemas.profile import CandidateProfile
from careerforge_ai.scoring.skill_gap import compute_skill_gap_matrix

__all__ = ["COACH_AGENT", "CoachAgent", "build_workflow", "build_learning_plan"]

COACH_AGENT = "coach"

_DEFAULT_HORIZON_DAYS = 30

#: Gaps handed to the planner. The top of the list is what actually gets worked on;
#: a 30-day plan covering nine skills is a wish list, not a plan.
_MAX_PLANNED_GAPS = 5


def build_workflow() -> Workflow:
    """The WF-08 graph: matrix → prioritise → plan → assemble."""
    return Workflow(
        name="skill_gap",
        agent=COACH_AGENT,
        trigger="api",
        description="Turn a target job into a prioritised gap matrix and a 30-day plan",
        steps=(
            Step(
                name="matrix",
                fn=_matrix,
                agent=COACH_AGENT,
                description="Deterministic gap matrix with computed priorities",
            ),
            Step(
                name="prioritise",
                fn=_prioritise,
                depends_on=("matrix",),
                agent=COACH_AGENT,
                description="Select the gaps worth a 30-day horizon",
            ),
            Step(
                name="plan",
                fn=_plan,
                depends_on=("prioritise",),
                agent=COACH_AGENT,
                optional=True,
                description="Weeks and mini projects, ordered by the computed priority",
            ),
            Step(
                name="assemble",
                fn=_assemble,
                depends_on=("matrix", "prioritise", "plan"),
                agent=COACH_AGENT,
                description="Build the LearningPlan, falling back when the model is unavailable",
            ),
        ),
    )


# ── steps ────────────────────────────────────────────────────────────────────


async def _matrix(context: RunContext, inputs: dict[str, Any]) -> SkillGapMatrix:
    job = context.maybe_service("job")
    profile = context.maybe_service("profile")
    if not isinstance(job, JDAnalysis):
        raise ValueError("skill_gap requires a JDAnalysis in services['job']")
    if not isinstance(profile, CandidateProfile):
        raise ValueError("skill_gap requires a CandidateProfile in services['profile']")

    graph = context.maybe_service("graph")
    skill_evidence = graph.skill_evidence if isinstance(graph, GraphBuildResult) else {}
    skill_confidence = graph.skill_confidence if isinstance(graph, GraphBuildResult) else {}
    if not isinstance(graph, GraphBuildResult):
        context.metadata.setdefault("warnings", []).append(
            "未提供证据图谱，缺口判定只能依据简历自述的技能等级"
        )

    categories = skill_categories(
        [skill.canonical_id for skill in job.all_skills if skill.canonical_id]
        + [item.skill.canonical_id for item in profile.skills]
    )

    matrix = compute_skill_gap_matrix(
        job=job,
        profile=profile,
        skill_categories=categories,
        evidence_by_skill=skill_evidence,
        skill_confidence=skill_confidence,
        market_frequency=context.maybe_service("market_frequency") or {},
    )
    matrix.job_id = context.metadata.get("job_id")
    return matrix


async def _prioritise(context: RunContext, inputs: dict[str, Any]) -> list[dict[str, Any]]:
    matrix: SkillGapMatrix = inputs["matrix"]
    selected = [row for row in matrix.rows if row.gap_level.value != "none"][:_MAX_PLANNED_GAPS]

    if not selected:
        context.metadata.setdefault("warnings", []).append(
            "该岗位没有需要补强的技能缺口，无需生成学习计划"
        )
    return [
        {
            "canonical_id": row.canonical_id,
            "display_name": row.display_name,
            "requirement": row.requirement.value,
            "gap_level": row.gap_level.value,
            "priority": row.priority,
            "rationale": row.rationale,
        }
        for row in selected
    ]


async def _plan(context: RunContext, inputs: dict[str, Any]) -> ExtractedLearningPlan | None:
    gaps = inputs["prioritise"]
    if not gaps:
        return None

    job = context.maybe_service("job")
    profile = context.maybe_service("profile")
    horizon = int(context.metadata.get("horizon_days") or _DEFAULT_HORIZON_DAYS)

    return await context.structured(
        "skill_gap",
        ExtractedLearningPlan,
        context={
            "source_text": "; ".join(gap["display_name"] for gap in gaps),
            "gaps": gaps,
            # Also passed through the structured channel: the deterministic planner
            # reads context, not the rendered prompt, and reading the prompt back
            # would make it depend on prose formatting.
            "horizon_days": horizon,
        },
        target_role=(job.role if isinstance(job, JDAnalysis) else "（未指定岗位）"),
        gap_rows=render_bullets(
            [
                f"{gap['display_name']}（{gap['requirement']}，缺口 {gap['gap_level']}，"
                f"优先级 {gap['priority']:.0f}）"
                for gap in gaps
            ]
        ),
        horizon_days=str(horizon),
        candidate_material=(
            "、".join(item.skill.display_name for item in profile.skills)
            if isinstance(profile, CandidateProfile)
            else "（未提供画像）"
        ),
    )


async def _assemble(context: RunContext, inputs: dict[str, Any]) -> LearningPlan:
    matrix: SkillGapMatrix = inputs["matrix"]
    gaps = inputs["prioritise"]
    plan: ExtractedLearningPlan | None = inputs.get("plan")
    horizon = int(context.metadata.get("horizon_days") or _DEFAULT_HORIZON_DAYS)

    # The extracted models are deliberately separate from the domain models, so the
    # LLM-facing contract can change without touching stored shapes. Conversion is
    # explicit rather than relying on coercion.
    weeks = [LearningPlanWeek(**item.model_dump()) for item in plan.weeks] if plan else []
    mini_projects = (
        [MiniProject(**item.model_dump()) for item in plan.mini_projects] if plan else []
    )

    if not weeks:
        # Deterministic fallback: the structure of a plan does not need a model, and
        # an empty page helps nobody.
        weeks = _fallback_weeks(gaps, horizon)
        context.metadata.setdefault("warnings", []).append(
            "模型不可用，已生成结构化周计划骨架；mini project 需人工补充"
        )

    plan_model = LearningPlan(
        user_id=context.user_id,
        job_id=matrix.job_id,
        horizon_days=horizon,
        title=plan.title if plan and plan.title else f"{horizon} 天补强计划",
        summary=(
            plan.summary
            if plan and plan.summary
            else f"针对 {len(gaps)} 个优先缺口，按「概念 → 原理 → 小项目 → 证据化」四段式推进。"
        ),
        weeks=weeks,
        mini_projects=mini_projects,
        priority_order=[gap["canonical_id"] for gap in gaps],
        generated_at=matrix.generated_at,
        model=context.provider.name if plan else None,
        prompt_version="skill_gap@v1" if plan else None,
        degraded=context.degraded,
    )

    context.metadata["output_ref"] = {
        "gaps": len(gaps),
        "high_priority": len([gap for gap in gaps if gap["gap_level"] == "high"]),
        "weeks": len(plan_model.weeks),
        "mini_projects": len(plan_model.mini_projects),
    }
    return plan_model


def _fallback_weeks(gaps: list[dict[str, Any]], horizon_days: int) -> list[LearningPlanWeek]:
    themes = (
        ("打基础：概念与最小可运行示例", "搭出可运行的最小示例", "一个能在本机跑起来的程序"),
        ("补原理：把机制讲清楚", "能解释核心机制与边界条件", "一份含至少 3 个「为什么」的技术笔记"),
        ("做小项目：把知识变成作品", "完成一个可演示的小项目", "一个可运行、可演示的 Mini Project"),
        ("上证据：把项目变成简历资产", "补 README 与验收说明", "GitHub 仓库 + 可验证的成果描述"),
    )
    weeks_count = max(1, min(12, horizon_days // 7))
    focus = gaps[0]["display_name"] if gaps else ""
    return [
        LearningPlanWeek(
            week=index + 1,
            theme=themes[min(index, len(themes) - 1)][0],
            goals=[
                f"{focus}：{themes[min(index, len(themes) - 1)][0]}"
                if focus
                else themes[min(index, len(themes) - 1)][0]
            ],
            focus_skills=[focus] if focus else [],
            resources=["官方文档", "一个可运行的开源示例"],
            output=themes[min(index, len(themes) - 1)][1],
            verification=themes[min(index, len(themes) - 1)][2],
        )
        for index in range(weeks_count)
    ]


# ── agent ────────────────────────────────────────────────────────────────────


class CoachAgent:
    """Builds gap matrices and learning plans. Stateless."""

    name = COACH_AGENT

    def workflow(self) -> Workflow:
        return build_workflow()

    async def run(
        self,
        executor: WorkflowExecutor,
        *,
        job: JDAnalysis,
        profile: CandidateProfile,
        graph: GraphBuildResult | None = None,
        horizon_days: int = _DEFAULT_HORIZON_DAYS,
        market_frequency: dict[str, float] | None = None,
    ) -> AgentOutcome:
        services: dict[str, Any] = {"job": job, "profile": profile}
        if graph is not None:
            services["graph"] = graph
        if market_frequency:
            services["market_frequency"] = market_frequency

        output = await executor.run(
            self.workflow(),
            trigger="api",
            services=services,
            metadata={"horizon_days": horizon_days},
        )
        result: LearningPlan | None = output.get("assemble")
        matrix: SkillGapMatrix | None = output.get("matrix")
        warnings = merge_workflow_warnings(output)
        warnings.extend(str(item) for item in output.metadata.get("warnings", []))

        return AgentOutcome(
            value=result,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=output.degradation_reason,
            warnings=warnings,
            # The gap matrix is a product in its own right — the gap page renders it
            # directly — so it travels alongside the plan rather than being dropped.
            extras={"matrix": matrix},
        )


async def build_learning_plan(
    executor: WorkflowExecutor, **kwargs: Any
) -> tuple[LearningPlan | None, AgentOutcome]:
    """Convenience wrapper returning both the plan and its trace."""
    outcome = await CoachAgent().run(executor, **kwargs)
    return outcome.value, outcome
