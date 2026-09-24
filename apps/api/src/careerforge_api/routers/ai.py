"""AI endpoints: the HTTP surface of the agent layer.

Scope, stated because the honest boundary matters more than the endpoint count:
these routes are **stateless**. Material arrives in the request body rather than by
id, because the tables those ids would point at (``jobs``, ``evidence``,
``documents``, ``resume_versions``) belong to phases that have not landed. When they
do, these handlers gain a persistence step and keep the same contracts.

What is real: every handler runs the production agent through a real
:class:`~careerforge_ai.orchestrator.WorkflowExecutor`, every run is written to
``agent_runs``, and every response carries metadata saying which provider served it
and whether the answer was degraded.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from careerforge_ai.agents import AgentOutcome
from careerforge_api.core.errors import NotFoundError, ValidationError
from careerforge_api.deps import CurrentUser, DbSession, OptionalUser, SettingsDep, get_request_id
from careerforge_api.schemas.ai import (
    AiMeta,
    AnalyzeJobRequest,
    AnalyzeJobResponse,
    CapabilitiesResponse,
    InterviewAnswerRequest,
    InterviewQuestion,
    InterviewSessionResponse,
    InterviewTurnResponse,
    MatchRequest,
    MatchResponse,
    StartInterviewRequest,
    ValidateClaimRequest,
    ValidateClaimResponse,
)
from careerforge_api.services.ai_service import AGENT_CATALOGUE, AIService, InterviewSessionStore

__all__ = ["get_ai_service", "get_interview_sessions", "router"]

router = APIRouter(tags=["ai"])


# ── dependencies ─────────────────────────────────────────────────────────────


def get_interview_sessions(request: Request) -> InterviewSessionStore:
    """The app-wide interview session store.

    App-wide rather than per-request because an interview spans several calls. It is
    in-process, so a second worker would not see a session started by the first —
    recorded as a limitation rather than left to be discovered.
    """
    store = getattr(request.app.state, "interview_sessions", None)
    if store is None:
        store = InterviewSessionStore()
        request.app.state.interview_sessions = store
    return store


async def get_ai_service(
    request: Request,
    session: DbSession,
    settings: SettingsDep,
    sessions: Annotated[InterviewSessionStore, Depends(get_interview_sessions)],
    user: OptionalUser,
) -> AsyncIterator[AIService]:
    """Bind the agent layer to this request's provider, prompts and session.

    A generator dependency so the metered model calls and cache events are flushed in the
    teardown, after the endpoint has run and while the request's session is still open. Doing it
    here rather than in each endpoint means a new AI endpoint cannot forget to record its
    calls — the failure mode that left ``llm_calls`` empty for an entire phase.
    """
    provider = getattr(request.app.state, "provider", None)
    prompts = getattr(request.app.state, "prompt_registry", None)
    if provider is None or prompts is None:  # pragma: no cover - lifespan always sets both
        raise ValidationError(
            "the AI layer is unavailable: the application did not finish starting up"
        )
    service = AIService(
        provider=provider,
        prompts=prompts,
        session=session,
        sessions=sessions,
        retriever=getattr(request.app.state, "retriever", None),
        # Built once with the provider chain, so a second identical request is served from the
        # first one's cache and the reported hit rate means something.
        cache_store=getattr(request.app.state, "ai_cache_store", None),
        user_id=user.id if user is not None else None,
    )
    try:
        yield service
    finally:
        await service.flush_observability()


AIServiceDep = Annotated[AIService, Depends(get_ai_service)]


def _meta(
    outcome: AgentOutcome,
    *,
    provider: str,
    workflow: str | None = None,
    prompt_version: str | None = None,
    cache_hit: bool = False,
) -> AiMeta:
    record = outcome.record
    return AiMeta(
        provider=provider,
        model=getattr(record, "model", None),
        prompt_version=prompt_version or getattr(record, "prompt_version", None),
        degraded=outcome.degraded,
        degraded_reason=outcome.degradation_reason.value,
        workflow=workflow or getattr(record, "workflow", None),
        run_id=getattr(record, "id", None),
        latency_ms=getattr(record, "latency_ms", None),
        cache_hit=cache_hit,
        warnings=list(outcome.warnings),
    )


# ── capabilities ─────────────────────────────────────────────────────────────


@router.get("/ai/capabilities", response_model=CapabilitiesResponse)
async def capabilities(
    request: Request,
    service: AIServiceDep,
    settings: SettingsDep,
    user: CurrentUser,
) -> CapabilitiesResponse:
    """What the agent layer can do — and what it cannot yet.

    Authenticated like the rest of ``/ai/*``: the payload names the provider chain and
    the deployment's limitations, which is deployment detail rather than public
    information. The limitations are still returned as data, so a client (or the
    architecture page) does not have to guess which half is real.
    """
    limitations: list[str] = []
    if service.retriever is None:
        limitations.append("证据检索未接入：断言验证只依据请求中提供的材料，不会去检索证据库")
    if settings.use_sqlite:
        limitations.append("当前使用 SQLite 与进程内队列，数据不跨进程共享")
    limitations.append("AI 端点为无状态实现：输入直接来自请求体，尚未与 jobs/evidence 表持久化打通")
    degraded = getattr(request.app.state, "provider", None) is not None and (
        service.provider_name == "heuristic"
    )
    active = get_interview_sessions(request).active
    return CapabilitiesResponse(
        agents=list(AGENT_CATALOGUE),
        provider=service.provider_name,
        provider_chain=list(settings.active_provider_chain()),
        degraded=degraded,
        retrieval_available=service.retriever is not None,
        session_store="in-process",
        active_interview_sessions=active,
        limitations=limitations,
    )


# ── stateless analysis ───────────────────────────────────────────────────────


@router.post("/ai/analyze/jd", response_model=AnalyzeJobResponse)
async def analyze_job(
    payload: AnalyzeJobRequest,
    service: AIServiceDep,
    user: CurrentUser,
    request_id: Annotated[str, Depends(get_request_id)],
) -> AnalyzeJobResponse:
    """Parse a job description into the structured, taxonomy-normalised analysis."""
    outcome = await service.job_agent().run(service.executor(), text=payload.text)
    analysis = outcome.value
    if analysis is None:
        raise ValidationError("岗位描述解析失败，请检查文本内容")

    # The executor's tracker attributes the run, but the approval to spend belongs to
    # the caller — so the run is bound to the authenticated user explicitly.
    return AnalyzeJobResponse(
        analysis=analysis,
        meta=_meta(
            outcome,
            provider=service.provider_name,
            workflow="jd_analysis",
            prompt_version="jd_analysis@v1",
        ),
    )


@router.post("/ai/validate/claim", response_model=ValidateClaimResponse)
async def validate_claim(
    payload: ValidateClaimRequest,
    service: AIServiceDep,
    user: CurrentUser,
) -> ValidateClaimResponse:
    """Run the hallucination gate over one claim.

    The endpoint exists so the gate can be probed directly — the fastest way for a
    reviewer to see that a fabricated metric is refused rather than reworded.
    """
    outcome = await service.validator_agent().run(
        service.executor(),
        claim=payload.claim,
        evidence_text=payload.evidence_text,
        job_context=payload.job_context,
        retriever=service.retriever,
        user_id=user.id,
    )
    validation = outcome.value
    if validation is None:
        raise ValidationError("断言验证未能完成")

    return ValidateClaimResponse(
        status=validation.status.value,
        confidence=validation.confidence,
        allows_resume_inclusion=validation.allows_resume_inclusion,
        is_blocking=validation.is_blocking,
        sources=[source.model_dump(mode="json") for source in validation.sources],
        reasons=[reason.model_dump(mode="json") for reason in validation.reasons],
        safe_rewrite=(
            validation.safe_rewrite.model_dump(mode="json") if validation.safe_rewrite else None
        ),
        unknowns=list(validation.unknowns),
        independent_source_count=validation.independent_source_count,
        meta=_meta(
            outcome,
            provider=service.provider_name,
            workflow="claim_validate",
            prompt_version="evidence_validator@v1",
        ),
    )


@router.post("/ai/match", response_model=MatchResponse)
async def match(
    payload: MatchRequest,
    service: AIServiceDep,
    user: CurrentUser,
) -> MatchResponse:
    """Score a candidate against a job description.

    Both inputs are supplied in the request: without the evidence tables there is no
    stored profile to load, and inventing one would make the score meaningless.
    """
    outcome = await service.match_agent().run(
        service.executor(), job=payload.job, profile=payload.profile
    )
    result = outcome.value
    if result is None:
        raise ValidationError("匹配评分未能完成")

    return MatchResponse(
        score=result.score,
        dimensions={
            key: dimension.model_dump(mode="json") for key, dimension in result.dimensions.items()
        },
        strengths=[item.model_dump(mode="json") for item in result.strengths],
        gaps=[item.model_dump(mode="json") for item in result.gaps],
        unknowns=[item.model_dump(mode="json") for item in result.unknowns],
        why=result.why.model_dump(mode="json"),
        narrative=result.narrative,
        evidence_coverage=result.evidence_coverage,
        meta=_meta(
            outcome,
            provider=service.provider_name,
            workflow="job_match",
            prompt_version="match_explainer@v1",
        ),
    )


# ── interview ────────────────────────────────────────────────────────────────


def _question_payload(turn: Any) -> InterviewQuestion | None:
    if turn is None:
        return None
    return InterviewQuestion(
        turn_index=turn.turn_index,
        content=turn.content,
        topic=turn.topic,
        level=turn.question_level.value if turn.question_level else None,
    )


def _session_payload(session_id: UUID, session: Any) -> InterviewSessionResponse:
    scorecard = session.scorecard.model_dump(mode="json") if session.scorecard else None
    return InterviewSessionResponse(
        session_id=session_id,
        mode=session.mode.value,
        status=session.status.value,
        current_level=session.current_level.value,
        plan=[item.model_dump(mode="json") for item in session.plan],
        turns=[
            {
                "turn_index": turn.turn_index,
                "role": turn.role,
                "content": turn.content,
                "topic": turn.topic,
                "level": turn.question_level.value if turn.question_level else None,
                "score": turn.evaluation.score if turn.evaluation else None,
            }
            for turn in session.turns
        ],
        scorecard=scorecard,
        meta=AiMeta(provider="session", workflow="interview"),
    )


@router.post("/ai/interview/start", response_model=InterviewSessionResponse)
async def start_interview(
    payload: StartInterviewRequest,
    service: AIServiceDep,
    user: CurrentUser,
) -> InterviewSessionResponse:
    """Plan an interview and ask the opening question."""
    outcome = await service.interview_agent().start(
        service.executor(),
        mode=payload.mode,
        job=payload.job,
        profile=payload.profile,
        difficulty=payload.difficulty,
    )
    session = outcome.value
    if session is None:
        raise ValidationError("面试会话创建失败")

    session_id = service.sessions.put(session, user_id=user.id)
    response = _session_payload(session_id, session)
    response.meta = _meta(
        outcome,
        provider=service.provider_name,
        workflow="interview_start",
        prompt_version="interviewer@v1",
    )
    return response


@router.post("/ai/interview/{session_id}/answer", response_model=InterviewTurnResponse)
async def answer_interview(
    session_id: UUID,
    payload: InterviewAnswerRequest,
    service: AIServiceDep,
    user: CurrentUser,
) -> InterviewTurnResponse:
    """Evaluate an answer, adapt the difficulty and ask the next question."""
    session = service.sessions.get(session_id, user_id=user.id)
    if session is None:
        raise NotFoundError("Interview session not found")

    outcome = await service.interview_agent().answer(
        service.executor(), session=session, answer=payload.answer
    )
    evaluation = outcome.extras.get("evaluation")
    change = outcome.extras.get("difficultyChange")
    next_question = outcome.extras.get("nextQuestion")

    return InterviewTurnResponse(
        session_id=session_id,
        status=session.status.value,
        current_level=session.current_level.value,
        evaluation=evaluation.model_dump(mode="json") if evaluation else None,
        difficulty_change=change.model_dump(mode="json") if change else None,
        next_question=_question_payload(next_question),
        meta=_meta(
            outcome,
            provider=service.provider_name,
            workflow="interview_turn",
            prompt_version="interview_evaluator@v1",
        ),
    )


@router.post("/ai/interview/{session_id}/finish", response_model=InterviewSessionResponse)
async def finish_interview(
    session_id: UUID,
    service: AIServiceDep,
    user: CurrentUser,
) -> InterviewSessionResponse:
    """Aggregate the scorecard and close the session."""
    session = service.sessions.get(session_id, user_id=user.id)
    if session is None:
        raise NotFoundError("Interview session not found")

    outcome = await service.interview_agent().finish(service.executor(), session=session)
    response = _session_payload(session_id, session)
    response.meta = _meta(outcome, provider=service.provider_name, workflow="interview_finish")
    return response


@router.get("/ai/interview/{session_id}", response_model=InterviewSessionResponse)
async def get_interview(
    session_id: UUID,
    service: AIServiceDep,
    user: CurrentUser,
) -> InterviewSessionResponse:
    """Resume a session after a reload — the reason the store is not per-request."""
    session = service.sessions.get(session_id, user_id=user.id)
    if session is None:
        raise NotFoundError("Interview session not found")
    return _session_payload(session_id, session)


@router.delete("/ai/interview/{session_id}", status_code=204)
async def abandon_interview(
    session_id: UUID,
    service: AIServiceDep,
    user: CurrentUser,
    settings: SettingsDep,
) -> Response:
    """Discard a session. Returns 204 with no body, so no envelope is produced."""
    if service.sessions.get(session_id, user_id=user.id) is None:
        raise NotFoundError("Interview session not found")
    service.sessions.drop(session_id)
    return Response(status_code=204)
