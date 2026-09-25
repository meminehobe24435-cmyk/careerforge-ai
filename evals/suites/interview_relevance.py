"""Suite: interview question relevance.

Interview questions are the easiest place in this product to be plausibly wrong: a question about
React Hooks in an embedded interview *reads* fine, and a model asked to grade its own questions
will say they are excellent. So this suite is **deterministic end to end**. It runs the real
planner, the real question generator and the real session state machine with whatever provider is
configured, then measures properties of the questions that arithmetic can check:

* **required-skill coverage** — of the JD's required skills, how many become the subject of a
  planned topic? A requirement the interviewer never asks about is one the candidate never gets
  to demonstrate.
* **forbidden-topic leakage** — each scenario declares topics that would be off-topic for the role
  (React for embedded, MCU/ADC for backend). This is the "does it stay in its lane" check, and it
  is the metric that catches a topic map which quietly degenerates to a generic catch-all.
* **duplicate rate** — pairwise Jaccard at or above 0.8 across the questions actually asked.
  Repeating a question burns the candidate's time and says the plan is not tracking coverage.
* **difficulty match** — the planned level against the requested level, within one rung (the
  adapter is allowed to move on its own; a jump of two is a bug).
* **evidence awareness** — the split between topics planned *because* evidence exists and topics
  planned *because* it is missing. Both are wanted; a planner that only does one of them is
  either flattering the candidate or interrogating them.

An LLM judge would be needed to answer "is this a *good* question", and it is deliberately absent
from this suite: it is optional, off by default, never a gate, and lives in ``evals/judge.py``
where it must declare its model and prompt version. The numbers above cannot be argued out of a
verdict by a second model.
"""

from __future__ import annotations

import time
from typing import Any

from careerforge_ai.agents.interview import InterviewAgent
from careerforge_ai.graph import GraphBuildResult, build_evidence_graph
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.parsing.tokenize import tokens
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.base import LLMProvider
from careerforge_ai.schemas.common import (
    DifficultyLevel,
    EvidenceKind,
    EvidenceStrength,
    InterviewMode,
    RequirementLevel,
    SkillCategory,
    SkillLevel,
    SourceAuthority,
    utcnow,
)
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator
from careerforge_ai.schemas.interview import InterviewSession
from careerforge_ai.schemas.job import JDAnalysis, JDSkill
from careerforge_ai.schemas.profile import CandidateProfile, ProfileSkill, Project, SkillRef
from evals.metrics import rate
from evals.report import SuiteOutcome

__all__ = ["SUITE_NAME", "suite_interview_relevance"]

SUITE_NAME = "interview_relevance"

#: Jaccard similarity at or above which two questions count as the same question. 0.8 is high on
#: purpose: paraphrases of one question should count as duplicates, while two questions merely
#: sharing a topic word should not.
_DUPLICATE_THRESHOLD = 0.8

#: Interview turns per scenario. Three questions is the minimum the scorecard accepts, and enough
#: to see whether the plan moves past its first topic.
_TURNS = 3

#: How far the planned level may sit from the requested one and still count as a match. The
#: difficulty ladder is allowed to move by itself; it is not allowed to jump.
_LEVEL_TOLERANCE = 1

_ANSWERS = (
    "我在项目里按优先级划分任务，用队列在任务与中断之间传递数据，并用信号量保护共享资源。",
    "遇到过优先级反转，用互斥量的优先级继承缓解；时序问题一般先用逻辑分析仪确认波形。",
    "我会先复现问题，再看调度器状态与栈使用情况，最后用 trace 确认是哪一步引入了延迟。",
)


def jaccard(left: str, right: str) -> float:
    """Symmetric token overlap — the duplicate detector, not the product's `token_overlap`.

    `token_overlap` is asymmetric and coverage-weighted (0.7 coverage + 0.3 Jaccard) because the
    claim gate needs "does the evidence cover the claim". Duplicate detection needs the symmetric
    question instead: two questions that share every token are the same question regardless of
    which one is longer.
    """
    left_tokens = set(tokens(left))
    right_tokens = set(tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def build_scenario_inputs(
    scenario: dict[str, Any],
) -> tuple[JDAnalysis, CandidateProfile, GraphBuildResult]:
    """Turn a scenario fixture into the three real inputs the interview agent takes."""
    skills = [
        JDSkill(
            canonical_id=item["canonical"],
            raw_text=item["raw"],
            requirement=RequirementLevel(item["requirement"]),
            jd_evidence=item["raw"],
        )
        for item in scenario["jd_skills"]
    ]
    job = JDAnalysis(
        role=scenario["role"],
        required_skills=[s for s in skills if s.requirement is RequirementLevel.REQUIRED],
        preferred_skills=[s for s in skills if s.requirement is RequirementLevel.PREFERRED],
        parse_confidence=0.9,
    )

    profile_skills = [
        ProfileSkill(
            skill=SkillRef(
                canonical_id=item["canonical"],
                display_name=item["display"],
                category=SkillCategory(item.get("category", "language")),
            ),
            level=SkillLevel.STRONG if item["evidenced"] else SkillLevel.BASIC,
            evidence_count=2 if item["evidenced"] else 0,
            evidence_score=0.8 if item["evidenced"] else 0.0,
        )
        for item in scenario["profile_skills"]
    ]
    profile = CandidateProfile(
        slug="eval-candidate",
        headline=scenario["role"],
        summary=scenario["candidate_summary"],
        projects=[
            Project(
                name=scenario["project_name"],
                summary=scenario["project_summary"],
                tech_stack=list(scenario["project_stack"]),
                evidence_strength=EvidenceStrength.HIGH,
            )
        ],
        skills=profile_skills,
    )

    evidence: list[EvidenceItem] = []
    for index, item in enumerate(scenario["profile_skills"]):
        if not item["evidenced"]:
            # No evidence at all for this skill: this is the gap the interview should probe.
            continue
        evidence.append(
            EvidenceItem(
                kind=EvidenceKind.REPO_FILE,
                title=f"{item['canonical']}_{index}.c",
                snippet=f"{item['display']} 相关实现：任务创建、优先级划分、队列通信与中断处理。",
                locator=EvidenceLocator(path=f"{item['canonical']}_{index}.c", section="main"),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                # Required by the schema, overwritten by the graph builder — the builder is the only
                # thing allowed to decide a confidence, so no number is invented here.
                confidence=0.0,
                occurred_at=utcnow(),
            )
        )
    graph = build_evidence_graph(profile=profile, evidence=evidence, job=job)
    return job, profile, graph


async def suite_interview_relevance(
    provider: LLMProvider, rows: list[dict[str, Any]]
) -> SuiteOutcome:
    started = time.perf_counter()
    result = SuiteOutcome(
        name=SUITE_NAME,
        dataset="interview_relevance",
        dataset_version=str(rows[0].get("fixture_version", "v1")) if rows else "v1",
        cases=len(rows),
    )

    executor = WorkflowExecutor(
        provider=provider,
        prompts=load_prompt_registry(),
        settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
    )
    agent = InterviewAgent()

    covered_total = required_total = 0
    forbidden_hits = forbidden_scenarios = 0
    duplicate_pairs = question_pairs = 0
    difficulty_matches = difficulty_total = 0
    evidence_backed = planned_total = gap_probes = 0
    question_counts_ok = 0
    asked_total = 0
    by_scenario: dict[str, dict[str, float]] = {}

    for row in rows:
        scenario = row["scenario"]
        requested_level = DifficultyLevel.from_level(int(scenario.get("difficulty", 2)))
        job, profile, graph = build_scenario_inputs(scenario)

        outcome = await agent.start(
            executor,
            mode=InterviewMode.TECHNICAL,
            job=job,
            profile=profile,
            graph=graph,
            difficulty=requested_level.level,
        )
        session: InterviewSession | None = outcome.value
        if session is None:
            result.failures.append({"kind": "session_not_started", "scenario": scenario["id"]})
            continue

        for turn_index in range(_TURNS - 1):
            answered = await agent.answer(
                executor,
                session=session,
                answer=_ANSWERS[turn_index % len(_ANSWERS)],
                job=job,
                profile=profile,
                graph=graph,
            )
            if answered.value is not None:
                session = answered.value

        plan = session.plan
        questions = [turn.content for turn in session.turns if turn.role == "interviewer"]
        asked_total += len(questions)
        question_text = " ".join(questions).lower()

        required = {
            skill.canonical_id for skill in job.required_skills if skill.canonical_id is not None
        }
        planned_terms = {
            term
            for item in plan
            for term in (item.topic, item.label, (item.topic or "").replace("_", " "))
        }
        covered = {
            skill
            for skill in required
            if skill in planned_terms or skill.replace("_", " ") in question_text
        }
        required_total += len(required)
        covered_total += len(covered)

        forbidden = [term.lower() for term in scenario.get("forbidden_topics", [])]
        if forbidden:
            forbidden_scenarios += 1
            leaked = [term for term in forbidden if term in question_text]
            if leaked:
                forbidden_hits += 1
                result.failures.append(
                    {
                        "kind": "forbidden_topic_leak",
                        "scenario": scenario["id"],
                        "leaked": leaked,
                        "questions": questions[:3],
                    }
                )

        for index, left in enumerate(questions):
            for right in questions[index + 1 :]:
                question_pairs += 1
                if jaccard(left, right) >= _DUPLICATE_THRESHOLD:
                    duplicate_pairs += 1

        for item in plan:
            difficulty_total += 1
            if abs(item.target_level.level - requested_level.level) <= _LEVEL_TOLERANCE:
                difficulty_matches += 1

            planned_total += 1
            if item.source == "evidence":
                evidence_backed += 1
            elif item.source == "gap":
                gap_probes += 1

        if len(questions) >= 2:
            question_counts_ok += 1

        by_scenario[scenario["id"]] = {
            "required_skills": float(len(required)),
            "covered": float(len(covered)),
            "plan_items": float(len(plan)),
            "evidence_backed_items": float(sum(1 for item in plan if item.source == "evidence")),
            "gap_probes": float(sum(1 for item in plan if item.source == "gap")),
            "questions": float(len(questions)),
        }

    result.metrics = {
        "interview.required_skill_coverage": rate(covered_total, required_total),
        "interview.forbidden_leakage_rate": rate(forbidden_hits, forbidden_scenarios),
        "interview.duplicate_rate": rate(duplicate_pairs, question_pairs),
        "interview.difficulty_match_rate": rate(difficulty_matches, difficulty_total),
        "interview.evidence_awareness_rate": rate(evidence_backed, planned_total),
        "interview.question_count_ok_rate": rate(question_counts_ok, len(rows)),
    }
    result.counters = {
        "scenarios": len(rows),
        "required_skills": required_total,
        "covered_skills": covered_total,
        "questions_asked": asked_total,
        "question_pairs": question_pairs,
        "duplicate_pairs": duplicate_pairs,
        "plan_items": planned_total,
        "evidence_backed_items": evidence_backed,
        "gap_probes": gap_probes,
        "difficulty_items": difficulty_total,
        "difficulty_matches": difficulty_matches,
    }
    result.breakdown = {"by_scenario": by_scenario}
    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result
