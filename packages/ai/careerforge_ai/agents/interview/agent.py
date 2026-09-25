"""The InterviewAgent and its three convenience entry points."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from careerforge_ai.agents.base import AgentOutcome, merge_workflow_warnings
from careerforge_ai.graph import GraphBuildResult
from careerforge_ai.orchestrator import Workflow, WorkflowExecutor
from careerforge_ai.schemas.common import (
    DegradationReason,
    DifficultyLevel,
    InterviewMode,
    InterviewStatus,
    utcnow,
)
from careerforge_ai.schemas.interview import (
    DifficultyChange,
    InterviewPlanItem,
    InterviewScorecard,
    InterviewSession,
    InterviewTurn,
    TurnEvaluation,
)
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile

__all__ = [
    "INTERVIEW_AGENT",
    "InterviewAgent",
    "build_start_workflow",
    "build_turn_workflow",
    "build_finish_workflow",
    "start_interview",
    "submit_answer",
    "finish_interview",
]

from careerforge_ai.agents.interview.plan import INTERVIEW_AGENT, mark_plan_coverage
from careerforge_ai.agents.interview.scorecard import (
    _MIN_QUESTIONS_FOR_SCORECARD,
    build_finish_workflow,
)
from careerforge_ai.agents.interview.turns import (
    build_start_workflow,
    build_turn_workflow,
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
        # The plan's ``covered`` flags are written from the turns that exist, never by the
        # planner: a first question on topic X marks X covered and leaves the rest open.
        mark_plan_coverage(session)

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
        mark_plan_coverage(session)

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

        # Stamped *before* the scorecard is aggregated, because the report's
        # ``duration_seconds`` is measured from this timestamp. Writing it after the workflow
        # returned would have left every scorecard reporting an interview that ended the
        # instant it started.
        session.completed_at = utcnow()
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
