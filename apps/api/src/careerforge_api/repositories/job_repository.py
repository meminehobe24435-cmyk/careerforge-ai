"""Job repository: postings, their skill rows and match history.

Tenant rule as everywhere. ``jobs`` de-duplicates on ``(user_id, description_sha256)``, so
pasting the same posting twice updates one row — and, importantly, keeps its match history
attached to one job rather than forking it.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.models.job_posting import Job, JobMatch, JobSkill

__all__ = ["JobRepository"]


class JobRepository:
    """Tenant-scoped reads and writes for ``jobs`` / ``job_skills`` / ``job_matches``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── jobs ─────────────────────────────────────────────────────────────────

    async def get(self, job_id: UUID, *, user_id: UUID) -> Job | None:
        statement = select(Job).where(Job.id == job_id, Job.user_id == user_id)
        return await self._session.scalar(statement)

    async def get_by_hash(self, digest: str, *, user_id: UUID) -> Job | None:
        statement = select(Job).where(Job.user_id == user_id, Job.description_sha256 == digest)
        return await self._session.scalar(statement)

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        role_contains: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Job]:
        statement = select(Job).where(Job.user_id == user_id)
        if role_contains:
            statement = statement.where(Job.role.ilike(f"%{role_contains}%"))
        statement = statement.order_by(Job.created_at.desc()).limit(limit).offset(offset)
        return (await self._session.scalars(statement)).all()

    async def count(self, *, user_id: UUID) -> int:
        statement = select(func.count()).select_from(Job).where(Job.user_id == user_id)
        return int(await self._session.scalar(statement) or 0)

    async def upsert(
        self,
        *,
        user_id: UUID,
        description_sha256: str,
        fields: dict[str, Any],
    ) -> tuple[Job, bool]:
        """Create or update the job identified by its description hash.

        Returns ``(job, created)``. An update refreshes the analysis and the normalised
        columns but keeps the row's identity, so a re-paste does not orphan its matches.
        """
        existing = await self.get_by_hash(description_sha256, user_id=user_id)
        if existing is None:
            job = Job(user_id=user_id, description_sha256=description_sha256, **fields)
            self._session.add(job)
            await self._session.flush()
            return job, True

        for key, value in fields.items():
            setattr(existing, key, value)
        await self._session.flush()
        return existing, False

    async def replace_skills(self, job: Job, rows: Iterable[dict[str, Any]]) -> int:
        """Replace the requirement rows atomically and return how many were written.

        Replaced rather than appended: a re-analysis that dropped a requirement would
        otherwise leave the withdrawn one in the tree, and the match engine reads them.

        The relationship is refreshed before returning. A freshly inserted parent has an
        unloaded ``skills`` collection, so reading it in the caller triggers a lazy load
        from synchronous code — which the async ORM refuses (``MissingGreenlet``).
        Refreshing here is what makes the rows this call just wrote visible to the caller.
        """
        await self._session.execute(delete(JobSkill).where(JobSkill.job_id == job.id))
        written = 0
        for row in rows:
            self._session.add(JobSkill(job_id=job.id, user_id=job.user_id, **row))
            written += 1
        await self._session.flush()
        await self._session.refresh(job, ["skills"])
        return written

    async def delete(self, job: Job) -> None:
        """Hard delete; skill rows and matches cascade."""
        await self._session.delete(job)
        await self._session.flush()

    # ── matches ──────────────────────────────────────────────────────────────

    async def add_match(self, **fields: Any) -> JobMatch:
        """Append a match. History is kept; the newest row is the current answer."""
        row = JobMatch(**fields)
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest_match(self, *, job_id: UUID, user_id: UUID) -> JobMatch | None:
        statement = (
            select(JobMatch)
            .where(JobMatch.job_id == job_id, JobMatch.user_id == user_id)
            .order_by(JobMatch.created_at.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def match_history(
        self, *, job_id: UUID, user_id: UUID, limit: int = 10
    ) -> Sequence[JobMatch]:
        statement = (
            select(JobMatch)
            .where(JobMatch.job_id == job_id, JobMatch.user_id == user_id)
            .order_by(JobMatch.created_at.desc())
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()

    async def count_matches(self, *, user_id: UUID) -> int:
        statement = select(func.count()).select_from(JobMatch).where(JobMatch.user_id == user_id)
        return int(await self._session.scalar(statement) or 0)
