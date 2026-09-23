"""Standalone worker entrypoint: ``python -m careerforge_api.workers.main``.

``docker-compose.yml`` runs the ``worker`` service with exactly that command, so
this module is the seam between the API image and the queue port. It polls
``background_jobs`` for ``queued`` rows and executes them through the same
:class:`~careerforge_api.workers.queue.InProcessQueue` that the API uses, which
means the ``queued → running → succeeded/failed`` transitions are produced by one
implementation rather than two.

Two honest notes:

* On the zero-dependency path (``USE_SQLITE=true``) the API already runs its tasks
  in-process; this entrypoint exists for the Docker topology, where the API and the
  worker are separate containers sharing PostgreSQL.
* With ``QUEUE_BACKEND=redis`` the process exits with a clear
  ``DEPENDENCY_UNAVAILABLE`` message instead of silently doing nothing — the Redis
  queue arrives in PHASE 15.

The loop is deliberately simple: claim, run, repeat, with a bounded in-flight count.
Nothing here parses or scores anything — that belongs to the AI core.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
from types import FrameType

from careerforge_api.core.config import APISettings, get_api_settings
from careerforge_api.core.errors import DependencyUnavailableError
from careerforge_api.core.logging import configure_logging, get_logger
from careerforge_api.db.session import create_all, create_engine, create_session_factory
from careerforge_api.repositories.task_repository import TaskRepository
from careerforge_api.workers.handlers import register_default_handlers
from careerforge_api.workers.queue import (
    InProcessQueue,
    QueuePort,
    build_queue,
)

__all__ = ["WorkerRuntime", "main", "run"]

_logger = get_logger("careerforge_api.workers")

#: How long to sleep when there is nothing queued (seconds).
POLL_INTERVAL_SECONDS = 1.0


class WorkerRuntime:
    """Owns the engine, the queue and the poll loop."""

    def __init__(self, settings: APISettings) -> None:
        self.settings = settings
        self.queue: QueuePort | None = None
        self._stop = asyncio.Event()
        self._in_flight: set[asyncio.Task[None]] = set()

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        engine = create_engine(self.settings)
        if self.settings.use_sqlite:
            # The local path has no migration step; PostgreSQL relies on
            # `alembic upgrade head` (the compose `migrate` service).
            await create_all(engine)
        self._engine = engine
        self._session_factory = create_session_factory(engine)
        self.queue = build_queue(self.settings, self._session_factory)
        # Without this the worker would claim jobs it has no handler for and fail them
        # with "no handler is registered for kind …" — the API process registers the same
        # set, so the two entrypoints cannot disagree about what this build can run.
        register_default_handlers(self.queue, self._session_factory)
        _logger.info(
            "worker_started",
            extra={
                "event": "worker_started",
                "backend": self.queue.backend_name,
                "kind": "worker",
            },
        )

    async def stop(self) -> None:
        self._stop.set()

    def request_stop(self) -> None:
        self._stop.set()

    async def shutdown(self) -> None:
        if self.queue is not None:
            await self.queue.shutdown()
        await self._engine.dispose()

    # ── loop ─────────────────────────────────────────────────────────────────

    async def run(self) -> int:
        assert self.queue is not None, "start() must run first"
        if not isinstance(self.queue, InProcessQueue):
            # RedisQueue (or any future shared queue) is not a DB poller: refuse
            # loudly rather than spinning on an empty loop.
            raise DependencyUnavailableError(
                f"the standalone worker cannot drive a '{self.queue.backend_name}' queue yet"
            )

        concurrency = max(1, self.settings.worker_concurrency)
        while not self._stop.is_set():
            self._in_flight = {task for task in self._in_flight if not task.done()}
            slots = concurrency - len(self._in_flight)
            if slots <= 0:
                await self._wait_for_slot()
                continue

            async with self._session_factory() as session:
                queued = await TaskRepository(session).next_queued(limit=slots)

            if not queued:
                await self._sleep_or_stop()
                continue

            for job in queued:
                task = self.queue.submit_existing(job.id)
                if task is not None:
                    self._in_flight.add(task)

        if self._in_flight:
            with contextlib.suppress(Exception):
                await asyncio.gather(*self._in_flight, return_exceptions=True)
        _logger.info("worker_stopped", extra={"event": "worker_stopped"})
        return 0

    async def _sleep_or_stop(self) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=POLL_INTERVAL_SECONDS)

    async def _wait_for_slot(self) -> None:
        # A finished task frees a slot; waking up on the next tick is enough here.
        await asyncio.sleep(0.05)


def _install_signal_handlers(runtime: WorkerRuntime) -> None:
    """SIGTERM/SIGINT → graceful stop.

    ``loop.add_signal_handler`` is unavailable on Windows, where the ``signal``
    module fallback is used instead; either way a container restart stops the worker
    between tasks rather than mid-write.
    """

    def _handler(_signum: int, _frame: FrameType | None = None) -> None:
        runtime.request_stop()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, runtime.request_stop)
        except (NotImplementedError, RuntimeError):
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, _handler)


async def main(settings: APISettings | None = None) -> int:
    """Run the worker until SIGINT/SIGTERM."""
    resolved = settings or get_api_settings()
    configure_logging(resolved)
    runtime = WorkerRuntime(resolved)
    _install_signal_handlers(runtime)
    await runtime.start()
    try:
        return await runtime.run()
    finally:
        await runtime.shutdown()


def run() -> int:
    """Synchronous entrypoint used by ``python -m`` and the container."""
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:  # pragma: no cover - interactive Ctrl-C
        return 0


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    sys.exit(run())
