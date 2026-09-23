"""Regression tests for interview behaviour that a real HTTP request caught.

Everything here maps to a defect the workflow tests in ``test_interview_agent`` did not
catch, and none of it duplicates them:

* the interviewer asked the opening question again as its follow-up, because the planned
  topic only travelled as a prompt variable while the deterministic handler reads the
  port's structured channel;
* ``confidence`` was reported as ``0.0`` — a scored dimension nothing had measured;
* the follow-up question ignored the plan, so the interview read as shallow rather than
  as broken, which is exactly why it needed a test instead of a comment.

Shared inputs come from ``conftest`` (``iv_*`` fixtures) and ``interview_data``, so this
module and ``test_interview_agent`` cannot drift onto different setups.
"""

from __future__ import annotations

from tests.interview_data import LONG_ANSWER

from careerforge_ai.agents import finish_interview, start_interview, submit_answer
from careerforge_ai.orchestrator import WorkflowExecutor
from careerforge_ai.providers.heuristic.handlers_interview import _confidence_proxy
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile


class TestQuestionSelection:
    async def test_the_follow_up_is_not_the_opening_question(
        self,
        iv_exec: WorkflowExecutor,
        iv_profile: CandidateProfile,
        iv_job: JDAnalysis,
        iv_graph,
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        opening = session.turns[0].content
        updated, _ = await submit_answer(
            iv_exec,
            session=session,
            answer=LONG_ANSWER,
            profile=iv_profile,
            graph=iv_graph,
        )
        assert updated is not None
        assert updated.turns[-1].content != opening

    async def test_the_opening_question_targets_a_planned_topic(
        self,
        iv_exec: WorkflowExecutor,
        iv_profile: CandidateProfile,
        iv_job: JDAnalysis,
        iv_graph,
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        planned = {item.topic for item in session.plan} | {"_default", "hr", "project"}
        assert session.turns[0].topic in planned


class TestConfidenceDimension:
    """``confidence`` must be a measurement, not a placeholder field."""

    async def test_a_strong_answer_produces_a_non_zero_confidence(
        self,
        iv_exec: WorkflowExecutor,
        iv_profile: CandidateProfile,
        iv_job: JDAnalysis,
        iv_graph,
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        updated, _ = await submit_answer(
            iv_exec,
            session=session,
            answer=LONG_ANSWER,
            profile=iv_profile,
            graph=iv_graph,
        )
        assert updated is not None
        candidate = next(turn for turn in updated.turns if turn.role == "candidate")
        assert candidate.evaluation is not None
        assert candidate.evaluation.confidence > 0.0

    async def test_the_scorecard_reports_the_measured_confidence(
        self,
        iv_exec: WorkflowExecutor,
        iv_profile: CandidateProfile,
        iv_job: JDAnalysis,
        iv_graph,
    ) -> None:
        session, _ = await start_interview(iv_exec, job=iv_job, profile=iv_profile, graph=iv_graph)
        assert session is not None
        for _ in range(3):
            session, _ = await submit_answer(
                iv_exec,
                session=session,
                answer=LONG_ANSWER,
                profile=iv_profile,
                graph=iv_graph,
            )
            assert session is not None
        scorecard, _ = await finish_interview(
            iv_exec, session=session, profile=iv_profile, graph=iv_graph
        )
        assert scorecard is not None
        confidence = next(d for d in scorecard.dimensions if d.key == "confidence")
        assert confidence.score > 0.0

    def test_hedging_lowers_the_proxy(self) -> None:
        assured = "我用 FreeRTOS 做了任务划分，因为我需要确定性的调度。"
        hedged = "我可能用过 FreeRTOS 吧，大概是做任务划分，不太确定具体细节。"
        assert _confidence_proxy(assured, ["任务"], 0.6) > _confidence_proxy(hedged, ["任务"], 0.6)

    def test_the_proxy_stays_within_bounds(self) -> None:
        # A scored dimension that can leave [0, 100] would break the scorecard, so the
        # bounds are checked at the extremes rather than only on a realistic answer.
        for answer in ("", "短", LONG_ANSWER * 3):
            for length_factor in (0.0, 0.5, 1.0):
                assert 0.0 <= _confidence_proxy(answer, [], length_factor) <= 100.0
