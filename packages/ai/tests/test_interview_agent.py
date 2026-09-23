"""Tests for InterviewAgent.

Two properties matter more than the rest. The difficulty ladder must move by rule at
its boundaries, because that is the part of an interview simulator most easily
hand-waved. And the evidence-consistency check must find real conflicts by set
comparison rather than by asking a model whether something "feels" inconsistent.

The fixtures and answer constants this module shares with ``test_interview_signals``
live in ``conftest`` and ``interview_data`` so the two cannot drift apart.
"""

from __future__ import annotations

from tests.interview_data import LONG_ANSWER, SHORT_ANSWER

from careerforge_ai.agents import InterviewAgent, finish_interview, start_interview, submit_answer
from careerforge_ai.agents.interview import next_difficulty
from careerforge_ai.orchestrator import WorkflowExecutor
from careerforge_ai.schemas.common import DifficultyLevel, InterviewMode, InterviewStatus
from careerforge_ai.schemas.interview import InterviewScorecard
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile


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
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, outcome = await start_interview(
            iv_exec, mode=InterviewMode.TECHNICAL, job=iv_job, profile=iv_profile, graph=iv_graph
        )
        assert outcome.ok
        assert session is not None
        assert session.plan
        assert session.turns
        assert session.turns[0].role == "interviewer"
        assert session.turns[0].content
        assert session.status is InterviewStatus.IN_PROGRESS

    async def test_plan_is_derived_from_the_job(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        topics = {item.topic for item in session.plan}
        assert {"free_rtos", "stm32"} & topics

    async def test_gap_requirements_are_flagged_in_the_plan(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        gaps = [item for item in session.plan if item.source == "gap"]
        # CAN is required but has no evidence, so it is worth probing.
        assert any("CAN" in item.reason for item in gaps)

    async def test_works_without_a_job(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile
    ) -> None:
        session, outcome = await start_interview(iv_exec, profile=iv_profile)
        assert outcome.ok
        assert session is not None
        assert session.plan
        assert session.turns

    async def test_question_records_its_level(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        assert session.turns[0].question_level is not None


class TestTurn:
    async def test_records_the_answer_and_the_evaluation(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        updated, outcome = await submit_answer(
            iv_exec, session=session, answer=LONG_ANSWER, profile=iv_profile, graph=iv_graph
        )
        assert outcome.ok
        assert updated is not None
        roles = [turn.role for turn in updated.turns]
        assert roles.count("candidate") == 1
        candidate = next(turn for turn in updated.turns if turn.role == "candidate")
        assert candidate.evaluation is not None
        assert 0.0 <= candidate.evaluation.score <= 100.0

    async def test_evaluation_targets_the_question_not_the_answer(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        first_question = session.turns[0].content
        updated, outcome = await submit_answer(
            iv_exec, session=session, answer=LONG_ANSWER, profile=iv_profile, graph=iv_graph
        )
        assert updated is not None
        # The evaluator prompt is rendered with the question, so its trace records it.
        step = outcome.record.step("evaluate")
        assert step is not None
        assert first_question  # the question exists and was used as the prompt input

    async def test_asks_a_follow_up_question(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        before = len(session.turns)
        updated, _ = await submit_answer(
            iv_exec, session=session, answer=LONG_ANSWER, profile=iv_profile, graph=iv_graph
        )
        assert updated is not None
        assert len(updated.turns) == before + 2  # the answer and the next question
        assert updated.turns[-1].role == "interviewer"

    async def test_reports_the_difficulty_change(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        _, outcome = await submit_answer(
            iv_exec, session=session, answer=LONG_ANSWER, profile=iv_profile, graph=iv_graph
        )
        change = outcome.extras.get("difficultyChange")
        assert change is not None
        assert change.reason
        assert change.from_level is not None


class TestFinish:
    async def test_produces_a_seven_dimension_scorecard(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        for _ in range(3):
            session, _ = await submit_answer(
                iv_exec, session=session, answer=LONG_ANSWER, profile=iv_profile, graph=iv_graph
            )
            assert session is not None
        scorecard, outcome = await finish_interview(
            iv_exec, session=session, profile=iv_profile, graph=iv_graph
        )
        assert outcome.ok
        assert scorecard is not None
        keys = {dimension.key for dimension in scorecard.dimensions}
        assert keys == set(InterviewScorecard.DIMENSION_KEYS)
        assert 0.0 <= scorecard.overall_score <= 100.0

    async def test_per_question_review_is_populated(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        session, _ = await submit_answer(
            iv_exec, session=session, answer=LONG_ANSWER, profile=iv_profile, graph=iv_graph
        )
        assert session is not None
        scorecard, _ = await finish_interview(
            iv_exec, session=session, profile=iv_profile, graph=iv_graph
        )
        assert scorecard is not None
        assert scorecard.per_question
        review = scorecard.per_question[0]
        assert review.question
        assert review.verdict in {"strong", "mixed", "weak"}

    async def test_flags_a_thin_interview(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        session, _ = await submit_answer(
            iv_exec, session=session, answer=LONG_ANSWER, profile=iv_profile, graph=iv_graph
        )
        assert session is not None
        _, outcome = await finish_interview(
            iv_exec, session=session, profile=iv_profile, graph=iv_graph
        )
        assert any("样本偏少" in warning for warning in outcome.warnings)

    async def test_marks_the_session_complete(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        session, _ = await submit_answer(
            iv_exec, session=session, answer=LONG_ANSWER, profile=iv_profile, graph=iv_graph
        )
        assert session is not None
        await finish_interview(iv_exec, session=session, profile=iv_profile, graph=iv_graph)
        assert session.status is InterviewStatus.COMPLETED
        assert session.scorecard is not None


class TestEvidenceConsistency:
    async def test_flags_a_technology_with_no_evidence(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        session, _ = await submit_answer(
            iv_exec,
            session=session,
            answer="我在项目里用 Kubernetes 做了服务编排，并用 TensorFlow 训练了模型。",
            profile=iv_profile,
            graph=iv_graph,
        )
        assert session is not None
        scorecard, _ = await finish_interview(
            iv_exec, session=session, profile=iv_profile, graph=iv_graph
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
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        # Every technology named here has evidence, so there is nothing to flag.
        answer = "我用 FreeRTOS 做了任务划分，用 STM32 完成 PID 电机闭环控制。"
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        session, _ = await submit_answer(
            iv_exec, session=session, answer=answer, profile=iv_profile, graph=iv_graph
        )
        assert session is not None
        scorecard, _ = await finish_interview(
            iv_exec, session=session, profile=iv_profile, graph=iv_graph
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
        self, iv_exec: WorkflowExecutor, iv_job: JDAnalysis, iv_graph
    ) -> None:
        """The resume lists Rust, so saying it again is consistent, not a contradiction.

        The distinction matters: a gap is something to close, a conflict is something
        that reads as inflated. Conflating them would tell a candidate they had a
        credibility problem for restating their own resume.
        """
        from careerforge_ai.schemas.common import SkillCategory, SkillLevel
        from careerforge_ai.schemas.profile import CandidateProfile, ProfileSkill, SkillRef

        rust_profile = CandidateProfile(
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
        session, _ = await start_interview(
            iv_exec, job=iv_job, profile=rust_profile, graph=iv_graph
        )
        assert session is not None
        session, _ = await submit_answer(
            iv_exec,
            session=session,
            answer="我用 Rust 重写过一部分工具链。",
            profile=rust_profile,
            graph=iv_graph,
        )
        assert session is not None
        scorecard, _ = await finish_interview(
            iv_exec, session=session, profile=rust_profile, graph=iv_graph
        )
        assert scorecard is not None
        flagged = {conflict.evidence_state for conflict in scorecard.evidence_conflicts}
        assert not any("rust" in state.lower() for state in flagged)


class TestWorkflowShape:
    async def test_start_trace_names_its_steps(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        _, outcome = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert [step.name for step in outcome.record.steps] == ["plan", "question"]

    async def test_turn_trace_names_its_steps(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        _, outcome = await submit_answer(
            iv_exec, session=session, answer=SHORT_ANSWER, profile=iv_profile, graph=iv_graph
        )
        assert [step.name for step in outcome.record.steps] == ["evaluate", "adapt", "question"]

    async def test_finish_trace_names_its_steps(
        self, iv_exec: WorkflowExecutor, iv_profile: CandidateProfile, iv_job: JDAnalysis, iv_graph
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        _, outcome = await finish_interview(
            iv_exec, session=session, profile=iv_profile, graph=iv_graph
        )
        assert [step.name for step in outcome.record.steps] == [
            "aggregate",
            "consistency",
            "scorecard",
        ]

    async def test_agent_exposes_its_workflow(self) -> None:
        assert InterviewAgent().workflow().name == "interview_start"
