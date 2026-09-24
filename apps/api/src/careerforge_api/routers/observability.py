"""``/ai-runs``, ``/ai-costs``, ``/cache``, ``/prompts`` — ``docs/API.md`` §2.12.

The AI Runs page exists to answer one question a reviewer will ask: *can I see what the model was
actually asked and what it cost?* So every response here is read straight from ``agent_runs`` and
``llm_calls`` — the rows the executor and the metered provider wrote — and nothing is estimated.
When a deployment runs on the zero-key heuristic provider the tokens really are zero; the payload
says so via ``provider`` and ``notes`` instead of showing an invented number.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query, Request

from careerforge_api.core.errors import NotFoundError
from careerforge_api.deps import CurrentUser, DbSession, SettingsDep
from careerforge_api.schemas.observability import (
    AiCostsResponse,
    AiRunDetailResponse,
    AiRunResponse,
    AiStepResponse,
    CacheStatsResponse,
    CostBreakdown,
    CostByEntity,
    CostTotals,
    DailyCost,
    LlmCallResponse,
    PromptVersionResponse,
)
from careerforge_api.services.metering import DatabaseCacheStore
from careerforge_api.services.observability_service import ObservabilityService

__all__ = ["router"]

router = APIRouter(tags=["observability"])

_RANGE = Query(default="7d", alias="range", pattern="^(7d|30d|90d|all)$")

#: Shown beside the numbers. A dashboard that reports 0 tokens without saying why invites the
#: reader to conclude the metering is broken, when in fact the provider charges nothing.
#: A tuple, not a parenthesised string: ``list("abc")`` is ``['a','b','c']``, which is how the
#: first version of this served a note spelled out one character per element.
_NOTES = (
    "token 与成本来自 provider 自报的用量；零 Key 的 heuristic 路径不产生 token，"
    "因此这些运行的 token/成本为 0 而延迟仍被测量。",
)


def _cache_store(request: Request) -> DatabaseCacheStore | None:
    return getattr(request.app.state, "ai_cache_store", None)


def _run_response(row: Any) -> AiRunResponse:
    return AiRunResponse(
        id=str(row.id),
        user_id=str(row.user_id) if row.user_id else None,
        workflow=row.workflow,
        agent=row.agent,
        status=row.status,
        trigger=row.trigger,
        provider=row.provider,
        model=row.model,
        prompt_version=row.prompt_version,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        total_tokens=row.total_tokens,
        cost_usd=float(row.cost_usd),
        cost_cny=float(row.cost_cny),
        latency_ms=row.latency_ms,
        cache_hit=row.cache_hit,
        request_id=row.request_id,
        error=row.error,
        step_count=len(row.steps or []),
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _step_response(step: dict[str, Any]) -> AiStepResponse:
    return AiStepResponse(
        name=str(step.get("name") or ""),
        status=str(step.get("status") or "ok"),
        latency_ms=int(step.get("latency_ms") or 0),
        provider=step.get("provider"),
        model=step.get("model"),
        prompt_version=step.get("prompt_version"),
        attempts=int(step.get("attempts") or 1),
        cache_hit=bool(step.get("cache_hit")),
        tokens=int((step.get("tokens") or {}).get("total_tokens") or 0),
        cost_usd=float((step.get("cost") or {}).get("usd") or 0.0),
        input_digest=str(step.get("input_digest") or ""),
        output_digest=str(step.get("output_digest") or ""),
        error_code=step.get("error_code"),
        error_message=step.get("error_message"),
        started_at=step.get("started_at"),
    )


@router.get("/ai-runs", summary="Traced agent runs, newest first")
async def list_ai_runs(
    session: DbSession,
    user: CurrentUser,
    agent: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    status: str | None = Query(
        default=None, pattern="^(running|succeeded|failed|degraded|cancelled)$"
    ),
    since_hours: int | None = Query(default=None, alias="sinceHours", ge=1, le=24 * 90),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Every AI operation the system performed, with its tokens, cost and latency.

    Runs with no owner (a seed, a scheduled job) are included: an operator asking "what has this
    deployment spent" wants the whole picture, and pretending those runs do not exist would
    understate it.
    """
    since = datetime.now(tz=None) - timedelta(hours=since_hours) if since_hours else None
    rows, total = await ObservabilityService(session).list_runs(
        agent=agent,
        workflow=workflow,
        status=status,
        since=since,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_run_response(row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/ai-runs/{run_id}", summary="One run: its steps, calls and totals")
async def get_ai_run(run_id: str, session: DbSession, user: CurrentUser) -> AiRunDetailResponse:
    """The step chain, plus one row per model call the run made.

    ``steps`` is the workflow's own trace (one entry per ``Step``), ``calls`` is the metered
    provider's record (one entry per model request). They are different granularities on purpose:
    a step can make two calls, and a call can happen outside a step.
    """
    try:
        parsed = UUID(run_id)
    except ValueError as exc:
        raise NotFoundError("Run not found") from exc

    service = ObservabilityService(session)
    row = await service.get_run(parsed)
    if row is None:
        raise NotFoundError("Run not found")
    calls = await service.calls_of(parsed)

    base = _run_response(row)
    return AiRunDetailResponse(
        **base.model_dump(),
        steps=[_step_response(step) for step in (row.steps or [])],
        calls=[
            LlmCallResponse(
                id=str(call.id),
                agent=call.agent,
                provider=call.provider,
                model=call.model,
                operation=call.operation,
                prompt_version=call.prompt_version,
                prompt_tokens=call.prompt_tokens,
                completion_tokens=call.completion_tokens,
                total_tokens=call.total_tokens,
                cost_usd=float(call.cost_usd),
                cost_cny=float(call.cost_cny),
                latency_ms=call.latency_ms,
                status=call.status,
                created_at=call.created_at,
            )
            for call in calls
        ],
        input_ref=dict(row.input_ref or {}),
        output_ref=dict(row.output_ref or {}),
    )


@router.get("/ai-costs", summary="Daily tokens and cost, with totals")
async def get_ai_costs(
    session: DbSession,
    user: CurrentUser,
    settings: SettingsDep,
    range_key: str = _RANGE,
) -> AiCostsResponse:
    summary = await ObservabilityService(session).cost_summary(range_key=range_key)
    budget = getattr(settings, "ai_daily_budget_usd", 0.0)
    return AiCostsResponse(
        range=str(summary["range"]),
        days=[DailyCost(**day) for day in summary["days"]],
        totals=CostTotals(**summary["totals"]),
        daily_budget_usd=float(budget),
        notes=list(_NOTES),
    )


@router.get("/ai-costs/by-agent", summary="Cost per agent")
async def get_costs_by_agent(
    session: DbSession,
    user: CurrentUser,
    range_key: str = _RANGE,
) -> list[CostByEntity]:
    rows = await ObservabilityService(session).cost_by_agent(range_key=range_key)
    return [CostByEntity(**row) for row in rows]


@router.get("/ai-costs/by-feature", summary="Cost per product feature")
async def get_costs_by_feature(
    session: DbSession,
    user: CurrentUser,
    range_key: str = _RANGE,
) -> list[CostBreakdown]:
    rows = await ObservabilityService(session).cost_by_feature(range_key=range_key)
    return [CostBreakdown(**row) for row in rows]


@router.get("/cache/stats", summary="Cache entries and hit rates, by kind")
async def get_cache_stats(
    request: Request, session: DbSession, user: CurrentUser
) -> CacheStatsResponse:
    """Persisted entries and hits per kind, beside the current process's counters."""
    stats = await ObservabilityService(session).cache_stats(store=_cache_store(request))
    return CacheStatsResponse(**stats)


@router.get("/prompts", summary="Prompt registry: versions, digests and which is active")
async def list_prompts(session: DbSession, user: CurrentUser) -> list[PromptVersionResponse]:
    rows = await ObservabilityService(session).prompt_versions()
    return [PromptVersionResponse(**row) for row in rows]
