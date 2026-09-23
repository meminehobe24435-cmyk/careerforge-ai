"""MatchAgent — explainable job match scoring (WF-04).

The score is arithmetic, not opinion. ``prepare`` assembles the facts, ``score``
runs the deterministic engine, and ``narrate`` — the only step that touches a model
— writes prose *about* the result without being able to change it.

That separation is enforced structurally rather than by instruction: the narrative
schema has no numeric field at all, so there is no shape in which a model could
return a different score even if it wanted to. It also means the agent still
produces a complete, explainable result with no API key, which is the whole point
of the deterministic design.
"""

from __future__ import annotations

from typing import Any

from careerforge_ai.agents.base import AgentOutcome, merge_workflow_warnings, render_bullets
from careerforge_ai.graph import GraphBuildResult
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.parsing.skill_taxonomy import skill_categories
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.match import ExtractedMatchNarrative, JobMatchResult
from careerforge_ai.schemas.profile import CandidateProfile
from careerforge_ai.scoring.match import compute_job_match

__all__ = ["MATCH_AGENT", "MatchAgent", "build_workflow", "compute_match"]

MATCH_AGENT = "match"

#: How many strengths and gaps to show the narrator. The full lists stay in the
#: result; the prompt only needs enough to characterise the outcome.
_NARRATIVE_ITEMS = 6


def build_workflow() -> Workflow:
    """The WF-04 graph: prepare → score → narrate."""
    return Workflow(
        name="job_match",
        agent=MATCH_AGENT,
        trigger="api",
        description="Score a candidate against a job description, deterministically",
        steps=(
            Step(
                name="prepare",
                fn=_prepare,
                agent=MATCH_AGENT,
                description="Assemble the profile, job and per-skill evidence maps",
            ),
            Step(
                name="score",
                fn=_score,
                depends_on=("prepare",),
                agent=MATCH_AGENT,
                description="Deterministic five-dimension scoring with a full derivation",
            ),
            Step(
                name="narrate",
                fn=_narrate,
                depends_on=("prepare", "score"),
                agent=MATCH_AGENT,
                optional=True,
                description="Model-written prose about the result; cannot alter it",
            ),
        ),
    )


# ── steps ────────────────────────────────────────────────────────────────────


async def _prepare(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    job = context.maybe_service("job")
    profile = context.maybe_service("profile")
    graph = context.maybe_service("graph")

    if job is None:
        job = context.metadata.get("job")
    if profile is None:
        profile = context.metadata.get("profile")
    if graph is None:
        graph = context.metadata.get("graph")

    if not isinstance(job, JDAnalysis):
        raise ValueError("job_match requires a JDAnalysis in services['job']")
    if not isinstance(profile, CandidateProfile):
        raise ValueError("job_match requires a CandidateProfile in services['profile']")

    skill_evidence: dict[str, list[Any]] = {}
    skill_confidence: dict[str, float] = {}
    if isinstance(graph, GraphBuildResult):
        skill_evidence = {key: list(value) for key, value in graph.skill_evidence.items()}
        skill_confidence = dict(graph.skill_confidence)
    else:
        # Without a graph the evidence dimension has nothing to measure. That is a
        # real limitation, not a neutral default, so it is recorded rather than
        # silently scored as zero evidence.
        context.metadata.setdefault("warnings", []).append(
            "未提供证据图谱，证据强度维度将按『无证据』计算"
        )

    categories = skill_categories(
        [skill.canonical_id for skill in job.all_skills if skill.canonical_id]
        + [item.skill.canonical_id for item in profile.skills]
    )

    return {
        "job": job,
        "profile": profile,
        "skill_evidence": skill_evidence,
        "skill_confidence": skill_confidence,
        "categories": categories,
        "has_graph": isinstance(graph, GraphBuildResult),
    }


async def _score(context: RunContext, inputs: dict[str, Any]) -> JobMatchResult:
    prepared = inputs["prepare"]
    result = compute_job_match(
        job=prepared["job"],
        profile=prepared["profile"],
        skill_evidence=prepared["skill_evidence"],
        skill_confidence=prepared["skill_confidence"],
        skill_categories=prepared["categories"],
    )

    context.metadata["input_ref"] = {
        "role": prepared["job"].role,
        "company": prepared["job"].company,
        "required_skills": len(prepared["job"].required_skills),
    }
    context.metadata["output_ref"] = {
        "score": result.score,
        "strengths": len(result.strengths),
        "gaps": len(result.gaps),
        "unknowns": len(result.unknowns),
    }
    return result


async def _narrate(context: RunContext, inputs: dict[str, Any]) -> ExtractedMatchNarrative | None:
    """Write prose about the score. Cannot change the score — the schema forbids it."""
    prepared = inputs["prepare"]
    result: JobMatchResult = inputs["score"]
    job: JDAnalysis = prepared["job"]

    return await context.structured(
        "match_explainer",
        ExtractedMatchNarrative,
        context={"source_text": f"{job.role} @ {job.company or ''}"},
        role=job.role or "（未命名岗位）",
        company=job.company or "（未提供公司名）",
        total_score=f"{result.score:.1f}",
        dimension_summary=render_bullets(
            [
                f"{dimension.label}：{dimension.score:.0f} 分（权重 {dimension.weight:.0%}）"
                for dimension in result.dimensions.values()
            ]
        ),
        strengths=render_bullets(
            [f"{item.display_name} — {item.reason}" for item in result.strengths[:_NARRATIVE_ITEMS]]
        ),
        gaps=render_bullets(
            [
                f"{item.display_name}（{item.severity.value}）"
                + (f"，JD 原文：{item.jd_evidence}" if item.jd_evidence else "")
                for item in result.top_gaps[:_NARRATIVE_ITEMS]
            ]
        ),
        unknowns=render_bullets(
            [
                f"{item.display_name} — {item.ask_user}"
                for item in result.unknowns[:_NARRATIVE_ITEMS]
            ]
        ),
    )


# ── agent ────────────────────────────────────────────────────────────────────


class MatchAgent:
    """Scores a candidate against a job. Stateless."""

    name = MATCH_AGENT

    def workflow(self) -> Workflow:
        return build_workflow()

    async def run(
        self,
        executor: WorkflowExecutor,
        *,
        job: JDAnalysis,
        profile: CandidateProfile,
        graph: GraphBuildResult | None = None,
    ) -> AgentOutcome:
        output = await executor.run(
            self.workflow(),
            services={"job": job, "profile": profile, "graph": graph}
            if graph
            else {
                "job": job,
                "profile": profile,
            },
            trigger="api",
        )
        result: JobMatchResult | None = output.get("score")
        warnings = merge_workflow_warnings(output)
        warnings.extend(str(item) for item in output.metadata.get("warnings", []))

        if result is not None:
            narrative: ExtractedMatchNarrative | None = output.get("narrate")
            # The deterministic explanation is always present; the model's prose is
            # an addition. When the model step degrades, the user still gets a
            # reason for the number rather than an empty panel.
            result.narrative = (
                narrative.summary.strip() if narrative and narrative.summary.strip() else ""
            )
            if narrative and narrative.caveats:
                result.why.notes.extend(str(item) for item in narrative.caveats[:4])
            result.degraded = output.degraded

        return AgentOutcome(
            value=result,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=output.degradation_reason,
            warnings=warnings,
        )


async def compute_match(
    executor: WorkflowExecutor,
    *,
    job: JDAnalysis,
    profile: CandidateProfile,
    graph: GraphBuildResult | None = None,
) -> tuple[JobMatchResult | None, AgentOutcome]:
    """Convenience wrapper returning both the result and its trace."""
    outcome = await MatchAgent().run(executor, job=job, profile=profile, graph=graph)
    return outcome.value, outcome
