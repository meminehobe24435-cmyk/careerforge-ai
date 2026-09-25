"""Interview turn execution: ask, evaluate and adapt."""

from __future__ import annotations

from typing import Any

from careerforge_ai.agents.base import render_bullets
from careerforge_ai.agents.interview.plan import (
    INTERVIEW_AGENT,
    _candidate_material,
    _covered_topics,
    _pick_topic,
    _plan_topics,
    _recent_turns,
    mark_plan_coverage,
    next_difficulty,
)
from careerforge_ai.orchestrator import RunContext, Step, Workflow
from careerforge_ai.schemas.common import (
    DifficultyLevel,
)
from careerforge_ai.schemas.interview import (
    ExtractedQuestion,
    ExtractedTurnEvaluation,
    InterviewPlanItem,
    InterviewSession,
    InterviewTurn,
    TurnEvaluation,
)
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile

# ── workflows ────────────────────────────────────────────────────────────────


def build_start_workflow() -> Workflow:
    """WF-07a: plan the interview and ask the first question."""
    return Workflow(
        name="interview_start",
        agent=INTERVIEW_AGENT,
        trigger="api",
        description="Build the question plan and ask the opening question",
        steps=(
            Step(name="plan", fn=_start_plan, agent=INTERVIEW_AGENT, description="Topic plan"),
            Step(
                name="question",
                fn=_ask,
                depends_on=("plan",),
                agent=INTERVIEW_AGENT,
                description="Opening question",
            ),
        ),
    )


def build_turn_workflow() -> Workflow:
    """WF-07b: evaluate an answer and ask the next question."""
    return Workflow(
        name="interview_turn",
        agent=INTERVIEW_AGENT,
        trigger="api",
        description="Evaluate one answer, adapt the difficulty and ask the next question",
        steps=(
            Step(
                name="evaluate",
                fn=_evaluate_turn,
                agent=INTERVIEW_AGENT,
                description="Score the answer",
            ),
            Step(
                name="adapt",
                fn=_adapt,
                depends_on=("evaluate",),
                agent=INTERVIEW_AGENT,
                description="Deterministic difficulty transition",
            ),
            Step(
                name="question",
                fn=_ask,
                depends_on=("adapt",),
                agent=INTERVIEW_AGENT,
                description="Next question at the new level",
            ),
        ),
    )


# ── start ────────────────────────────────────────────────────────────────────


async def _start_plan(context: RunContext, inputs: dict[str, Any]) -> list[InterviewPlanItem]:
    job = context.maybe_service("job")
    graph = context.maybe_service("graph")
    plan = _plan_topics(job if isinstance(job, JDAnalysis) else None, graph)
    context.metadata["output_ref"] = {"topics": len(plan)}
    return plan


async def _ask(context: RunContext, inputs: dict[str, Any]) -> InterviewTurn:
    session: InterviewSession = context.service("session")
    profile = context.maybe_service("profile")
    job = context.maybe_service("job")

    # Three call sites reach this step: the start workflow (plan output available),
    # the turn workflow (adapt output available), and neither (fall back to the
    # session's own plan). Reading `session.plan` unconditionally would fail on the
    # first of those, because the plan is assigned after the workflow returns.
    adapt = inputs.get("adapt")
    if isinstance(adapt, dict):
        plan_item = adapt["next"]
        current_level = DifficultyLevel.from_level(int(adapt["level"]))
    elif inputs.get("plan"):
        plan_item = inputs["plan"][0]
        current_level = session.current_level
    else:
        plan_item = _pick_topic(session)
        current_level = session.current_level

    question: ExtractedQuestion = await context.structured(
        "interviewer",
        ExtractedQuestion,
        context={
            "source_text": _candidate_material(
                profile if isinstance(profile, CandidateProfile) else None
            ),
            # The topic, level, mode and progress also travel through the structured
            # channel: the deterministic interviewer reads context, not the rendered
            # prompt, and without them it asked the same generic question every turn.
            "topic": plan_item.topic,
            "level": current_level.level,
            "mode": session.mode.value,
            "asked_count": session.turn_count,
        },
        mode=session.mode.value,
        target_role=(job.role if isinstance(job, JDAnalysis) else "（未指定岗位）"),
        current_level=f"{current_level.value} (L{current_level.level})",
        topic=plan_item.topic,
        covered_topics=_covered_topics(session),
        asked_count=str(session.turn_count),
        candidate_material=_candidate_material(
            profile if isinstance(profile, CandidateProfile) else None
        ),
        job_requirements=render_bullets(
            [f"{skill.raw_text}（{skill.requirement.value}）" for skill in job.all_skills]
            if isinstance(job, JDAnalysis)
            else []
        ),
        recent_turns=_recent_turns(session),
    )

    return InterviewTurn(
        turn_index=session.next_turn_index(),
        role="interviewer",
        content=question.question,
        topic=question.topic,
        question_level=question.level,
        # ``tokens`` / ``latency_ms`` are left unset on purpose: this builder never measured
        # them, and a written ``0`` would claim it had. The model call's real usage lives on
        # the step trace (``StepTrace.usage``), which is where the AI Runs page reads it.
    )


# ── turn ─────────────────────────────────────────────────────────────────────


async def _evaluate_turn(context: RunContext, inputs: dict[str, Any]) -> TurnEvaluation:
    session: InterviewSession = context.service("session")
    answer = str(context.metadata.get("answer") or "")
    # The candidate's answer has just been appended, so ``turns[-1]`` is the answer.
    # The question being evaluated is the most recent *interviewer* turn.
    question = next((turn for turn in reversed(session.turns) if turn.role == "interviewer"), None)
    profile = context.maybe_service("profile")

    raw: ExtractedTurnEvaluation = await context.structured(
        "interview_evaluator",
        ExtractedTurnEvaluation,
        # ``topic`` travels in BOTH places, and that is not redundancy: the prompt variable is what a
        # language model reads, while ``context`` is what a *deterministic* handler reads. Passing it
        # only as a prompt variable made ``handlers_interview._TOPIC_TERMS`` unreachable on the
        # zero-key path — the same answer scored 5/7 through the API and 12/14 in a direct call,
        # because the topic-keyed vocabulary was never applied. Found by PHASE 13's interview page.
        context={"source_text": answer, "topic": question.topic if question else ""},
        question=question.content if question else "",
        level=(
            question.question_level.value if question and question.question_level else "concept"
        ),
        topic=(question.topic if question else ""),
        answer=answer,
        candidate_material=_candidate_material(
            profile if isinstance(profile, CandidateProfile) else None
        ),
        rubric=render_bullets(
            [
                "technical_accuracy：说的是否正确，自信的错误比犹豫的正确更低",
                "depth：是否触及机制、边界与失败模式",
                "communication：结构清晰、具体、无填充",
                "problem_solving：是否有方法（假设 → 证据 → 隔离）",
                "engineering_thinking：是否考虑代价、约束、可维护性与取舍",
            ]
        ),
    )

    def clamp(value: float) -> float:
        return round(max(0.0, min(100.0, float(value))), 2)

    scores = {
        "technical_accuracy": clamp(raw.technical_accuracy),
        "depth": clamp(raw.depth),
        "communication": clamp(raw.communication),
        "problem_solving": clamp(raw.problem_solving),
        "engineering_thinking": clamp(raw.engineering_thinking),
    }
    overall = round(sum(scores.values()) / len(scores), 2)

    return TurnEvaluation(
        turn_index=session.next_turn_index(),
        score=overall,
        technical_accuracy=scores["technical_accuracy"] / 100.0,
        depth=scores["depth"] / 100.0,
        communication=scores["communication"] / 100.0,
        problem_solving=scores["problem_solving"] / 100.0,
        engineering_thinking=scores["engineering_thinking"] / 100.0,
        confidence=clamp(raw.confidence) / 100.0,
        missing_knowledge=list(raw.missing_knowledge)[:5],
        feedback=raw.feedback,
        strong_points=list(raw.strong_points)[:5],
        follow_up_topics=list(raw.follow_up_topics)[:5],
        suggested_answer=raw.suggested_answer,
    )


async def _adapt(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    """Move one rung, and pick the next topic."""
    session: InterviewSession = context.service("session")
    evaluation: TurnEvaluation = inputs["evaluate"]
    change = next_difficulty(session.current_level, evaluation.score)

    # The next topic: prefer something not yet covered, since the turn has moved on. The
    # ``covered`` flags are refreshed from the interviewer turns first, so the pick and the
    # flags cannot disagree about what has been asked.
    mark_plan_coverage(session)
    next_item = next((item for item in session.plan if not item.covered), session.plan[0])

    return {"change": change, "level": change.to_level.level, "next": next_item}
