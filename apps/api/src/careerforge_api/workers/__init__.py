"""Background execution: the queue port and the standalone worker entrypoint.

The API process enqueues through :class:`~careerforge_api.workers.queue.InProcessQueue`
on the zero-dependency path; the Docker topology runs
``python -m careerforge_api.workers.main`` as a separate service. Both drive the same
execution code, so the ``background_jobs`` state machine is implemented once.
"""

from __future__ import annotations

from careerforge_api.workers.queue import (
    BUILTIN_JOB_KINDS,
    HandlerContext,
    InProcessQueue,
    JobHandler,
    QueuePort,
    QueueSelection,
    RedisQueue,
    build_queue,
    build_queue_selection,
)

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
