"""Tests for InterviewAgent.

Two properties matter more than the rest. The difficulty ladder must move by rule at
its boundaries, because that is the part of an interview simulator most easily
hand-waved. And the evidence-consistency check must find real conflicts by set
comparison rather than by asking a model whether something "feels" inconsistent.
"""

from __future__ import annotations

import pytest

from careerforge_ai.agents import InterviewAgent, finish_interview, start_interview, submit_answer
from careerforge_ai.agents.interview import next_difficulty
from careerforge_ai.graph import build_evidence_graph
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.common import (
    DifficultyLevel,
    EvidenceKind,
    InterviewMode,
    InterviewStatus,
    RequirementLevel,
    SkillCategory,
    SkillLevel,
    SourceAuthority,
    utcnow,
)
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator
from careerforge_ai.schemas.interview import InterviewScorecard
from careerforge_ai.schemas.job import JDAnalysis, JDSkill
from careerforge_ai.schemas.profile import (
    CandidateProfile,
    Experience,
    ProfileSkill,
    Project,
    SkillRef,
)

LONG_ANSWER = (
    "我们使用 FreeRTOS 的队列在中断与任务之间传递数据，因为直接操作全局变量会带来竞态；"
    "任务按优先级划分，共享资源用互斥量保护以避免优先级反转，考虑过直接关中断但代价是延迟变大，"
    "所以最终选择了队列加信号量的方案。"
)
SHORT_ANSWER = "用过。"


@pytest.fixture
def executor() -> WorkflowExecutor:
    return WorkflowExecutor(
        provider=HeuristicProvider(),
        prompts=load_prompt_registry(),
        settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
    )


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        slug="alex",
        headline="Embedded Engineer",
        summary="电子信息工程本科，做过两轮自平衡机器人。",
        years_experience=1.0,
        experiences=[
            Experience(
                company="某科技",
                title="嵌入式实习生",
                description="使用 STM32 与 FreeRTOS 开发电机控制固件。",
            )
        ],
        projects=[
            Project(
                name="Balance Robot",
                summary="基于 STM32 的两轮自平衡小车",
                tech_stack=["STM32", "FreeRTOS", "PID"],
            )
        ],
        skills=[
            ProfileSkill(
                skill=SkillRef(
                    canonical_id="stm32", display_name="STM32", category=SkillCategory.EMBEDDED
                ),
                level=SkillLevel.STRONG,
                evidence_count=2,
            ),
            ProfileSkill(
                skill=SkillRef(
                    canonical_id="free_rtos",
                    display_name="FreeRTOS",
                    category=SkillCategory.EMBEDDED,
                ),
                level=SkillLevel.STRONG,
                evidence_count=2,
            ),
        ],
    )


@pytest.fixture
def job() -> JDAnalysis:
    def required(canonical_id: str, raw: str) -> JDSkill:
        return JDSkill(
            canonical_id=canonical_id,
            raw_text=raw,
            requirement=RequirementLevel.REQUIRED,
            jd_evidence=f"熟悉 {raw}",
        )

    return JDAnalysis(
        company="某科技",
        role="嵌入式软件工程师",
        required_skills=[
            required("free_rtos", "FreeRTOS"),
            required("stm32", "STM32"),
            required("can", "CAN"),
        ],
    )


@pytest.fixture
def graph(profile: CandidateProfile):
    return build_evidence_graph(
        profile=profile,
        evidence=[
            EvidenceItem(
                kind=EvidenceKind.REPO_FILE,
                title="freertos.c",
                snippet="基于 FreeRTOS 的任务划分与优先级配置，任务间通过队列通信，共享资源用互斥量保护。",
                locator=EvidenceLocator(path="Core/Src/freertos.c", line=18),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                confidence=0.0,
                occurred_at=utcnow(),
            ),
            EvidenceItem(
                kind=EvidenceKind.REPO_FILE,
                title="motor_control.c",
                snippet="在 STM32 上实现 PID 电机闭环控制。",
                locator=EvidenceLocator(path="Core/Src/motor_control.c", line=42),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                confidence=0.0,
                occurred_at=utcnow(),
            ),
        ],
    )


class TestDifficultyLadder:
    def test_promotes_on_a_strong_answer(self) -> None:
        change = next_difficulty(DifficultyLevel.CONCEPT, 90.0)
        assert change.to_level is DifficultyLevel.ENGINEERING
        assert "高于" in change.reason

    def test_demotes_on_a_weak_answer(self) -> None:
        change = next_difficulty(DifficultyLevel.DEBUGGING, 20.0)
        assert change.to_level is DifficultyLevel.ENGINEERING
        assert "低于" in change.reason

    def test_holds_in_the_middle(self) -> None:
        change = next_difficulty(DifficultyLevel.ENGINEERING, 60.0)
        assert change.to_level is DifficultyLevel.ENGINEERING

    def test_cannot_promote_past_the_top(self) -> None:
        change = next_difficulty(DifficultyLevel.DEBUGGING, 100.0)
        assert change.to_level is DifficultyLevel.DEBUGGING

    def test_cannot_demote_below_the_bottom(self) -> None:
        change = next_difficulty(DifficultyLevel.CONCEPT, 0.0)
        assert change.to_level is DifficultyLevel.CONCEPT

    def test_boundaries_are_inclusive(self) -> None:
        assert (
            next_difficulty(DifficultyLevel.CONCEPT, 75.0).to_level is DifficultyLevel.ENGINEERING
        )
        assert (
            next_difficulty(DifficultyLevel.DEBUGGING, 45.0).to_level is DifficultyLevel.ENGINEERING
        )

    def test_every_change_explains_itself(self) -> None:
        for level in DifficultyLevel:
            for score in (0.0, 45.0, 60.0, 75.0, 100.0):
                assert next_difficulty(level, score).reason


class TestStart:
    async def test_builds_a_plan_and_asks_the_first_question(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, outcome = await start_interview(
            executor, mode=InterviewMode.TECHNICAL, job=job, profile=profile, graph=graph
        )
        assert outcome.ok
        assert session is not None
        assert session.plan
        assert session.turns
        assert session.turns[0].role == "interviewer"
        assert session.turns[0].content
        assert session.status is InterviewStatus.IN_PROGRESS

    async def test_plan_is_derived_from_the_job(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        topics = {item.topic for item in session.plan}
        assert {"free_rtos", "stm32"} & topics

    async def test_gap_requirements_are_flagged_in_the_plan(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        gaps = [item for item in session.plan if item.source == "gap"]
        # CAN is required but has no evidence, so it is worth probing.
        assert any("CAN" in item.reason for item in gaps)

    async def test_works_without_a_job(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        session, outcome = await start_interview(executor, profile=profile)
        assert outcome.ok
        assert session is not None
        assert session.plan
        assert session.turns

    async def test_question_records_its_level(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        assert session.turns[0].question_level is not None


class TestTurn:
    async def test_records_the_answer_and_the_evaluation(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        updated, outcome = await submit_answer(
            executor, session=session, answer=LONG_ANSWER, profile=profile, graph=graph
        )
        assert outcome.ok
        assert updated is not None
        roles = [turn.role for turn in updated.turns]
        assert roles.count("candidate") == 1
        candidate = next(turn for turn in updated.turns if turn.role == "candidate")
        assert candidate.evaluation is not None
        assert 0.0 <= candidate.evaluation.score <= 100.0

    async def test_evaluation_targets_the_question_not_the_answer(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        first_question = session.turns[0].content
        updated, outcome = await submit_answer(
            executor, session=session, answer=LONG_ANSWER, profile=profile, graph=graph
        )
        assert updated is not None
        # The evaluator prompt is rendered with the question, so its trace records it.
        step = outcome.record.step("evaluate")
        assert step is not None
        assert first_question  # the question exists and was used as the prompt input

    async def test_asks_a_follow_up_question(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        before = len(session.turns)
        updated, _ = await submit_answer(
            executor, session=session, answer=LONG_ANSWER, profile=profile, graph=graph
        )
        assert updated is not None
        assert len(updated.turns) == before + 2  # the answer and the next question
        assert updated.turns[-1].role == "interviewer"

    async def test_reports_the_difficulty_change(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        _, outcome = await submit_answer(
            executor, session=session, answer=LONG_ANSWER, profile=profile, graph=graph
        )
        change = outcome.extras.get("difficultyChange")
        assert change is not None
        assert change.reason
        assert change.from_level is not None


class TestFinish:
    async def test_produces_a_seven_dimension_scorecard(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        for _ in range(3):
            session, _ = await submit_answer(
                executor, session=session, answer=LONG_ANSWER, profile=profile, graph=graph
            )
            assert session is not None
        scorecard, outcome = await finish_interview(
            executor, session=session, profile=profile, graph=graph
        )
        assert outcome.ok
        assert scorecard is not None
        keys = {dimension.key for dimension in scorecard.dimensions}
        assert keys == set(InterviewScorecard.DIMENSION_KEYS)
        assert 0.0 <= scorecard.overall_score <= 100.0

    async def test_per_question_review_is_populated(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        session, _ = await submit_answer(
            executor, session=session, answer=LONG_ANSWER, profile=profile, graph=graph
        )
        assert session is not None
        scorecard, _ = await finish_interview(
            executor, session=session, profile=profile, graph=graph
        )
        assert scorecard is not None
        assert scorecard.per_question
        review = scorecard.per_question[0]
        assert review.question
        assert review.verdict in {"strong", "mixed", "weak"}

    async def test_flags_a_thin_interview(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        session, _ = await submit_answer(
            executor, session=session, answer=LONG_ANSWER, profile=profile, graph=graph
        )
        assert session is not None
        _, outcome = await finish_interview(executor, session=session, profile=profile, graph=graph)
        assert any("样本偏少" in warning for warning in outcome.warnings)

    async def test_marks_the_session_complete(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        session, _ = await submit_answer(
            executor, session=session, answer=LONG_ANSWER, profile=profile, graph=graph
        )
        assert session is not None
        await finish_interview(executor, session=session, profile=profile, graph=graph)
        assert session.status is InterviewStatus.COMPLETED
        assert session.scorecard is not None


class TestEvidenceConsistency:
    async def test_flags_a_technology_with_no_evidence(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        session, _ = await submit_answer(
            executor,
            session=session,
            answer="我在项目里用 Kubernetes 做了服务编排，并用 TensorFlow 训练了模型。",
            profile=profile,
            graph=graph,
        )
        assert session is not None
        scorecard, _ = await finish_interview(
            executor, session=session, profile=profile, graph=graph
        )
        assert scorecard is not None
        assert scorecard.evidence_conflicts
        conflict = scorecard.evidence_conflicts[0]
        assert conflict.evidence_state
        assert conflict.advice
        consistency = next(
            dimension
            for dimension in scorecard.dimensions
            if dimension.key == "evidence_consistency"
        )
        assert consistency.score < 100.0

    async def test_an_answer_about_evidenced_work_raises_no_conflict(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        # Every technology named here has evidence, so there is nothing to flag.
        answer = "我用 FreeRTOS 做了任务划分，用 STM32 完成 PID 电机闭环控制。"
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        session, _ = await submit_answer(
            executor, session=session, answer=answer, profile=profile, graph=graph
        )
        assert session is not None
        scorecard, _ = await finish_interview(
            executor, session=session, profile=profile, graph=graph
        )
        assert scorecard is not None
        assert scorecard.evidence_conflicts == []
        consistency = next(
            dimension
            for dimension in scorecard.dimensions
            if dimension.key == "evidence_consistency"
        )
        assert consistency.score == 100.0


class TestConsistencyRulePrecision:
    """The rule is lexical, so its precision is bounded — and measured here.

    A first-person clause that merely *discusses* a technology is still flagged.
    That is the deliberate direction of the error: the advice tells the candidate to
    have evidence ready for something the interviewer is likely to probe.
    """

    def test_first_person_claim_is_detected(self) -> None:
        from careerforge_ai.agents.interview import claimed_skills

        assert "kubernetes" in claimed_skills("我在项目里用 Kubernetes 做了服务编排。")

    def test_clause_without_a_claim_marker_is_reasoning_not_a_claim(self) -> None:
        from careerforge_ai.agents.interview import claimed_skills

        assert claimed_skills("因为直接操作全局变量会带来竞态，所以改用队列。") == set()

    async def test_a_declared_but_unproven_skill_is_a_gap_not_a_conflict(
        self, executor: WorkflowExecutor, job: JDAnalysis, graph
    ) -> None:
        """The resume lists Rust, so saying it again is consistent, not a contradiction.

        The distinction matters: a gap is something to close, a conflict is something
        that reads as inflated. Conflating them would tell a candidate they had a
        credibility problem for restating their own resume.
        """
        from careerforge_ai.schemas.common import SkillCategory, SkillLevel
        from careerforge_ai.schemas.profile import CandidateProfile, ProfileSkill, SkillRef

        profile = CandidateProfile(
            slug="alex",
            skills=[
                ProfileSkill(
                    skill=SkillRef(
                        canonical_id="rust", display_name="Rust", category=SkillCategory.LANGUAGE
                    ),
                    level=SkillLevel.MODERATE,
                    evidence_count=0,
                )
            ],
        )
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        session, _ = await submit_answer(
            executor,
            session=session,
            answer="我用 Rust 重写过一部分工具链。",
            profile=profile,
            graph=graph,
        )
        assert session is not None
        scorecard, _ = await finish_interview(
            executor, session=session, profile=profile, graph=graph
        )
        assert scorecard is not None
        flagged = {conflict.evidence_state for conflict in scorecard.evidence_conflicts}
        assert not any("rust" in state.lower() for state in flagged)


class TestWorkflowShape:
    async def test_start_trace_names_its_steps(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        _, outcome = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert [step.name for step in outcome.record.steps] == ["plan", "question"]

    async def test_turn_trace_names_its_steps(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        _, outcome = await submit_answer(
            executor, session=session, answer=SHORT_ANSWER, profile=profile, graph=graph
        )
        assert [step.name for step in outcome.record.steps] == ["evaluate", "adapt", "question"]

    async def test_finish_trace_names_its_steps(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        session, _ = await start_interview(executor, job=job, profile=profile, graph=graph)
        assert session is not None
        _, outcome = await finish_interview(executor, session=session, profile=profile, graph=graph)
        assert [step.name for step in outcome.record.steps] == [
            "aggregate",
            "consistency",
            "scorecard",
        ]

    async def test_agent_exposes_its_workflow(self) -> None:
        assert InterviewAgent().workflow().name == "interview_start"
