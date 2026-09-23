"""``background_jobs`` access for the queue, the worker and ``/tasks/*``.

Two read paths, deliberately separate:

* :meth:`TaskRepository.get_for_user` — **always** filters by ``user_id``. This is
  what ``GET /tasks/{id}`` uses, so another user's task is indistinguishable from a
  missing one (``404 NOT_FOUND``, never ``403``; ``docs/API.md`` §1.2).
* :meth:`TaskRepository.get` — unfiltered, for the worker/queue itself, which is
  operating on jobs it already claims by id. It is named without a tenant
  qualifier precisely so an accidental use in a router is obvious in review.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.db.compat import utcnow
from careerforge_api.models.job import BackgroundJob

__all__ = ["TaskRepository"]


class TaskRepository:
    """Task persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── writes ───────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        kind: str,
        payload: dict[str, Any] | None = None,
        user_id: UUID | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> BackgroundJob:
        job = BackgroundJob(
            kind=kind,
            payload=dict(payload or {}),
            user_id=user_id,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
            status="queued",
            progress=0,
            attempts=0,
            queued_at=utcnow(),
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def mark_running(self, job_id: UUID, *, worker_id: str, stage: str | None = None) -> None:
        job = await self.get(job_id)
        if job is None or job.is_terminal:
            return
        job.status = "running"
        job.worker_id = worker_id
        job.started_at = job.started_at or utcnow()
        job.attempts += 1
        if stage is not None:
            job.stage = stage
        await self._session.flush()

    async def update_progress(
        self,
        job_id: UUID,
        *,
        stage: str | None = None,
        progress: int | None = None,
    ) -> None:
        job = await self.get(job_id)
        if job is None or job.is_terminal:
            return
        if stage is not None:
            job.stage = stage
        if progress is not None:
            job.progress = max(0, min(100, int(progress)))
        await self._session.flush()

    async def mark_succeeded(self, job_id: UUID, result: dict[str, Any] | None = None) -> None:
        job = await self.get(job_id)
        if job is None or job.is_terminal:
            return
        job.status = "succeeded"
        job.progress = 100
        job.result = dict(result or {})
        job.error = None
        job.finished_at = utcnow()
        await self._session.flush()

    async def mark_failed(self, job_id: UUID, error: str) -> None:
        job = await self.get(job_id)
        if job is None or job.is_terminal:
            return
        job.status = "failed"
        job.error = error[:2000]
        job.finished_at = utcnow()
        await self._session.flush()

    async def mark_cancelled(self, job_id: UUID, *, detail: str | None = None) -> None:
        job = await self.get(job_id)
        if job is None or job.is_terminal:
            return
        job.status = "cancelled"
        job.stage = "cancelled"
        job.error = detail
        job.finished_at = utcnow()
        await self._session.flush()

    # ── reads ────────────────────────────────────────────────────────────────

    async def get(self, job_id: UUID) -> BackgroundJob | None:
        """Unfiltered lookup for the worker/queue; **not** for request handlers."""
        return await self._session.get(BackgroundJob, job_id)

    async def get_for_user(
        self,
        job_id: UUID,
        *,
        user_id: UUID,
        allow_system_jobs: bool = True,
    ) -> BackgroundJob | None:
        """Tenant-scoped lookup: returns ``None`` for someone else's task.

        ``user_id IS NULL`` rows are system tasks (``docs/DATABASE.md`` §2.11 makes
        the column nullable for exactly that) and are readable by any authenticated
        user; they carry no tenant data.
        """
        job = await self._session.get(BackgroundJob, job_id)
        if job is None:
            return None
        if job.user_id == user_id:
            return job
        if job.user_id is None and allow_system_jobs:
            return job
        return None

    async def find_by_idempotency_key(self, key: str) -> BackgroundJob | None:
        statement = select(BackgroundJob).where(BackgroundJob.idempotency_key == key)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def next_queued(self, *, limit: int = 10) -> list[BackgroundJob]:
        """Oldest first (``ix_background_jobs_status_queued_at`` backs this)."""
        statement = (
            select(BackgroundJob)
            .where(BackgroundJob.status == "queued")
            .order_by(BackgroundJob.queued_at)
            .limit(limit)
        )
        return list((await self._session.execute(statement)).scalars())
