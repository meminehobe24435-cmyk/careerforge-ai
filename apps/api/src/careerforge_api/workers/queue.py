"""The task queue port and its two implementations.

``docs/ARCHITECTURE.md`` §1.3 defines the split this module implements:

* **InProcessQueue** — the zero-dependency path. Work runs in the API process as an
  ``asyncio`` task, but every state change is written to ``background_jobs`` first,
  so ``GET /tasks/{id}`` reports the same thing it would in the Docker topology
  (``queued → running → succeeded/failed``, with ``stage`` and ``progress``). A
  cancelled or crashed job leaves an honest row behind rather than disappearing.
* **RedisQueue** — the production path, which is **not implemented in PHASE 1**.
  It raises a clear :class:`~careerforge_api.core.errors.DependencyUnavailableError`
  instead of pretending, and it refuses to construct at all unless
  ``QUEUE_BACKEND=redis``. The Docker topology in PHASE 15 replaces this class; the
  port below is the contract it must satisfy.

:func:`build_queue` chooses between them and reports the downgrade it had to apply,
which ``GET /system/health`` publishes instead of hiding.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
import contextlib
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from careerforge_api.core.config import APISettings
from careerforge_api.core.errors import DependencyUnavailableError, NotFoundError
from careerforge_api.core.ids import new_ulid
from careerforge_api.core.logging import get_logger
from careerforge_api.models.job import BackgroundJob
from careerforge_api.repositories.task_repository import TaskRepository

__all__ = [
    "BUILTIN_JOB_KINDS",
    "HandlerContext",
    "InProcessQueue",
    "JobHandler",
    "QueuePort",
    "QueueSelection",
    "RedisQueue",
    "build_queue",
    "build_queue_selection",
]

_logger = get_logger("careerforge_api.workers.queue")

#: Message used everywhere the Redis path is unavailable, so the reason is never vague.
REDIS_UNAVAILABLE_MESSAGE = (
    "Redis queue is not available in this environment: QUEUE_BACKEND=redis requires a "
    "running Redis server and the redis client, neither of which exists without the "
    "Docker topology (PHASE 15). Set USE_SQLITE=true / QUEUE_BACKEND=inprocess to use "
    "the in-process queue, which persists task state in background_jobs."
)

#: Job kinds the API can execute out of the box. Real kinds (``profile.import``,
#: ``github.analyze``, …) are registered by the phases that introduce them.
BUILTIN_JOB_KINDS: tuple[str, ...] = ("system.ping", "system.noop")


@dataclass(slots=True)
class HandlerContext:
    """What a job handler is given."""

    job_id: UUID
    kind: str
    payload: dict[str, Any]
    user_id: UUID | None
    #: ``await ctx.report(stage="parsing", progress=10)`` — persisted immediately.
    report: Callable[[str, int], Awaitable[None]]
    #: True once the row says cancelled; long handlers should check it between stages.
    is_cancelled: Callable[[], Awaitable[bool]]


JobHandler = Callable[[HandlerContext], Awaitable[Mapping[str, Any] | None]]


@runtime_checkable
class QueuePort(Protocol):
    """What a queue implementation must provide."""

    backend_name: str

    async def enqueue(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        user_id: UUID | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> BackgroundJob: ...

    async def get(self, job_id: UUID, *, user_id: UUID | None = None) -> BackgroundJob | None: ...

    async def cancel(self, job_id: UUID, *, user_id: UUID | None = None) -> BackgroundJob: ...

    def register_handler(self, kind: str, handler: JobHandler) -> None: ...

    def registered_kinds(self) -> list[str]:
        """Which job kinds this process can actually run.

        Part of the port rather than an implementation detail: startup logs it, and it is
        how a misconfigured deployment (an API image with no handlers) is visible instead
        of failing every job at claim time.
        """
        ...

    async def shutdown(self) -> None: ...


class _QueueBase:
    """Shared handler registry and task bookkeeping."""

    backend_name = "unknown"

    def __init__(self, *, worker_id: str | None = None) -> None:
        self.worker_id = worker_id or f"worker-{new_ulid()[:10]}"
        self._handlers: dict[str, JobHandler] = {}
        self._tasks: dict[UUID, asyncio.Task[None]] = {}
        self._cancelled: set[UUID] = set()
        self.register_handler("system.ping", _ping_handler)
        self.register_handler("system.noop", _noop_handler)

    def register_handler(self, kind: str, handler: JobHandler) -> None:
        self._handlers[kind] = handler

    def registered_kinds(self) -> list[str]:
        return sorted(self._handlers)

    def _handler_for(self, kind: str) -> JobHandler | None:
        return self._handlers.get(kind)


async def _ping_handler(context: HandlerContext) -> Mapping[str, Any]:
    """Built-in liveness handler: two stages, so ``/tasks/{id}`` has something to show."""
    await context.report("starting", 10)
    await asyncio.sleep(0.05)
    await context.report("running", 50)
    await asyncio.sleep(0.05)
    await context.report("finishing", 90)
    return {"pong": True, "payload": dict(context.payload)}


async def _noop_handler(context: HandlerContext) -> Mapping[str, Any]:
    await context.report("done", 100)
    return {"noop": True}


class InProcessQueue(_QueueBase):
    """``asyncio`` task queue with durable state in ``background_jobs`` (ADR-010)."""

    backend_name = "inprocess"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        concurrency: int = 2,
        worker_id: str | None = None,
    ) -> None:
        super().__init__(worker_id=worker_id)
        self._session_factory = session_factory
        self._semaphore = asyncio.Semaphore(max(1, concurrency))

    # ── port implementation ──────────────────────────────────────────────────

    async def enqueue(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        user_id: UUID | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> BackgroundJob:
        async with self._session_factory() as session:
            repository = TaskRepository(session)
            if idempotency_key:
                # 24h replay rule (docs/API.md §1.4): return the first job, not a second one.
                existing = await repository.find_by_idempotency_key(idempotency_key)
                if existing is not None:
                    await session.commit()
                    return existing
            job = await repository.create(
                kind=kind,
                payload=dict(payload or {}),
                user_id=user_id,
                idempotency_key=idempotency_key,
                max_attempts=max_attempts,
            )
            job_id = job.id
            await session.commit()

        # The freshly created row is returned as-is rather than re-read: the execution
        # task starts immediately, and a second SELECT could already observe it running
        # (or finished). The caller asked for "queued", so it gets "queued" — the same
        # determinism the 202 response in docs/API.md §1.4 depends on.
        self._tasks[job_id] = asyncio.create_task(self._run(job_id), name=f"job-{job_id}")
        return job

    async def get(self, job_id: UUID, *, user_id: UUID | None = None) -> BackgroundJob | None:
        async with self._session_factory() as session:
            repository = TaskRepository(session)
            if user_id is None:
                return await repository.get(job_id)
            return await repository.get_for_user(job_id, user_id=user_id)

    async def cancel(self, job_id: UUID, *, user_id: UUID | None = None) -> BackgroundJob:
        async with self._session_factory() as session:
            repository = TaskRepository(session)
            job = (
                await repository.get(job_id)
                if user_id is None
                else await repository.get_for_user(job_id, user_id=user_id)
            )
            if job is None:
                raise NotFoundError("Task not found")
            if job.is_terminal:
                await session.commit()
                return job
            self._cancelled.add(job_id)
            task = self._tasks.get(job_id)
            if task is not None and not task.done():
                task.cancel()
            await repository.mark_cancelled(job_id, detail="cancelled by request")
            await session.commit()
            refreshed = await repository.get(job_id)
            assert refreshed is not None
            return refreshed

    async def shutdown(self) -> None:
        """Cancel everything still running (used by the lifespan on the way out)."""
        tasks = [task for task in self._tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    def submit_existing(self, job_id: UUID) -> asyncio.Task[None] | None:
        """Execute a row that another process (or a previous request) already queued.

        This is how the standalone worker in ``careerforge_api.workers.main`` drives
        the same execution path as an in-API enqueue, so the status transitions have
        exactly one implementation.
        """
        if job_id in self._tasks and not self._tasks[job_id].done():
            return None
        task = asyncio.create_task(self._run(job_id), name=f"job-{job_id}")
        self._tasks[job_id] = task
        return task

    # ── execution ────────────────────────────────────────────────────────────

    async def _run(self, job_id: UUID) -> None:
        async with self._semaphore:
            handler = None
            async with self._session_factory() as session:
                repository = TaskRepository(session)
                job = await repository.get(job_id)
                if job is None or job.is_terminal:
                    return
                handler = self._handler_for(job.kind)
                if handler is None:
                    await repository.mark_failed(
                        job_id,
                        f"no handler is registered for kind '{job.kind}' in this process "
                        f"(known kinds: {', '.join(self.registered_kinds())})",
                    )
                    await session.commit()
                    return
                await repository.mark_running(job_id, worker_id=self.worker_id)
                kind = job.kind
                payload = dict(job.payload or {})
                user_id = job.user_id
                await session.commit()

            context = HandlerContext(
                job_id=job_id,
                kind=kind,
                payload=payload,
                user_id=user_id,
                report=lambda stage, progress: self._report(job_id, stage, progress),
                is_cancelled=lambda: self._is_cancelled(job_id),
            )

            try:
                result = await handler(context)
            except asyncio.CancelledError:
                async with self._session_factory() as session:
                    await TaskRepository(session).mark_cancelled(
                        job_id, detail="cancelled while running"
                    )
                    await session.commit()
                return
            except Exception as exc:
                _logger.error(
                    "job_failed",
                    exc_info=exc,
                    extra={
                        "event": "job_failed",
                        "task_id": str(job_id),
                        "kind": kind,
                        "detail": f"{type(exc).__name__}: {exc}",
                    },
                )
                async with self._session_factory() as session:
                    await TaskRepository(session).mark_failed(
                        job_id, f"{type(exc).__name__}: {exc}"
                    )
                    await session.commit()
                return
            finally:
                self._tasks.pop(job_id, None)

            async with self._session_factory() as session:
                await TaskRepository(session).mark_succeeded(
                    job_id, dict(result) if result is not None else {}
                )
                await session.commit()

    async def _report(self, job_id: UUID, stage: str, progress: int) -> None:
        async with self._session_factory() as session:
            await TaskRepository(session).update_progress(job_id, stage=stage, progress=progress)
            await session.commit()

    async def _is_cancelled(self, job_id: UUID) -> bool:
        if job_id in self._cancelled:
            return True
        async with self._session_factory() as session:
            job = await TaskRepository(session).get(job_id)
            return bool(job and job.status == "cancelled")


class RedisQueue(_QueueBase):
    """Production queue stub (PHASE 15). Unreachable unless ``QUEUE_BACKEND=redis``.

    ``implemented = False`` is what lets :func:`build_queue_selection` detect that the
    configured backend cannot serve work in this build and downgrade explicitly
    (``GET /system/health`` publishes the reason). The constructor itself refuses to
    exist unless ``QUEUE_BACKEND=redis``, so nothing can route work here by accident.
    """

    backend_name = "redis"
    #: Flipped to ``True`` when the Redis-backed implementation lands (PHASE 15).
    implemented = False

    def __init__(self, settings: APISettings, *args: Any, **kwargs: Any) -> None:
        if settings.queue_backend != "redis":
            # Construction itself is a programming error when Redis is not selected.
            raise DependencyUnavailableError(
                f"RedisQueue requires QUEUE_BACKEND=redis (current: {settings.queue_backend})",
                details=[{"field": "QUEUE_BACKEND", "issue": "not_redis"}],
            )
        super().__init__(*args, **kwargs)
        self._settings = settings

    async def enqueue(self, **_kwargs: Any) -> BackgroundJob:
        raise DependencyUnavailableError(REDIS_UNAVAILABLE_MESSAGE)

    async def get(self, *_args: Any, **_kwargs: Any) -> BackgroundJob | None:
        raise DependencyUnavailableError(REDIS_UNAVAILABLE_MESSAGE)

    async def cancel(self, *_args: Any, **_kwargs: Any) -> BackgroundJob:
        raise DependencyUnavailableError(REDIS_UNAVAILABLE_MESSAGE)

    async def shutdown(self) -> None:  # pragma: no cover - nothing to shut down
        return None


@dataclass(slots=True)
class QueueSelection:
    """The queue plus an honest account of whether it is the configured one."""

    queue: QueuePort
    backend: str
    configured: str
    degradation_reason: str | None = None

    @property
    def degraded(self) -> bool:
        return self.degradation_reason is not None


def build_queue_selection(
    settings: APISettings,
    session_factory: async_sessionmaker[AsyncSession],
) -> QueueSelection:
    """Build the queue for ``settings.queue_backend``, falling back when it cannot run.

    ``QUEUE_BACKEND=redis`` with no Redis implementation in this build degrades to the
    in-process queue **and reports it**; with ``ALLOW_QUEUE_FALLBACK=false`` the stub is
    returned instead, so the first task fails loudly rather than running somewhere the
    operator did not ask for.
    """
    configured = settings.queue_backend or "inprocess"
    if configured == "redis":
        redis_queue = RedisQueue(settings)
        if redis_queue.implemented:
            return QueueSelection(queue=redis_queue, backend="redis", configured=configured)
        if not settings.allow_queue_fallback:
            return QueueSelection(queue=redis_queue, backend="redis", configured=configured)
        _logger.warning(
            "queue_backend_fallback",
            extra={
                "event": "queue_backend_fallback",
                "backend": "inprocess",
                "detail": REDIS_UNAVAILABLE_MESSAGE,
            },
        )
        return QueueSelection(
            queue=InProcessQueue(session_factory, concurrency=settings.worker_concurrency),
            backend="inprocess",
            configured=configured,
            degradation_reason="redis_unavailable",
        )
    return QueueSelection(
        queue=InProcessQueue(session_factory, concurrency=settings.worker_concurrency),
        backend="inprocess",
        configured=configured,
    )


def build_queue(
    settings: APISettings,
    session_factory: async_sessionmaker[AsyncSession],
) -> QueuePort:
    """Just the queue, for callers that do not need the degradation report."""
    return build_queue_selection(settings, session_factory).queue
