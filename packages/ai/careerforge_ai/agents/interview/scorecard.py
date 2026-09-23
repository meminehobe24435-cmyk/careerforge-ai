"""Scorecard aggregation and the evidence-consistency check."""

from __future__ import annotations

import re
from typing import Any

from careerforge_ai.agents.interview.plan import (
    _DEMOTE_BELOW,
    _PROMOTE_AT,
    INTERVIEW_AGENT,
)
from careerforge_ai.graph import GraphBuildResult
from careerforge_ai.orchestrator import RunContext, Step, Workflow
from careerforge_ai.parsing.skill_taxonomy import extract_skill_mentions
from careerforge_ai.schemas.common import (
    DifficultyLevel,
)
from careerforge_ai.schemas.interview import (
    EvidenceConflict,
    InterviewScorecard,
    InterviewSession,
    QuestionReview,
    ScorecardDimension,
    TurnEvaluation,
)
from careerforge_ai.schemas.profile import CandidateProfile

#: Questions asked before the interview is considered long enough to score.
_MIN_QUESTIONS_FOR_SCORECARD = 3

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


def claimed_skills(answer: str) -> set[str]:
    """Skills mentioned in a clause that also carries a first-person claim marker."""
    claimed: set[str] = set()
    for clause in _CLAUSE_SPLIT.split(answer):
        lowered = clause.lower()
        if not any(marker in lowered for marker in _CLAIM_MARKERS):
            continue
        claimed |= {skill.canonical_id for skill, _, _ in extract_skill_mentions(clause)}
    return claimed
