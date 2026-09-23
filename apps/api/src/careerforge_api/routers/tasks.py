"""``/tasks`` — polling and cancelling asynchronous tasks (``docs/API.md`` §1.4/§2.13).

Long operations return ``202`` with a task id; these endpoints are how the client
follows one. The payload always carries the five documented keys — ``status``,
``progress``, ``stage``, ``result``, ``error`` — plus the id and timestamps the UI
already knows, so a client never has to correlate anything itself.

Task ids are the documented ``tsk_…`` handle derived from the row's UUID
(:func:`careerforge_api.core.ids.task_public_id`); a bare UUID is accepted too, which
keeps hand-written curl calls and log greps usable.

``GET /tasks/{id}/stream`` (SSE, §1.5) is **not** implemented in PHASE 1 — streaming
arrives with the interview and resume-generation endpoints, which are the features
that need it. ``streamUrl`` is already part of the ``202`` contract, so a client can
feature-detect on its presence.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from careerforge_api.core.errors import NotFoundError
from careerforge_api.core.ids import parse_task_id, task_public_id
from careerforge_api.deps import CurrentUser, DbSession
from careerforge_api.models.job import BackgroundJob
from careerforge_api.repositories.task_repository import TaskRepository
from careerforge_api.schemas.task import TaskCancelResponse, TaskResponse

__all__ = ["router"]

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _task_id(raw: str) -> UUID:
    """Parse the public handle; a malformed id is a 404, not a 400.

    ``docs/API.md`` §1.2 treats "not yours" and "does not exist" identically, and a
    malformed id is simply another id that does not exist.
    """
    parsed = parse_task_id(raw)
    if parsed is None:
        raise NotFoundError("Task not found")
    return parsed


def _to_response(job: BackgroundJob) -> TaskResponse:
    """Field names in, camelCase out (`response_model_by_alias`)."""
    return TaskResponse(
        task_id=task_public_id(job.id),
        kind=job.kind,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        result=job.result,
        error=job.error,
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def _load_own_task(task_id: str, *, session: DbSession, user: CurrentUser) -> BackgroundJob:
    """Tenant-scoped fetch: another user's task is a ``404``, never a ``403``.

    The filter lives in the repository, so a caller cannot accidentally widen it.
    """
    repository = TaskRepository(session)
    job = await repository.get_for_user(_task_id(task_id), user_id=user.id)
    if job is None:
        raise NotFoundError("Task not found")
    return job


@router.get("/{task_id}", summary="Task status")
async def get_task(task_id: str, session: DbSession, user: CurrentUser) -> TaskResponse:
    job = await _load_own_task(task_id, session=session, user=user)
    return _to_response(job)


@router.post("/{task_id}/cancel", summary="Cancel a queued or running task")
async def cancel_task(
    task_id: str,
    request: Request,
    session: DbSession,
    user: CurrentUser,
) -> TaskCancelResponse:
    """Idempotent: cancelling a finished task reports its final state with ``cancelled: false``."""
    job = await _load_own_task(task_id, session=session, user=user)
    if job.is_terminal:
        return TaskCancelResponse(
            **_to_response(job).model_dump(),
            cancelled=False,
            detail=f"task is already {job.status}",
        )

    queue = getattr(request.app.state, "queue", None)
    if queue is None:  # pragma: no cover - only when create_app was bypassed
        repository = TaskRepository(session)
        await repository.mark_cancelled(job.id, detail="cancelled by request")
        await session.commit()
        refreshed = await repository.get(job.id)
        assert refreshed is not None
        job = refreshed
    else:
        job = await queue.cancel(job.id, user_id=user.id)
    return TaskCancelResponse(**_to_response(job).model_dump(), cancelled=job.status == "cancelled")
