"""Aggregate reads for the analytics page.

Separate from :class:`~careerforge_api.repositories.application_repository.ApplicationRepository`
on purpose: the tracker's queries are about *one* card (its events, its position), while these
are whole-cohort aggregates over four tables. Keeping them apart means neither repository grows
a reason to change that belongs to the other.

Every query is tenant-scoped and **batched**: one statement per table, grouped in Python. The
alternative — a query per application for its events — is the classic analytics N+1, and it
gets slower exactly as a candidate becomes more interesting to look at.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.models.application import Application, ApplicationEvent, CareerEvent
from careerforge_api.models.job_posting import JobSkill

__all__ = ["AnalyticsRepository"]


class AnalyticsRepository:
    """Read-only aggregates: applications, their status history, requirements, the timeline."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def applications_for_user(self, *, user_id: UUID) -> Sequence[Application]:
        """Every non-archived card.

        No date filter here, deliberately: the cohort window is applied by the engine, which also
        has to *describe* the window it applied (``FunnelCohort.from_at``). Filtering in SQL and
        again in Python would mean two places deciding what "30d ago" means.

        Archived cards are excluded: archiving means "stop showing me this", and a funnel that
        keeps counting what the user put away is a funnel they cannot reconcile with their board.
        """
        statement = select(Application).where(
            Application.user_id == user_id, Application.archived_at.is_(None)
        )
        return (await self._session.scalars(statement)).all()

    async def status_history(self, *, user_id: UUID) -> Sequence[tuple[UUID, str | None, str]]:
        """``(application_id, from_status, to_status)`` for every event — the funnel's source.

        Read whole rather than filtered by date: a card's *history* is what the funnel counts,
        and the window applies to when the card was created (see ``analytics/funnel.py``).
        """
        statement = select(
            ApplicationEvent.application_id,
            ApplicationEvent.from_status,
            ApplicationEvent.to_status,
        ).where(ApplicationEvent.user_id == user_id)
        return [(row[0], row[1], row[2]) for row in (await self._session.execute(statement)).all()]

    async def job_requirements(
        self, *, user_id: UUID
    ) -> Sequence[tuple[UUID, str | None, str, float]]:
        """``(job_id, canonical_id, requirement, weight)`` for every stored requirement."""
        statement = select(
            JobSkill.job_id,
            JobSkill.canonical_id,
            JobSkill.requirement,
            JobSkill.weight,
        ).where(JobSkill.user_id == user_id)
        return [
            (row[0], row[1], row[2], float(row[3]))
            for row in (await self._session.execute(statement)).all()
        ]

    async def career_events(self, *, user_id: UUID, limit: int = 500) -> Sequence[CareerEvent]:
        """The milestone feed, newest first."""
        statement = (
            select(CareerEvent)
            .where(CareerEvent.user_id == user_id)
            .order_by(CareerEvent.occurred_at.desc())
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()
