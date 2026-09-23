"""``background_jobs`` — the task table behind ``/tasks/*`` (``docs/DATABASE.md`` §2.11).

``docs/ARCHITECTURE.md`` §8.3 requires long operations to return ``202`` with a job
id and to report staged progress. This table is the durable half of that promise:
the in-process queue executes the work, but the state always lives in a row, so
``GET /tasks/{id}`` answers identically whether the worker is in this process or in
a separate container, and a crashed process leaves a ``running`` row behind rather
than losing the task silently.

``unique(idempotency_key)`` implements the 24-hour replay rule of §1.4: the same
``Idempotency-Key`` returns the first job instead of doing the work twice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType, TimestampType, UUIDType

__all__ = ["BACKGROUND_JOB_TERMINAL_STATUSES", "BACKGROUND_JOB_STATUSES", "BackgroundJob"]

BACKGROUND_JOB_STATUSES: tuple[str, ...] = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
)

#: Statuses after which no further transition is allowed.
BACKGROUND_JOB_TERMINAL_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})

_STATUS_LIST = ", ".join(f"'{status}'" for status in BACKGROUND_JOB_STATUSES)


class BackgroundJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One asynchronous task."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_LIST})", name="status_valid"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
        CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        UniqueConstraint("idempotency_key", name="uq_background_jobs_idempotency_key"),
        Index("ix_background_jobs_status_queued_at", "status", "queued_at"),
    )

    #: Nullable for system jobs that belong to no tenant.
    user_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    #: Task type, e.g. ``profile.import`` / ``github.analyze`` (PHASE 2+).
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="queued")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    #: 0–100, mirrored into the SSE ``progress`` event (``docs/API.md`` §1.5).
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Human-readable current stage (``parsing``, ``embedding``, …).
    stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)

    @property
    def is_terminal(self) -> bool:
        return self.status in BACKGROUND_JOB_TERMINAL_STATUSES
