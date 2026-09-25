"""PHASE 13 file-length split: helpers shared by the failure-injection suites.

Two suites drive failing providers now — ``test_failure_injection.py`` (the model and the retriever
misbehave) and ``test_failed_run_trace.py`` (nothing can serve the request, and what the trace says
about it) — and helpers copied into both would drift into two meanings of "the run row". Same
convention as ``failure_support.py``: not named ``test_*`` so pytest does not collect it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from careerforge_api.models.observability import AgentRun
from tests.conftest import Session
from tests.failure_support import run_job_through_the_tracker


async def post(client: AsyncClient, account: Session, path: str, payload: dict[str, Any]) -> Any:
    return await client.post(f"/api/v1{path}", json=payload, headers=account.headers)


async def run_row(app: FastAPI, run_id: str) -> AgentRun:
    """The row behind ``meta.run_id``, read from ``agent_runs`` rather than guessed from JSON."""
    async with app.state.session_factory() as db:
        row = await db.get(AgentRun, UUID(run_id))
    assert row is not None, "the run the response named was never written to agent_runs"
    return row


async def run_count(app: FastAPI) -> int:
    async with app.state.session_factory() as db:
        return int(await db.scalar(select(func.count()).select_from(AgentRun)) or 0)


async def newest_run_ids(app: FastAPI, *, limit: int = 1) -> list[UUID]:
    """The newest run ids, read from a fresh session.

    Uses the app's own session factory rather than a request, which is the point: the row a *failed*
    request left behind is only visible from outside that request's transaction.
    """
    async with app.state.session_factory() as db:
        rows = await db.scalars(
            select(AgentRun.id).order_by(AgentRun.started_at.desc()).limit(limit)
        )
        return list(rows.all())


async def newest_runs(app: FastAPI, *, limit: int = 1) -> list[AgentRun]:
    async with app.state.session_factory() as db:
        rows = await db.scalars(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit))
        return list(rows.all())


async def steps_of(client: AsyncClient, account: Session, run_id: str) -> dict[str, dict[str, Any]]:
    response = await client.get(f"/api/v1/ai-runs/{run_id}", headers=account.headers)
    assert response.status_code == 200, response.text
    return {step["name"]: step for step in response.json()["data"]["steps"]}


async def job_run_committed(
    app: FastAPI, account: Session, provider: Any, *, max_retries: int = 0
) -> tuple[AgentRun, BaseException | None]:
    return await run_job_through_the_tracker(app, account, provider, max_retries=max_retries)


__all__ = [
    "job_run_committed",
    "newest_run_ids",
    "newest_runs",
    "post",
    "run_count",
    "run_row",
    "steps_of",
]

#: The claim the gate is driven with. Real material, so a verdict about it means something. Defined
#: here as well as in the two suites so a future third one does not invent its own.
CLAIM = "使用 STM32 与 FreeRTOS 开发电机控制固件"

_ = Path
