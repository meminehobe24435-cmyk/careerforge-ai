"""Application repository: board rows, their event log and the career timeline.

Tenant rule as everywhere — every read takes ``user_id`` and no query is built without it.

Two behaviours worth naming here rather than in the service:

* :meth:`ApplicationRepository.compact_positions` renumbers a column densely after a
  write. Positions arrive from a drag-and-drop client, which is a hostile source of
  ordering data (duplicates, gaps, an entire column reordered in one gesture), so the
  server never trusts them as a sequence — it re-derives one.
* :meth:`ApplicationRepository.next_position` appends to the end of a column by reading
  the maximum, not the count: after a partial reorder a count would collide.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.models.application import (
    Application,
    ApplicationEvent,
    CareerEvent,
)

__all__ = ["ApplicationRepository"]


class ApplicationRepository:
    """Tenant-scoped reads and writes for §2.7 and §2.11."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── applications ─────────────────────────────────────────────────────────

    async def get(self, application_id: UUID, *, user_id: UUID) -> Application | None:
        statement = select(Application).where(
            Application.id == application_id, Application.user_id == user_id
        )
        return await self._session.scalar(statement)

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        status: str | None = None,
        include_archived: bool = False,
        limit: int = 200,
    ) -> Sequence[Application]:
        statement = select(Application).where(Application.user_id == user_id)
        if status is not None:
            statement = statement.where(Application.status == status)
        if not include_archived:
            statement = statement.where(Application.archived_at.is_(None))
        statement = statement.order_by(
            Application.status, Application.position, Application.created_at
        ).limit(limit)
        return (await self._session.scalars(statement)).all()

    async def count_by_status(self, *, user_id: UUID) -> dict[str, int]:
        """Non-archived cards per status. Zero-filled for every status, so a caller
        cannot mistake "no rows" for "column missing"."""
        statement = (
            select(Application.status, func.count())
            .where(Application.user_id == user_id, Application.archived_at.is_(None))
            .group_by(Application.status)
        )
        rows = (await self._session.execute(statement)).all()
        return {str(status): int(count) for status, count in rows}

    async def next_position(self, *, user_id: UUID, status: str) -> int:
        statement = select(func.max(Application.position)).where(
            Application.user_id == user_id, Application.status == status
        )
        current = await self._session.scalar(statement)
        return 0 if current is None else int(current) + 1

    def add(self, **fields: object) -> Application:
        row = Application(**fields)
        self._session.add(row)
        return row

    async def flush(self) -> None:
        await self._session.flush()

    async def compact_positions(self, *, user_id: UUID, status: str) -> None:
        """Renumber one column densely from zero, keeping the current order.

        Two statements rather than one: SQLite and PostgreSQL both reject a single
        ``UPDATE`` whose new values collide with existing rows under a unique index.
        There is no unique index on ``(user_id, status, position)`` today, but writing
        the version that survives one is cheaper than remembering to rewrite this later.
        """
        rows = list(await self.list_for_user(user_id=user_id, status=status, include_archived=True))
        for index, row in enumerate(rows):
            if row.position != index:
                await self._session.execute(
                    update(Application).where(Application.id == row.id).values(position=index)
                )
        await self._session.flush()

    async def delete(self, application: Application) -> None:
        """Hard delete; the event log cascades. Archiving is the reversible operation."""
        await self._session.delete(application)
        await self._session.flush()

    # ── events ───────────────────────────────────────────────────────────────

    def add_event(
        self,
        *,
        application: Application,
        from_status: str | None,
        to_status: str,
        note: str = "",
        occurred_at: datetime,
    ) -> ApplicationEvent:
        event = ApplicationEvent(
            application_id=application.id,
            user_id=application.user_id,
            from_status=from_status,
            to_status=to_status,
            note=note,
            occurred_at=occurred_at,
        )
        self._session.add(event)
        return event

    async def events_of(
        self, *, application_id: UUID, user_id: UUID, limit: int = 100
    ) -> Sequence[ApplicationEvent]:
        statement = (
            select(ApplicationEvent)
            .where(
                ApplicationEvent.application_id == application_id,
                ApplicationEvent.user_id == user_id,
            )
            .order_by(ApplicationEvent.occurred_at.desc())
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()

    async def count_events(self, *, user_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(ApplicationEvent)
            .where(ApplicationEvent.user_id == user_id)
        )
        return int(await self._session.scalar(statement) or 0)

    # ── career timeline ──────────────────────────────────────────────────────

    async def add_career_event(
        self,
        *,
        user_id: UUID,
        kind: str,
        ref_type: str,
        ref_id: UUID,
        title: str,
        occurred_at: datetime,
        dedupe_key: str,
        metadata: dict[str, object] | None = None,
    ) -> CareerEvent | None:
        """Append a milestone, or return ``None`` when it is already on the timeline.

        Idempotent by ``(user_id, dedupe_key)``: dragging a card back and forth must not
        append the same milestone repeatedly, and a timeline that inflates itself is not
        a timeline. Checked before inserting rather than by catching an integrity error,
        so the same code path works inside a caller's transaction on both backends.
        """
        existing = await self._session.scalar(
            select(CareerEvent.id).where(
                CareerEvent.user_id == user_id, CareerEvent.dedupe_key == dedupe_key
            )
        )
        if existing is not None:
            return None
        event = CareerEvent(
            user_id=user_id,
            kind=kind,
            ref_type=ref_type,
            ref_id=ref_id,
            title=title,
            occurred_at=occurred_at,
            event_metadata=dict(metadata or {}),
            dedupe_key=dedupe_key,
        )
        self._session.add(event)
        return event

    async def timeline(self, *, user_id: UUID, limit: int = 50) -> Sequence[CareerEvent]:
        statement = (
            select(CareerEvent)
            .where(CareerEvent.user_id == user_id)
            .order_by(CareerEvent.occurred_at.desc())
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()

    async def count_career_events(self, *, user_id: UUID) -> int:
        statement = (
            select(func.count()).select_from(CareerEvent).where(CareerEvent.user_id == user_id)
        )
        return int(await self._session.scalar(statement) or 0)


def group_by_status(
    rows: Iterable[Application], statuses: Sequence[str]
) -> dict[str, list[Application]]:
    """Bucket cards into columns, preserving each column's stored order."""
    columns: dict[str, list[Application]] = {status: [] for status in statuses}
    for row in rows:
        columns.setdefault(row.status, []).append(row)
    return columns
