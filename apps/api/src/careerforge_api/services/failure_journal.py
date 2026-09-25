"""The failure journal: the reason a failed run still leaves a row.

The problem this solves
-----------------------
``DatabaseRunTracker`` writes ``agent_runs`` inside the request's own transaction, and ``get_db``
rolls that transaction back on any exception. So a 400 or a 500 from an AI endpoint used to leave
**no trace at all**: the run the executor had carefully recorded — status ``failed``, the step that
died, the error code — vanished with the rollback. PHASE 12 measured it (a run count that did not
move across a failed request) and recorded the contradiction with ``executor.py``'s comment that
"observability is never lost".

How it is fixed, and what was rejected
--------------------------------------
A failed run is written through a **separate short-lived session, after the request's transaction
has finished**. Three approaches were considered:

1. ``session.begin_nested()`` + an explicit commit on the failure path — *rejected*. A SAVEPOINT is
   still part of the enclosing transaction, so the rollback that ``get_db`` performs after the
   handler raises discards it too. It looks like a durable write and is not one.
2. Writing from a second session **while the request's transaction is open** — *rejected*. SQLite
   has a single writer, and PHASE 2 already paid for this lesson: a second connection writing
   mid-transaction produced "database is locked". A failed request must not also become a flaky one.
3. **This module**: the tracker hands the failed record to a journal, and the journal is flushed by
   middleware *after* the response (or the exception) has passed through ``get_db`` — i.e. after the
   transaction is committed or rolled back. One extra session per failed request, opened when the
   request has already released its write lock.

The trade-off, stated plainly: a failure's row is written outside the request transaction, so it
does not carry the request's other uncommitted changes — it carries the run record, which is
self-contained by construction. A crash between the failure and the flush loses the record, and the
risk window is one middleware frame wide rather than the whole response. Nothing about the success
path changes: same rows, same ids, same transaction.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from careerforge_ai.schemas.common import AgentRunStatus, UsageStatus
from careerforge_ai.schemas.observability import AgentRunRecord, LLMUsage
from careerforge_api.core.logging import get_logger
from careerforge_api.models.observability import AgentRun
from careerforge_api.services.error_report import sanitize_error_text

__all__ = ["FailureJournal", "apply_record_to_row", "row_exists", "usage_columns"]

logger = get_logger("careerforge_api.failures")

#: Statuses that must survive a rollback. A ``degraded`` or ``succeeded`` run commits with the
#: request and needs no journal entry — the journal exists only for the runs whose transaction is
#: about to be thrown away.
JOURNALED_STATUSES: frozenset[AgentRunStatus] = frozenset({AgentRunStatus.FAILED})


def usage_columns(usage: LLMUsage | None) -> dict[str, Any]:
    """The count columns for an envelope, or all-``NULL`` when there is no usage object at all.

    One function so the run row, the call rows and the journal's own insert cannot disagree. A
    missing envelope means no model call was made (no steps), and that stores ``NULL`` too: "we
    never asked" and "we asked and were not told" both differ from a measured zero, and the status
    column names which it was so a reader can still tell them apart from the row.
    """
    if usage is None:
        return {
            "usage_status": UsageStatus.UNAVAILABLE.value,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "cached_tokens": None,
            "cost_usd": None,
            "cost_cny": None,
        }
    return usage.projection()


def apply_record_to_row(row: AgentRun, record: AgentRunRecord) -> None:
    """Copy a finished :class:`AgentRunRecord` onto its row.

    Shared by the tracker's normal path and by the journal, because a failure persisted differently
    from a success is a failure described in a different vocabulary — and the whole point is that an
    operator can read both the same way.
    """
    row.status = record.status.value if hasattr(record.status, "value") else str(record.status)
    row.steps = [step.model_dump(mode="json") for step in record.steps]
    row.input_ref = dict(record.input_ref)
    row.output_ref = dict(record.output_ref)
    # ``record.usage`` is ``None`` only when no step carried an envelope; ``usage_columns`` names
    # that state in the status column instead of leaving the counts ambiguous.
    columns = usage_columns(record.usage)
    row.prompt_tokens = columns["prompt_tokens"]
    row.completion_tokens = columns["completion_tokens"]
    row.total_tokens = columns["total_tokens"]
    row.cached_tokens = columns["cached_tokens"]
    row.cost_usd = columns["cost_usd"]
    row.cost_cny = columns["cost_cny"]
    row.usage_status = columns["usage_status"]
    row.latency_ms = record.latency_ms
    row.cache_hit = record.cache_hits > 0
    row.prompt_version = record.prompt_version
    row.provider = record.provider or row.provider
    row.model = record.model or row.model
    row.request_id = record.request_id or row.request_id
    # The error is sanitised here rather than at the raise site: this is the last place before the
    # text becomes a row, so no future caller can bypass it by forgetting.
    row.error = sanitize_error_text(record.error_message)
    row.error_code = record.error_code
    row.finished_at = record.finished_at


def new_row(record: AgentRunRecord, run_id: UUID) -> AgentRun:
    """A fresh ``agent_runs`` row for a run the request transaction never committed."""
    return AgentRun(
        id=run_id,
        user_id=record.user_id,
        workflow=record.workflow,
        agent=record.agent,
        status=record.status.value if hasattr(record.status, "value") else str(record.status),
        trigger=record.trigger
        if record.trigger in {"api", "job", "manual", "seed", "eval"}
        else "api",
        steps=[],
        input_ref={},
        output_ref={},
        provider=record.provider,
        model=record.model,
        request_id=record.request_id,
        started_at=record.started_at,
        parent_run_id=record.parent_run_id,
    )


async def row_exists(session: AsyncSession, run_id: UUID) -> AgentRun | None:
    return await session.get(AgentRun, run_id)


class FailureJournal:
    """Holds runs whose transaction is about to be rolled back, until it is safe to write them.

    Lives on ``app.state`` because it spans the request and the middleware frame after it. The
    buffer is in-process: a failure recorded by one worker is flushed by that worker, which is the
    same lifetime guarantee the rest of the run tracing has.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._session_factory = session_factory
        self._pending: list[tuple[UUID, AgentRunRecord]] = []
        self._lock = asyncio.Lock()
        #: Counters for the API/health surfaces: how many failures were recorded, and how many of
        #: those could not be written. A silent zero here would hide a broken journal.
        self.recorded = 0
        self.persisted = 0
        self.failed = 0

    def bind(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Attach the factory the flush needs. Called once at startup."""
        self._session_factory = session_factory

    @property
    def pending(self) -> int:
        return len(self._pending)

    def record(self, run_id: UUID, record: AgentRunRecord) -> None:
        """Journal a run that a rollback is about to erase."""
        self.recorded += 1
        self._pending.append((run_id, record))

    async def flush(self) -> int:
        """Write every pending failure. Idempotent, and safe to call when there is nothing to do.

        Idempotent because the request transaction *may* have committed the row after all (the
        failure can be raised on a path where the handler still returns). In that case the row is
        already final and this is a no-op — so calling flush twice can never double-write, and the
        success path's rows keep the ids the request transaction gave them.
        """
        if self._session_factory is None or not self._pending:
            return 0
        async with self._lock:
            pending, self._pending = self._pending, []
        written = 0
        for run_id, record in pending:
            try:
                if await self._persist(run_id, record):
                    written += 1
            except Exception as exc:  # pragma: no cover - a broken journal must not break a request
                self.failed += 1
                # ``extra=`` rather than bare keywords: the repo's logger takes structured fields
                # this way, and passing them as kwargs is what the type checker rejects.
                logger.warning(
                    "failure_journal_write_failed",
                    extra={
                        "event": "failure_journal_write_failed",
                        "run_id": str(run_id),
                        "detail": f"{type(exc).__name__}: {exc}",
                    },
                )
        self.persisted += written
        return written

    async def _persist(self, run_id: UUID, record: AgentRunRecord) -> bool:
        if self._session_factory is None:
            return False
        async with self._session_factory() as session:
            row = await row_exists(session, run_id)
            if row is not None and row.status not in {"running"}:
                # Already written by the request's own transaction: nothing to repair.
                return False
            if row is None:
                row = new_row(record, run_id)
                session.add(row)
            apply_record_to_row(row, record)
            await session.commit()
            return True
