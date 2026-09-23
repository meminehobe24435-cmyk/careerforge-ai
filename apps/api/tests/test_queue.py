"""The queue port: in-process execution, the Redis stub, and idempotency.

``docs/ARCHITECTURE.md`` §1.3 promises that swapping the queue backend does not change
the domain layer; ``docs/API.md`` §1.4 promises a 24-hour idempotency window. Both are
queue-level properties, so they are tested here rather than through an endpoint.
"""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from fastapi import FastAPI
import pytest
from sqlalchemy import func, select

from careerforge_api.core.config import APISettings
from careerforge_api.core.errors import DependencyUnavailableError, NotFoundError
from careerforge_api.db.session import create_engine, create_session_factory
from careerforge_api.models.job import BackgroundJob
from careerforge_api.repositories.task_repository import TaskRepository
from careerforge_api.workers.queue import (
    BUILTIN_JOB_KINDS,
    InProcessQueue,
    RedisQueue,
    build_queue_selection,
)
from tests.conftest import Session


def test_builtin_handlers_cover_the_registered_kinds(app: FastAPI) -> None:
    assert set(BUILTIN_JOB_KINDS) <= set(app.state.queue.registered_kinds())


async def test_enqueue_persists_the_row_before_running_it(app: FastAPI, demo: Session) -> None:
    queue = app.state.queue
    job = await queue.enqueue(
        kind="system.ping", payload={"n": 1}, user_id=UUID(demo.id), max_attempts=5
    )
    assert job.status == "queued"
    assert job.progress == 0
    assert job.attempts == 0
    assert job.max_attempts == 5
    assert job.queued_at is not None
    assert job.user_id == UUID(demo.id)

    for _ in range(100):
        await asyncio.sleep(0.02)
        async with app.state.session_factory() as session:
            current = await TaskRepository(session).get(job.id)
        if current is not None and current.is_terminal:
            break
    assert current is not None
    assert current.status == "succeeded"
    assert current.progress == 100
    assert current.result == {"pong": True, "payload": {"n": 1}}
    assert current.finished_at is not None


async def test_idempotency_key_returns_the_first_job(app: FastAPI, demo: Session) -> None:
    """``Idempotency-Key`` within 24h must not do the work twice (docs/API.md §1.4)."""
    queue = app.state.queue
    key = "idem-key-1"
    first = await queue.enqueue(kind="system.noop", user_id=UUID(demo.id), idempotency_key=key)
    second = await queue.enqueue(kind="system.noop", user_id=UUID(demo.id), idempotency_key=key)
    assert first.id == second.id

    async with app.state.session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(BackgroundJob)
            .where(BackgroundJob.idempotency_key == key)
        )
    assert count == 1


async def test_a_failing_handler_marks_the_row_failed(app: FastAPI, demo: Session) -> None:
    queue = app.state.queue

    async def explode(context) -> None:  # type: ignore[no-untyped-def]
        await context.report("about-to-fail", 30)
        raise ValueError("handler blew up")

    queue.register_handler("test.explode", explode)
    job = await queue.enqueue(kind="test.explode", user_id=UUID(demo.id))
    for _ in range(100):
        await asyncio.sleep(0.02)
        async with app.state.session_factory() as session:
            current = await TaskRepository(session).get(job.id)
        if current is not None and current.is_terminal:
            break
    assert current is not None
    assert current.status == "failed"
    assert "handler blew up" in (current.error or "")
    assert current.progress == 30  # the last reported stage is preserved


async def test_cancel_refuses_a_task_that_does_not_exist(app: FastAPI) -> None:
    with pytest.raises(NotFoundError):
        await app.state.queue.cancel(uuid4())


async def test_submit_existing_drives_a_row_queued_elsewhere(app: FastAPI, demo: Session) -> None:
    """The standalone worker claims rows it did not create (workers/main.py)."""
    async with app.state.session_factory() as session:
        job = await TaskRepository(session).create(
            kind="system.noop", payload={}, user_id=UUID(demo.id)
        )
        await session.commit()
        job_id = job.id

    queue = app.state.queue
    assert hasattr(queue, "submit_existing")
    task = queue.submit_existing(job_id)
    assert task is not None
    await task

    async with app.state.session_factory() as session:
        finished = await TaskRepository(session).get(job_id)
    assert finished is not None and finished.status == "succeeded"


def test_redis_queue_refuses_to_construct_without_the_redis_backend() -> None:
    with pytest.raises(DependencyUnavailableError) as error:
        RedisQueue(APISettings(use_sqlite=True, queue_backend="inprocess"))
    assert "QUEUE_BACKEND" in str(error.value)


async def test_redis_queue_reports_a_clear_unavailable_error() -> None:
    """QUEUE_BACKEND=redis is unreachable-by-default and says exactly why."""
    queue = RedisQueue(APISettings(use_sqlite=False, queue_backend="redis"))
    with pytest.raises(DependencyUnavailableError) as error:
        await queue.enqueue(kind="system.noop")
    assert "not available in this environment" in str(error.value)
    assert queue.backend_name == "redis"


async def test_build_queue_selection_falls_back_and_reports_it(settings_factory) -> None:
    """A configured-but-unavailable backend degrades, and the downgrade is reportable."""
    settings: APISettings = settings_factory(queue_backend="redis")
    engine = create_engine(settings)
    try:
        selection = build_queue_selection(settings, create_session_factory(engine))
        assert selection.backend == "inprocess"
        assert selection.configured == "redis"
        assert selection.degraded is True
        assert selection.degradation_reason == "redis_unavailable"
    finally:
        await engine.dispose()


async def test_build_queue_selection_can_refuse_to_degrade() -> None:
    """With fallbacks disabled the operator gets the stub, not a silent substitution."""
    settings = APISettings(use_sqlite=True, queue_backend="redis", allow_queue_fallback=False)
    selection = build_queue_selection(settings, None)  # type: ignore[arg-type]
    assert selection.backend == "redis"
    assert selection.degraded is False
    assert isinstance(selection.queue, RedisQueue)
    # ... and using it fails with the documented, specific message.
    with pytest.raises(DependencyUnavailableError):
        await selection.queue.enqueue(kind="system.noop")


async def test_in_process_queue_respects_its_concurrency_limit(app: FastAPI, demo: Session) -> None:
    """``WORKER_CONCURRENCY`` bounds how many handlers run at once (ADR-010)."""
    settings: APISettings = app.state.settings
    assert settings.worker_concurrency >= 1

    queue: InProcessQueue = app.state.queue
    active = 0
    peak = 0

    async def tracked(context) -> None:  # type: ignore[no-untyped-def]
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.05)
        active -= 1

    queue.register_handler("test.tracked", tracked)
    # Rows are inserted directly so the test drives execution via submit_existing —
    # the same entry point the standalone worker uses.
    async with app.state.session_factory() as session:
        repository = TaskRepository(session)
        jobs = [await repository.create(kind="test.tracked") for _ in range(4)]
        await session.commit()
        job_ids = [job.id for job in jobs]

    tasks = [queue.submit_existing(job_id) for job_id in job_ids]
    await asyncio.gather(*[task for task in tasks if task is not None])
    assert 1 <= peak <= settings.worker_concurrency

    async with app.state.session_factory() as session:
        repository = TaskRepository(session)
        for job_id in job_ids:
            finished = await repository.get(job_id)
            assert finished is not None and finished.status == "succeeded"
