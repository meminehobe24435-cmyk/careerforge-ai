"""Task models: ``GET /tasks/{id}`` and ``POST /tasks/{id}/cancel``.

``docs/API.md`` §1.4 fixes the polling payload as
``{status, progress, stage, result, error}``; those five keys are always present.
The extra fields (``taskId``, ``kind``, timestamps, attempts) are additive and exist
so the UI does not have to guess an id it already knows.

``TaskAccepted`` is the ``202`` body the long-task endpoints will return from PHASE 2
(``taskId`` / ``status`` / ``streamUrl``); it is here already because the queue —
not the routers — owns the ``tsk_…`` handle.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["TaskAccepted", "TaskCancelResponse", "TaskResponse", "TaskStatusValue"]

TaskStatusValue = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class TaskAccepted(_CamelModel):
    """``202 Accepted`` body (``docs/API.md`` §1.4)."""

    task_id: str = Field(alias="taskId")
    status: str
    stream_url: str | None = Field(default=None, alias="streamUrl")


class TaskResponse(_CamelModel):
    """``data`` of ``GET /tasks/{id}``."""

    task_id: str = Field(alias="taskId")
    kind: str
    status: str
    #: 0–100; mirrored by the SSE ``progress`` event.
    progress: int = 0
    #: Current human-readable stage (``parsing``, ``matching``, …).
    stage: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    attempts: int = 0
    max_attempts: int = Field(default=3, alias="maxAttempts")
    queued_at: datetime | None = Field(default=None, alias="queuedAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")


class TaskCancelResponse(TaskResponse):
    """``data`` of ``POST /tasks/{id}/cancel`` — the task plus whether it was stopped."""

    cancelled: bool = False
    detail: str | None = None
