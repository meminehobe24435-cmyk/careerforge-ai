"""InterviewAgent — adaptive interview simulation (WF-07).

An interview is a loop, not a DAG, so it is three workflows rather than one: start,
turn and finish. They map exactly onto the three API calls the front end makes, and
each keeps its own trace.

Three decisions define the behaviour:

**Questions come from the candidate's own material.** The topic plan is built from
the job's required skills crossed with what the evidence graph does or does not
support, so a question about FreeRTOS is asked because *this* candidate used
FreeRTOS — not because FreeRTOS is on a generic list.

**Difficulty adapts by rule, not by vibes.** A turn score above 75 raises the level,
below 45 lowers it, and the transition is reported with its reason so the UI can
show it. A model asked to "make it harder" produces drift; a rule produces a ladder
that can be tested.

**The scorecard is arithmetic.** The model supplies per-turn sub-scores; the engine
clamps them and aggregates. Six dimensions come from those means, and the seventh —
evidence consistency — is computed deterministically by checking whether the spoken
answers claim things the evidence graph cannot support. That last one is the
capability almost no interview tool has: it cross-checks the resume, the evidence
base and the spoken answer against each other, so the candidate learns about a
credibility risk before a real interviewer finds it.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from careerforge_ai.agents.base import AgentOutcome, merge_workflow_warnings, render_bullets
from careerforge_ai.graph import GraphBuildResult
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.parsing.skill_taxonomy import extract_skill_mentions
from careerforge_ai.schemas.common import (
    DegradationReason,
    DifficultyLevel,
    InterviewMode,
    InterviewStatus,
    RequirementLevel,
)
from careerforge_ai.schemas.interview import (
    DifficultyChange,
    EvidenceConflict,
    ExtractedQuestion,
    ExtractedTurnEvaluation,
    InterviewPlanItem,
    InterviewScorecard,
    InterviewSession,
    InterviewTurn,
    QuestionReview,
    ScorecardDimension,
    TurnEvaluation,
)
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile

__all__ = [
    "INTERVIEW_AGENT",
    "claimed_skills",
    "next_difficulty",
    "InterviewAgent",
    "build_start_workflow",
    "build_turn_workflow",
    "build_finish_workflow",
    "start_interview",
    "submit_answer",
    "finish_interview",
]

INTERVIEW_AGENT = "interview"

#: Interview topic key per canonical skill. Topics without an entry fall back to the
#: generic project question, which is honest: a tailored question needs a tailored
#: bank.
_TOPIC_BY_SKILL: dict[str, str] = {
    "free_rtos": "free_rtos",
    "rtos_scheduler": "rtos_scheduler",
    "stm32": "stm32",
    "spi": "spi",
    "i2c": "i2c",
    "can": "can",
    "uart": "uart",
    "dma": "dma",
    "pid": "pid",
    "motor_control": "pid",
    "performance_tuning": "performance_tuning",
    "embedded_linux": "rtos_scheduler",
}

#: Dimension keys already defined on the scorecard model, in radar order.
_SCORE_DIMENSIONS: tuple[tuple[str, str], ...] = (
    ("technical_accuracy", "技术准确性"),
    ("communication", "表达沟通"),
    ("depth", "技术深度"),
    ("problem_solving", "问题解决"),
    ("engineering_thinking", "工程思维"),
    ("confidence", "自信度"),
    ("evidence_consistency", "证据一致性"),
)

#: Difficulty ladder thresholds. A rule rather than a judgement call, so the
#: adaptivity is testable.
_PROMOTE_AT = 75.0
_DEMOTE_BELOW = 45.0

#: Questions asked before the interview is considered long enough to score.
_MIN_QUESTIONS_FOR_SCORECARD = 3

#: Turns kept in the prompt context. Enough for continuity, not enough to grow the
#: request without bound.
_RECENT_TURNS = 6


def _plan_topics(job: JDAnalysis | None, graph: GraphBuildResult | None) -> list[InterviewPlanItem]:
    """Order the interview topics by what the job wants and the evidence shows."""
    if job is None:
        return [
            InterviewPlanItem(
                topic="project",
                label="项目深挖",
                target_level=DifficultyLevel.ENGINEERING,
                reason="未提供岗位，按项目经历提问",
                source="resume",
            )
        ]

    planned: list[InterviewPlanItem] = []
    seen: set[str] = set()

    for jd_skill in job.all_skills:
        canonical = jd_skill.canonical_id
        if not canonical or canonical in seen:
            continue
        topic = _TOPIC_BY_SKILL.get(canonical)
        if topic is None:
            continue
        seen.add(canonical)

        has_evidence = bool(graph and graph.skill_evidence.get(canonical))
        confidence = graph.skill_confidence.get(canonical, 0.0) if graph else 0.0

        if has_evidence:
            reason = f"岗位要求 {jd_skill.raw_text}，且你有 {len(graph.skill_evidence[canonical])} 条证据"
            source = "evidence"
        elif jd_skill.requirement is RequirementLevel.REQUIRED:
            reason = f"岗位必备 {jd_skill.raw_text}，但证据图谱中没有支撑，面试中很可能被追问"
            source = "gap"
        else:
            reason = f"岗位提到 {jd_skill.raw_text}"
            source = "jd_requirement"

        planned.append(
            InterviewPlanItem(
                topic=topic,
                label=jd_skill.raw_text,
                target_level=(
                    DifficultyLevel.ENGINEERING
                    if has_evidence and confidence >= 0.75
                    else DifficultyLevel.CONCEPT
                ),
                reason=reason,
                source=source,
                source_ids=list(graph.skill_evidence.get(canonical, [])) if graph else [],
            )
        )

    if not planned:
        planned.append(
            InterviewPlanItem(
                topic="_default",
                label="项目与经历",
                target_level=DifficultyLevel.CONCEPT,
                reason="岗位技能无法映射到面试题库，改问项目经历",
                source="resume",
            )
        )
    return planned


def _candidate_material(profile: CandidateProfile | None) -> str:
    if profile is None:
        return "（未提供候选人材料）"
    lines: list[str] = []
    for project in profile.projects:
        lines.append(f"项目：{project.name} — {project.summary or project.description}")
        if project.tech_stack:
            lines.append(f"  技术栈：{'、'.join(project.tech_stack)}")
    for experience in profile.experiences:
        lines.append(f"经历：{experience.company} · {experience.title} — {experience.description}")
    if profile.skills:
        lines.append("技能：" + "、".join(item.skill.display_name for item in profile.skills))
    return "\n".join(lines) or "（未提供候选人材料）"


def _recent_turns(session: InterviewSession) -> str:
    turns = session.turns[-_RECENT_TURNS:]
    if not turns:
        return "（面试刚开始）"
    return render_bullets([f"{turn.role}: {turn.content[:200]}" for turn in turns])


def _covered_topics(session: InterviewSession) -> str:
    topics = [turn.topic for turn in session.turns if turn.topic]
    return "、".join(dict.fromkeys(topics)) or "（无）"


def _pick_topic(session: InterviewSession) -> InterviewPlanItem:
    """The first planned topic not yet covered, else the first."""
    covered = {turn.topic for turn in session.turns if turn.role == "interviewer"}
    for item in session.plan:
        if item.topic not in covered:
            return item
    return session.plan[0]


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


def build_finish_workflow() -> Workflow:
    """WF-07c: aggregate the scorecard."""
    return Workflow(
        name="interview_finish",
        agent=INTERVIEW_AGENT,
        trigger="api",
        description="Aggregate per-turn evaluations into the seven-dimension scorecard",
        steps=(
            Step(
                name="aggregate",
                fn=_aggregate,
                agent=INTERVIEW_AGENT,
                description="Dimension means",
            ),
            Step(
                name="consistency",
                fn=_consistency,
                depends_on=("aggregate",),
                agent=INTERVIEW_AGENT,
                description="Cross-check the answers against the evidence graph",
            ),
            Step(
                name="scorecard",
                fn=_scorecard,
                depends_on=("aggregate", "consistency"),
                agent=INTERVIEW_AGENT,
                description="Assemble the report",
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
            )
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
        tokens=0,
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
        context={"source_text": answer},
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


def next_difficulty(current: DifficultyLevel, score: float) -> DifficultyChange:
    """One rung up or down, by rule.

    A pure function on purpose: the adaptivity is the part of an interview simulator
    most likely to be hand-waved, and a rule that can be called directly is a rule
    that can be tested at its boundaries. A model asked to "make it harder" produces
    drift instead.
    """
    if score >= _PROMOTE_AT and current.level < DifficultyLevel.DEBUGGING.level:
        target = DifficultyLevel.from_level(current.level + 1)
        reason = f"回答得分 {score:.0f}，高于 {_PROMOTE_AT:.0f}，进入更深一层追问"
    elif score <= _DEMOTE_BELOW and current.level > DifficultyLevel.CONCEPT.level:
        target = DifficultyLevel.from_level(current.level - 1)
        reason = f"回答得分 {score:.0f}，低于 {_DEMOTE_BELOW:.0f}，退回上一层确认基础"
    else:
        target = current
        reason = f"回答得分 {score:.0f}，保持当前难度"
    return DifficultyChange(from_level=current, to_level=target, reason=reason)


async def _adapt(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    """Move one rung, and pick the next topic."""
    session: InterviewSession = context.service("session")
    evaluation: TurnEvaluation = inputs["evaluate"]
    change = next_difficulty(session.current_level, evaluation.score)

    # The next topic: prefer something not yet covered, since the turn has moved on.
    covered = {turn.topic for turn in session.turns if turn.role == "interviewer"}
    next_item = next((item for item in session.plan if item.topic not in covered), session.plan[0])

    return {"change": change, "level": change.to_level.level, "next": next_item}


# ── finish ───────────────────────────────────────────────────────────────────


async def _aggregate(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    session: InterviewSession = context.service("session")
    evaluations = [turn.evaluation for turn in session.turns if turn.evaluation is not None]
    if not evaluations:
        context.metadata.setdefault("warnings", []).append("面试没有可评分的回答，报告将不完整")

    def mean(attribute: str) -> float:
        values = [float(getattr(item, attribute)) for item in evaluations]
        return round(sum(values) / len(values) * 100, 1) if values else 0.0

    dimensions = [
        ScorecardDimension(
            key="technical_accuracy", label="技术准确性", score=mean("technical_accuracy")
        ),
        ScorecardDimension(key="communication", label="表达沟通", score=mean("communication")),
        ScorecardDimension(key="depth", label="技术深度", score=mean("depth")),
        ScorecardDimension(key="problem_solving", label="问题解决", score=mean("problem_solving")),
        ScorecardDimension(
            key="engineering_thinking", label="工程思维", score=mean("engineering_thinking")
        ),
        ScorecardDimension(key="confidence", label="自信度", score=mean("confidence")),
    ]
    return {"dimensions": dimensions, "evaluations": evaluations}


#: Clause markers that turn a mention into a personal claim. A candidate explaining
#: *why* a queue beats a global variable is reasoning; a candidate saying "我用 X 做了
#: Y" is making a claim the interviewer will test.
_CLAIM_MARKERS: tuple[str, ...] = (
    "我用",
    "我在",
    "我们使用",
    "我使用",
    "做了",
    "用过",
    "我做过",
    "我实现",
    "我负责",
    "我开发",
    "我搭建",
    "我写",
    "我参与",
    "我完成",
    "i used",
    "i built",
    "i implemented",
    "i developed",
    "i wrote",
)

#: Clause separators used to scope a claim marker to nearby text.
_CLAUSE_SPLIT: re.Pattern[str] = re.compile(r"[，,。；;！？!?\n]")


def claimed_skills(answer: str) -> set[str]:
    """Skills mentioned in a clause that also carries a first-person claim marker."""
    claimed: set[str] = set()
    for clause in _CLAUSE_SPLIT.split(answer):
        lowered = clause.lower()
        if not any(marker in lowered for marker in _CLAIM_MARKERS):
            continue
        claimed |= {skill.canonical_id for skill, _, _ in extract_skill_mentions(clause)}
    return claimed


async def _consistency(context: RunContext, inputs: dict[str, Any]) -> list[EvidenceConflict]:
    """Cross-check *claimed* skills in the spoken answers against the graph.

    Deterministic on purpose. A model asked "did this answer contradict the resume?"
    will produce plausible-sounding conflicts; a set comparison produces real ones.

    Known limitation, stated rather than hidden: the claim marker is detected
    lexically, so a candidate who discusses a technology inside a first-person
    sentence is still flagged. That is the deliberate direction of the error — the
    advice tells them to have evidence ready for something they are likely to be
    asked about.
    """
    session: InterviewSession = context.service("session")
    graph = context.maybe_service("graph")
    profile = context.maybe_service("profile")

    evidenced: set[str] = set()
    if isinstance(graph, GraphBuildResult):
        evidenced = {skill for skill, ids in graph.skill_evidence.items() if ids}
    declared: set[str] = set()
    if isinstance(profile, CandidateProfile):
        declared = {item.skill.canonical_id for item in profile.skills}

    conflicts: list[EvidenceConflict] = []
    for turn in session.turns:
        if turn.role != "candidate" or not turn.content.strip():
            continue
        # A skill the resume already lists but cannot prove is a *gap*, not a spoken
        # contradiction. Only skills new to the conversation are flagged here.
        unsupported = sorted(claimed_skills(turn.content) - evidenced - declared)
        if not unsupported:
            continue
        conflicts.append(
            EvidenceConflict(
                statement=turn.content[:200],
                evidence_state=(
                    "你在回答中提到了这些技术，但证据图谱中没有支撑材料："
                    + "、".join(unsupported[:5])
                ),
                severity="high" if len(unsupported) > 2 else "medium",
                advice="面试前补齐相关代码或文档，或调整表述范围，避免追问时无法举证",
            )
        )
    return conflicts[:6]


async def _scorecard(context: RunContext, inputs: dict[str, Any]) -> InterviewScorecard:
    session: InterviewSession = context.service("session")
    aggregated = inputs["aggregate"]
    conflicts: list[EvidenceConflict] = inputs["consistency"]

    dimensions: list[ScorecardDimension] = list(aggregated["dimensions"])
    consistency_score = 100.0 if not conflicts else max(30.0, 100.0 - 18.0 * len(conflicts))
    dimensions.append(
        ScorecardDimension(
            key="evidence_consistency",
            label="证据一致性",
            score=round(consistency_score, 1),
            comment=(
                "口述内容与证据图谱一致"
                if not conflicts
                else f"{len(conflicts)} 处内容缺少证据支撑"
            ),
        )
    )

    evaluations: list[TurnEvaluation] = aggregated["evaluations"]
    overall = (
        round(sum(dimension.score for dimension in dimensions) / len(dimensions), 1)
        if dimensions
        else 0.0
    )

    per_question: list[QuestionReview] = []
    for index, turn in enumerate(session.turns):
        if turn.role != "interviewer":
            continue
        evaluation = turn.evaluation
        if evaluation is None and index + 1 < len(session.turns):
            evaluation = session.turns[index + 1].evaluation
        verdict = "mixed"
        if evaluation is not None:
            verdict = (
                "strong"
                if evaluation.score >= _PROMOTE_AT
                else "weak"
                if evaluation.score <= _DEMOTE_BELOW
                else "mixed"
            )
        answer = next(
            (later.content for later in session.turns[index + 1 :] if later.role == "candidate"),
            "",
        )
        per_question.append(
            QuestionReview(
                turn_index=turn.turn_index,
                topic=turn.topic or "",
                level=turn.question_level,
                verdict=verdict,
                question=turn.content,
                answer=answer[:600],
                suggested_answer=evaluation.suggested_answer if evaluation else "",
                missing_knowledge=list(evaluation.missing_knowledge) if evaluation else [],
                follow_up_topics=list(evaluation.follow_up_topics) if evaluation else [],
            )
        )

    missing = list(
        dict.fromkeys(item for review in per_question for item in review.missing_knowledge)
    )
    follow_ups = list(
        dict.fromkeys(item for review in per_question for item in review.follow_up_topics)
    )
    strengths = list(
        dict.fromkeys(item for evaluation in evaluations for item in evaluation.strong_points)
    )
    weaknesses = [item.feedback for item in evaluations if item.score <= _DEMOTE_BELOW][:5]

    if len(evaluations) < _MIN_QUESTIONS_FOR_SCORECARD:
        context.metadata.setdefault("warnings", []).append(
            f"仅完成 {len(evaluations)} 题，样本偏少，评分仅供参考"
        )

    context.metadata["output_ref"] = {
        "questions": len(per_question),
        "overall": overall,
        "conflicts": len(conflicts),
    }

    return InterviewScorecard(
        interview_id=session.id,
        mode=session.mode,
        overall_score=overall,
        dimensions=dimensions,
        strengths=strengths[:5],
        weaknesses=weaknesses,
        missing_knowledge=missing[:8],
        follow_up_topics=follow_ups[:8],
        evidence_conflicts=conflicts,
        per_question=per_question,
        difficulty_start=session.plan[0].target_level if session.plan else DifficultyLevel.CONCEPT,
        difficulty_end=session.current_level,
        duration_seconds=0,
    )


# ── agent ────────────────────────────────────────────────────────────────────


class InterviewAgent:
    """Runs an interview across three workflows. The session is passed in and out."""

    name = INTERVIEW_AGENT

    def workflow(self) -> Workflow:
        return build_start_workflow()

    async def start(
        self,
        executor: WorkflowExecutor,
        *,
        mode: InterviewMode = InterviewMode.TECHNICAL,
        job: JDAnalysis | None = None,
        job_id: UUID | None = None,
        profile: CandidateProfile | None = None,
        graph: GraphBuildResult | None = None,
        difficulty: int = 1,
    ) -> AgentOutcome:
        # ``JDAnalysis`` is the parsed description, not the stored job record, so the
        # record id is passed separately rather than read off the analysis.
        session = InterviewSession(
            mode=mode,
            status=InterviewStatus.IN_PROGRESS,
            job_id=job_id,
            current_level=DifficultyLevel.from_level(difficulty),
        )
        services: dict[str, Any] = {"session": session}
        if job is not None:
            services["job"] = job
        if profile is not None:
            services["profile"] = profile
        if graph is not None:
            services["graph"] = graph

        output = await executor.run(build_start_workflow(), trigger="api", services=services)
        plan: list[InterviewPlanItem] = output.get("plan") or []
        first: InterviewTurn | None = output.get("question")

        session.plan = plan
        if first is not None:
            session.turns.append(first)
            session.current_level = first.question_level or session.current_level

        return AgentOutcome(
            value=session,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=output.degradation_reason,
            warnings=merge_workflow_warnings(output)
            + [str(item) for item in output.metadata.get("warnings", [])],
        )

    async def answer(
        self,
        executor: WorkflowExecutor,
        *,
        session: InterviewSession,
        answer: str,
        job: JDAnalysis | None = None,
        profile: CandidateProfile | None = None,
        graph: GraphBuildResult | None = None,
    ) -> AgentOutcome:
        last_question = next(
            (turn for turn in reversed(session.turns) if turn.role == "interviewer"), None
        )
        session.turns.append(
            InterviewTurn(
                turn_index=session.next_turn_index(),
                role="candidate",
                content=answer,
                topic=last_question.topic if last_question else None,
            )
        )
        services: dict[str, Any] = {"session": session}
        if job is not None:
            services["job"] = job
        if profile is not None:
            services["profile"] = profile
        if graph is not None:
            services["graph"] = graph

        output = await executor.run(
            build_turn_workflow(),
            trigger="api",
            services=services,
            metadata={"answer": answer},
        )
        evaluation: TurnEvaluation | None = output.get("evaluate")
        adaptation = output.get("adapt") or {}
        next_turn: InterviewTurn | None = output.get("question")

        if evaluation is not None:
            session.turns[-1] = session.turns[-1].model_copy(update={"evaluation": evaluation})
        change = adaptation.get("change")
        if isinstance(change, DifficultyChange):
            session.current_level = change.to_level
        if next_turn is not None:
            session.turns.append(next_turn)

        return AgentOutcome(
            value=session,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=output.degradation_reason,
            warnings=merge_workflow_warnings(output)
            + [str(item) for item in output.metadata.get("warnings", [])],
            extras={
                "evaluation": evaluation,
                "difficultyChange": change,
                "nextQuestion": next_turn,
            },
        )

    async def finish(
        self,
        executor: WorkflowExecutor,
        *,
        session: InterviewSession,
        profile: CandidateProfile | None = None,
        graph: GraphBuildResult | None = None,
    ) -> AgentOutcome:
        services: dict[str, Any] = {"session": session}
        if profile is not None:
            services["profile"] = profile
        if graph is not None:
            services["graph"] = graph

        output = await executor.run(build_finish_workflow(), trigger="api", services=services)
        scorecard: InterviewScorecard | None = output.get("scorecard")
        if scorecard is not None:
            session.scorecard = scorecard
            session.status = InterviewStatus.COMPLETED

        return AgentOutcome(
            value=scorecard,
            record=output.record,
            degraded=output.degraded
            or (
                scorecard is not None and len(scorecard.per_question) < _MIN_QUESTIONS_FOR_SCORECARD
            ),
            degradation_reason=(
                output.degradation_reason if output.degraded else DegradationReason.NONE
            ),
            warnings=merge_workflow_warnings(output)
            + [str(item) for item in output.metadata.get("warnings", [])],
        )


async def start_interview(
    executor: WorkflowExecutor, **kwargs: Any
) -> tuple[InterviewSession | None, AgentOutcome]:
    outcome = await InterviewAgent().start(executor, **kwargs)
    return outcome.value, outcome


async def submit_answer(
    executor: WorkflowExecutor, **kwargs: Any
) -> tuple[InterviewSession | None, AgentOutcome]:
    outcome = await InterviewAgent().answer(executor, **kwargs)
    return outcome.value, outcome


async def finish_interview(
    executor: WorkflowExecutor, **kwargs: Any
) -> tuple[InterviewScorecard | None, AgentOutcome]:
    outcome = await InterviewAgent().finish(executor, **kwargs)
    return outcome.value, outcome
