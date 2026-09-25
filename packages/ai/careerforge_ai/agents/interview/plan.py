"""Interview planning: topic selection, material rendering and the difficulty ladder."""

from __future__ import annotations

from careerforge_ai.agents.base import render_bullets
from careerforge_ai.graph import GraphBuildResult
from careerforge_ai.schemas.common import (
    DifficultyLevel,
    RequirementLevel,
)
from careerforge_ai.schemas.interview import (
    DifficultyChange,
    InterviewPlanItem,
    InterviewSession,
)
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile

INTERVIEW_AGENT = "interview"

#: Difficulty ladder thresholds. A rule rather than a judgement call, so the
#: adaptivity is testable.
_PROMOTE_AT = 75.0

_DEMOTE_BELOW = 45.0

#: Turns kept in the prompt context. Enough for continuity, not enough to grow the
#: request without bound.
_RECENT_TURNS = 6


#: Interview topic key per canonical skill. Topics without an entry fall back to the
#: generic project question, which is honest: a tailored question needs a tailored
#: bank.
#:
#: Coverage matters more than it looks. The PHASE 12 evaluation (``evals/suites/interview_relevance.py``)
#: measured *required-skill coverage* — the share of a posting's must-have skills that become the
#: subject of a planned topic — and found **0.33**: this map held embedded skills only, so a backend
#: or AI-application interview fell through to the single generic project topic and asked the
#: candidate nothing about FastAPI, PostgreSQL or RAG. The zero-key path is a first-class deployment
#: (ADR-009), so a coverage hole here is a hole in the product, not in the provider.
_TOPIC_BY_SKILL: dict[str, str] = {
    # embedded
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
    # backend and data
    "python": "python",
    "fastapi": "fastapi",
    "django": "python",
    "flask": "python",
    "postgresql": "sql_database",
    "sql": "sql_database",
    "mysql": "sql_database",
    "redis": "redis",
    "kafka": "messaging",
    "rabbitmq": "messaging",
    # AI application
    "rag": "rag",
    "llm": "llm",
    "vector_db": "vector_search",
    "prompt_engineering": "llm",
    "pytorch": "ml_training",
    "tensorflow": "ml_training",
    # frontend
    "react": "frontend_react",
    "typescript": "frontend_react",
    "javascript": "frontend_react",
    # platform and quality
    "docker": "docker",
    "kubernetes": "kubernetes",
    "ci_cd": "ci_cd",
    "testing": "testing",
    "pytest": "testing",
}


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

        # One lookup, used for both the flag and the count: reading the mapping twice
        # invited the two to disagree, and the second read was the one the checker
        # could not prove safe.
        evidence_items = graph.skill_evidence.get(canonical, []) if graph else []
        has_evidence = bool(evidence_items)
        confidence = graph.skill_confidence.get(canonical, 0.0) if graph else 0.0

        if has_evidence:
            reason = f"岗位要求 {jd_skill.raw_text}，且你有 {len(evidence_items)} 条证据"
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


def _asked_topics(session: InterviewSession) -> set[str | None]:
    """The topics the interviewer has actually asked about.

    One definition, read by both the next-topic picker and the plan's ``covered`` flag: two
    copies of "what has been asked" would eventually disagree, and the flag would then say a
    topic had been covered while the picker still chose it.
    """
    return {turn.topic for turn in session.turns if turn.role == "interviewer"}


def mark_plan_coverage(session: InterviewSession) -> None:
    """Write ``covered`` on every plan item from the interviewer turns actually asked.

    The flag is *derived*, never declared by the planner: a plan item marked covered by
    construction would claim a question had been asked when none had. Called by
    :class:`~careerforge_ai.agents.interview.agent.InterviewAgent` after every turn it appends,
    so it is current whenever a session is serialised.
    """
    asked = _asked_topics(session)
    for item in session.plan:
        item.covered = item.topic in asked


def _pick_topic(session: InterviewSession) -> InterviewPlanItem:
    """The first planned topic not yet covered, else the first."""
    covered = _asked_topics(session)
    for item in session.plan:
        if item.topic not in covered:
            return item
    return session.plan[0]


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
