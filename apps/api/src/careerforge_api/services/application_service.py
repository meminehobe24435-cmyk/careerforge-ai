"""The application tracker: board writes, the event log and the career timeline.

Every rule in this module is a decision about what the *history* means, so they are
stated once, here, rather than spread across the router:

* **A status change writes an event, always.** ``application_events`` is append-only and
  is the funnel's data source in PHASE 9. A board whose history depends on whether the
  client happened to send a note would be a board whose statistics cannot be trusted.
* **A status change to the same status writes nothing.** Dragging a card within its own
  column is a reorder, not a move, and an event log full of ``applied → applied`` rows
  makes the funnel read as though the candidate applied four times.
* **``applied_at`` is set when a card first leaves ``wishlist``**, and never cleared
  automatically. Rewinding a card to ``wishlist`` is a correction of the board, not a
  denial that the application happened; the timeline keeps the truth.
* **Closed statuses drop the next action.** ``offer`` and ``rejected`` mean nothing
  further is expected, so keeping a reminder on the card would ask the candidate to act
  on something that cannot happen.
* **No transition is forbidden.** The board is drag-and-drop, so a strict forward-only
  state machine would fight the user for no benefit: candidates mis-drag, get rejected
  after an interview and move a card back, and reopen a wishlist item months later.
  Instead of policing direction, the service records every move, which is what makes the
  history auditable after the fact.

The score snapshot and the company/role snapshot are copied from the posting at creation
and never updated afterwards — see ``models/application.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.core.errors import NotFoundError, ValidationError
from careerforge_api.db.compat import utcnow
from careerforge_api.models.application import (
    APPLICATION_MILESTONES,
    APPLICATION_STATUSES,
    CLOSED_STATUSES,
    Application,
    ApplicationEvent,
)
from careerforge_api.models.job_posting import Job
from careerforge_api.models.user import User
from careerforge_api.repositories.application_repository import ApplicationRepository
from careerforge_api.repositories.job_repository import JobRepository

__all__ = ["ApplicationBoard", "ApplicationService", "ApplicationStats"]


@dataclass(slots=True)
class ApplicationBoard:
    """Cards grouped into the seven documented columns."""

    columns: dict[str, list[Application]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    archived: int = 0

    @property
    def total(self) -> int:
        return sum(len(items) for items in self.columns.values())


@dataclass(frozen=True, slots=True)
class ApplicationStats:
    """The three numbers ``GET /dashboard`` reports from the tracker.

    ``interviews`` counts cards *currently* in an interview stage, including those that
    have since reached an offer — a candidate holding an offer has interviewed. It is a
    snapshot of the board, not the ever-reached funnel: an application that was
    interviewed and then rejected is not in this number, because the board no longer says
    it is. The funnel counts from the event log in PHASE 9 and the two are expected to
    differ, which is why both definitions are shipped with the numbers.
    """

    total: int
    interviews: int
    offers: int
    by_status: dict[str, int]


class ApplicationService:
    """Tenant-scoped board operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._apps = ApplicationRepository(session)
        self._jobs = JobRepository(session)

    # ── reads ────────────────────────────────────────────────────────────────

    async def get(self, application_id: UUID, *, user: User) -> Application | None:
        return await self._apps.get(application_id, user_id=user.id)

    async def require(self, application_id: UUID, *, user: User) -> Application:
        """The row, or ``404`` — never ``403``, so ids cannot be probed."""
        row = await self.get(application_id, user=user)
        if row is None:
            raise NotFoundError("Application not found")
        return row

    async def board(self, *, user: User, include_archived: bool = False) -> ApplicationBoard:
        rows = list(
            await self._apps.list_for_user(user_id=user.id, include_archived=include_archived)
        )
        columns: dict[str, list[Application]] = {status: [] for status in APPLICATION_STATUSES}
        archived = 0
        for row in rows:
            if row.is_archived:
                archived += 1
            columns.setdefault(row.status, []).append(row)
        counts = {status: len(columns[status]) for status in APPLICATION_STATUSES}
        return ApplicationBoard(columns=columns, counts=counts, archived=archived)

    async def list_for_user(
        self, *, user: User, status: str | None = None, include_archived: bool = False
    ) -> list[Application]:
        if status is not None and status not in APPLICATION_STATUSES:
            raise ValidationError(
                f"unknown status '{status}'",
                details=[
                    {
                        "field": "status",
                        "issue": "not_allowed",
                        "message": f"allowed: {', '.join(APPLICATION_STATUSES)}",
                    }
                ],
            )
        return list(
            await self._apps.list_for_user(
                user_id=user.id, status=status, include_archived=include_archived
            )
        )

    async def events_of(self, *, application: Application) -> list[ApplicationEvent]:
        return list(
            await self._apps.events_of(application_id=application.id, user_id=application.user_id)
        )

    async def stats(self, *, user: User) -> ApplicationStats:
        by_status = dict.fromkeys(APPLICATION_STATUSES, 0)
        by_status.update(await self._apps.count_by_status(user_id=user.id))
        interviews = sum(by_status[status] for status in ("interview", "final", "offer"))
        return ApplicationStats(
            total=sum(by_status.values()),
            interviews=interviews,
            offers=by_status["offer"],
            by_status=by_status,
        )

    # ── writes ───────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        user: User,
        job_id: UUID | None = None,
        company: str = "",
        role: str = "",
        location: str | None = None,
        status: str = "wishlist",
        salary_expectation: str | None = None,
        notes: str = "",
        next_action_at: datetime | None = None,
        resume_version_id: UUID | None = None,
        note: str = "",
    ) -> Application:
        """Add a card, snapshotting whatever it points at."""
        job = await self._require_job(job_id, user=user) if job_id else None
        if status not in APPLICATION_STATUSES:
            raise ValidationError(f"unknown status '{status}'")

        company_name = (company or (job.company_name_raw if job else "") or "").strip()
        resolved_role = (role or (job.role if job else "") or "").strip()
        if not company_name and not resolved_role:
            raise ValidationError(
                "provide either jobId or at least one of company/role",
                details=[{"field": "company", "issue": "missing"}],
            )

        now = utcnow()
        row = self._apps.add(
            user_id=user.id,
            job_id=job.id if job else None,
            resume_version_id=resume_version_id,
            company_name=company_name,
            role=resolved_role,
            location=(location if location is not None else (job.location if job else None)),
            status=status,
            match_score_snapshot=await self._score_snapshot(job, user=user),
            applied_at=None if status == "wishlist" else now,
            next_action_at=None if status in CLOSED_STATUSES else next_action_at,
            salary_expectation=salary_expectation,
            notes=notes,
            position=await self._apps.next_position(user_id=user.id, status=status),
        )
        await self._apps.flush()
        await self._record(
            row, from_status=None, to_status=status, note=note or "加入投递看板", occurred_at=now
        )
        await self._apps.flush()
        return row

    async def update(
        self,
        *,
        user: User,
        application: Application,
        fields: dict[str, object],
        note: str = "",
    ) -> Application:
        """Apply a partial update, writing an event only when the status actually moves."""
        now = utcnow()
        new_status = fields.get("status")
        status_changed = isinstance(new_status, str) and new_status != application.status
        if isinstance(new_status, str) and new_status not in APPLICATION_STATUSES:
            raise ValidationError(f"unknown status '{new_status}'")

        for key in ("company", "role", "location", "salary_expectation", "notes"):
            if key in fields and fields[key] is not None:
                value = fields[key]
                if key in {"company", "role"}:
                    setattr(application, "company_name" if key == "company" else "role", str(value))
                else:
                    setattr(application, key, value)

        if fields.get("resume_version_id") is not None:
            application.resume_version_id = _as_uuid(
                fields["resume_version_id"], what="Resume version"
            )
        if "next_action_at" in fields:
            application.next_action_at = _as_datetime(fields["next_action_at"])
        if fields.get("applied_at") is not None:
            application.applied_at = _as_datetime(fields["applied_at"])
        if "archived" in fields and fields["archived"] is not None:
            application.archived_at = now if fields["archived"] else None

        if status_changed:
            await self._move(application, str(new_status), note=note, now=now)
        elif "position" in fields and isinstance(fields["position"], int):
            await self._place(application, index=int(fields["position"]))
        await self._apps.flush()
        return application

    async def reorder(self, *, user: User, items: list[dict[str, object]]) -> list[Application]:
        """Apply drag-and-drop placements: change columns, then re-derive each order.

        Positions are re-derived server-side (see ``ApplicationRepository.compact_positions``)
        because the client is a hostile source of ordering data — duplicates and gaps are
        normal from a gesture that can be interrupted mid-flight.

        Status changes write events; a pure position change does not. That is the same
        distinction the board draws when it shows a card moving columns versus moving
        within one.
        """
        now = utcnow()
        touched: list[Application] = []
        columns: set[str] = set()
        for item in items:
            raw_id = item.get("id")
            status = item.get("status")
            if not isinstance(raw_id, str) or not isinstance(status, str):
                raise ValidationError("each item needs an id and a status")
            if status not in APPLICATION_STATUSES:
                raise ValidationError(f"unknown status '{status}'")
            application = await self.require(_as_uuid(raw_id, what="Application"), user=user)
            position = item.get("position")
            index = int(position) if isinstance(position, int) else 0

            if application.status != status:
                await self._move(application, status, note="", now=now)
            await self._place(application, index=index, status=status)
            columns.add(status)
            columns.add(application.status)
            touched.append(application)

        await self._apps.flush()
        for column in columns:
            await self._apps.compact_positions(user_id=user.id, status=column)
        return touched

    async def delete(self, *, application: Application) -> None:
        """Hard delete. Archiving is the reversible operation and keeps the history."""
        await self._apps.delete(application)

    # ── internals ────────────────────────────────────────────────────────────

    async def _move(
        self, application: Application, status: str, *, note: str, now: datetime
    ) -> None:
        previous = application.status
        application.status = status
        if previous == "wishlist" and application.applied_at is None and status != "wishlist":
            # The day the application actually left the wishlist is a fact worth keeping;
            # it is what the funnel's first stage is measured from.
            application.applied_at = now
        if status in CLOSED_STATUSES:
            application.next_action_at = None
        await self._apps.flush()
        await self._record(
            application, from_status=previous, to_status=status, note=note, occurred_at=now
        )
        await self._apps.flush()
        # A card that changes columns lands at the end of its new column: the gesture
        # that moved it said nothing about where in that column it belongs.
        await self._place(application, index=None, status=status)

    async def _place(
        self, application: Application, *, index: int | None, status: str | None = None
    ) -> None:
        """Put a card at ``index`` of a column, shifting the rest down. ``None`` appends.

        Done by rebuilding the column's order in memory and writing it back densely. A
        single ``UPDATE`` with arithmetic would need the whole column's old order anyway,
        and this version is correct for a multi-column move without special cases.
        """
        target = status or application.status
        siblings = [
            row
            for row in await self._apps.list_for_user(
                user_id=application.user_id, status=target, include_archived=True
            )
            if row.id != application.id
        ]
        order = list(siblings)
        landing = len(order) if index is None else min(index, len(order))
        order.insert(landing, application)
        application.status = target
        for position, row in enumerate(order):
            row.position = position
        await self._session.flush()

    async def _record(
        self,
        application: Application,
        *,
        from_status: str | None,
        to_status: str,
        note: str,
        occurred_at: datetime,
    ) -> None:
        """Write the audit row, and a timeline milestone when this is one."""
        self._apps.add_event(
            application=application,
            from_status=from_status,
            to_status=to_status,
            note=note,
            occurred_at=occurred_at,
        )
        kind = APPLICATION_MILESTONES.get(to_status, "")
        if not kind:
            return
        await self._apps.add_career_event(
            user_id=application.user_id,
            kind=kind,
            ref_type="application",
            ref_id=application.id,
            title=_milestone_title(kind, application),
            occurred_at=occurred_at,
            # One milestone per card per status: a card dragged back and forth records
            # "interviewed at X" once, which is what a timeline is for.
            dedupe_key=f"application:{application.id}:{to_status}",
            metadata={"status": to_status, "company": application.company_name},
        )

    async def _require_job(self, job_id: UUID, *, user: User) -> Job:
        job = await self._jobs.get(job_id, user_id=user.id)
        if job is None:
            raise NotFoundError("Job not found")
        return job

    async def _score_snapshot(self, job: Job | None, *, user: User) -> Decimal | None:
        """The stored match score at this moment, or ``None`` when none exists.

        ``None`` rather than ``0``: the board must not read "we never scored this" as
        "this job matches you zero percent".
        """
        if job is None:
            return None
        match = await self._jobs.latest_match(job_id=job.id, user_id=user.id)
        return None if match is None else Decimal(str(match.score))


def _milestone_title(kind: str, application: Application) -> str:
    where = application.company_name or "未命名公司"
    subject = application.role or "岗位"
    if kind == "offer":
        return f"获得 Offer：{where} · {subject}"
    if kind == "interview":
        return f"进入面试：{where} · {subject}"
    return f"投递：{where} · {subject}"


def _as_uuid(value: object, *, what: str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise NotFoundError(f"{what} not found") from exc


def _as_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    raise ValidationError("expected an ISO-8601 timestamp")
