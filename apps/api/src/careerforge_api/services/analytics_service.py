"""Career analytics: the API's half of the funnel.

The arithmetic lives in ``careerforge_ai.analytics`` (pure, framework-free, unit-tested at its
boundaries); this module's only jobs are to fetch the rows, turn them into the engine's
:class:`~careerforge_ai.analytics.funnel.ApplicationRecord` shape, and hand back the result.
That split is what makes the funnel testable against hand-built cohorts *and* against the
database, without two implementations of the same counting rules.

Three mapping decisions carry the honesty of the page:

* **``statuses_seen`` comes from the event log**, not from ``applications.status``. The board
  shows where a card is; the funnel counts how far it got, and a rejected-after-interview card
  is in both "rejected" and "interviewed" depending on which question you ask.
* **A required skill set is required + preferred**, because a posting that asks for something as
  a preference still influenced whether the candidate applied and still came up in the interview.
* **A category is derived, not typed**: the taxonomy category of the posting's heaviest required
  skill. If a posting's skills never resolved, the card is ``unknown`` rather than guessed at.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.analytics import (
    RANGE_DAYS,
    ApplicationRecord,
    build_funnel,
    category_performance,
    cohort_window,
    compute_rates,
    monthly_buckets,
    recent_entries,
    skill_correlation,
)
from careerforge_ai.parsing.skill_taxonomy import SKILL_BY_ID
from careerforge_ai.schemas.analytics import (
    CategoryPerformance,
    FunnelCohort,
    FunnelStage,
    RateCard,
    SkillCorrelation,
    TimelineBucket,
    TimelineEntry,
)
from careerforge_api.core.errors import ValidationError
from careerforge_api.db.compat import utcnow
from careerforge_api.models.application import Application
from careerforge_api.models.user import User
from careerforge_api.repositories.analytics_repository import AnalyticsRepository

__all__ = ["AnalyticsService", "AnalyticsSnapshot"]


class AnalyticsSnapshot:
    """Everything one request needs, fetched once.

    The three endpoints below share one cohort, so they share one read. Rebuilding it per
    endpoint would triple the queries and — worse — let the funnel and the correlation table
    disagree if a row changed between the two calls.
    """

    __slots__ = ("cohort", "range_key", "records", "timeline")

    def __init__(
        self,
        *,
        range_key: str,
        cohort: FunnelCohort,
        records: list[ApplicationRecord],
        timeline: list[TimelineEntry],
    ) -> None:
        self.range_key = range_key
        self.cohort = cohort
        self.records = records
        self.timeline = timeline


class AnalyticsService:
    """Deterministic analytics for one candidate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AnalyticsRepository(session)

    # ── the shared cohort ────────────────────────────────────────────────────

    async def snapshot(
        self, *, user: User, range_key: str = "30d", now: datetime | None = None
    ) -> AnalyticsSnapshot:
        """Build the cohort once, for every analytics endpoint."""
        if range_key not in RANGE_DAYS:
            raise ValidationError(
                f"unknown range '{range_key}'",
                details=[
                    {
                        "field": "range",
                        "issue": "not_allowed",
                        "message": f"allowed: {', '.join(RANGE_DAYS)}",
                    }
                ],
            )
        moment = now or utcnow()
        applications = await self._repo.applications_for_user(user_id=user.id)
        history = await self._repo.status_history(user_id=user.id)
        requirements = await self._repo.job_requirements(user_id=user.id)

        statuses: dict[UUID, set[str]] = defaultdict(set)
        for application_id, from_status, to_status in history:
            if from_status:
                statuses[application_id].add(from_status)
            statuses[application_id].add(to_status)

        required_by_job: dict[UUID, list[tuple[str | None, str, float]]] = defaultdict(list)
        for job_id, canonical_id, requirement, weight in requirements:
            required_by_job[job_id].append((canonical_id, requirement, weight))

        records = [
            self._to_record(
                application,
                statuses=statuses.get(application.id, set()),
                requirements=required_by_job.get(application.job_id or _NEVER, []),
            )
            for application in applications
        ]

        cohort, selected = cohort_window(range_key=range_key, now=moment, records=records)
        timeline = [
            TimelineEntry(
                kind=event.kind,
                title=event.title,
                occurred_at=event.occurred_at,
                status=str(event.event_metadata.get("status") or "") or None,
                ref_id=str(event.ref_id) if event.ref_id else None,
            )
            for event in await self._repo.career_events(user_id=user.id)
        ]
        return AnalyticsSnapshot(
            range_key=range_key, cohort=cohort, records=selected, timeline=timeline
        )

    @staticmethod
    def _to_record(
        application: Application,
        *,
        statuses: set[str],
        requirements: list[tuple[str | None, str, float]],
    ) -> ApplicationRecord:
        """Map one row to the engine's vocabulary, deriving the category from the taxonomy."""
        skills = tuple(canonical for canonical, _requirement, _weight in requirements if canonical)
        return ApplicationRecord(
            id=str(application.id),
            created_at=application.created_at,
            statuses_seen=frozenset(statuses),
            match_score=(
                float(application.match_score_snapshot)
                if application.match_score_snapshot is not None
                else None
            ),
            job_id=str(application.job_id) if application.job_id else None,
            required_skills=skills,
            category=_dominant_category(requirements),
        )

    # ── the endpoints ────────────────────────────────────────────────────────

    async def funnel(
        self, *, user: User, range_key: str = "30d", now: datetime | None = None
    ) -> tuple[FunnelCohort, list[FunnelStage]]:
        snapshot = await self.snapshot(user=user, range_key=range_key, now=now)
        return snapshot.cohort, build_funnel(snapshot.records)

    async def rates(
        self, *, user: User, range_key: str = "30d", now: datetime | None = None
    ) -> tuple[FunnelCohort, list[RateCard]]:
        snapshot = await self.snapshot(user=user, range_key=range_key, now=now)
        return snapshot.cohort, compute_rates(snapshot.records, cohort=snapshot.cohort)

    async def skill_correlation(
        self, *, user: User, range_key: str = "30d", now: datetime | None = None
    ) -> list[SkillCorrelation]:
        snapshot = await self.snapshot(user=user, range_key=range_key, now=now)
        return skill_correlation(snapshot.records, display_names=_display_names())

    async def categories(
        self, *, user: User, range_key: str = "30d", now: datetime | None = None
    ) -> list[CategoryPerformance]:
        snapshot = await self.snapshot(user=user, range_key=range_key, now=now)
        return category_performance(snapshot.records)

    async def timeline(
        self,
        *,
        user: User,
        range_key: str = "all",
        now: datetime | None = None,
        limit: int = 50,
        months: int = 12,
    ) -> tuple[list[TimelineEntry], list[TimelineBucket]]:
        """The feed and the monthly trend.

        Its window filters **events**, not applications: a milestone reached this week belongs in
        this week's view even when the application it belongs to is three months old. The other
        four endpoints filter the cohort instead, and both choices are stated in the docs.
        """
        if range_key not in RANGE_DAYS:
            raise ValidationError(f"unknown range '{range_key}'")
        moment = now or utcnow()
        events = [
            TimelineEntry(
                kind=event.kind,
                title=event.title,
                occurred_at=event.occurred_at,
                status=str(event.event_metadata.get("status") or "") or None,
                ref_id=str(event.ref_id) if event.ref_id else None,
            )
            for event in await self._repo.career_events(user_id=user.id)
        ]
        return (
            recent_entries(events, range_key=range_key, now=moment, limit=limit),
            monthly_buckets(events, range_key=range_key, now=moment, months=months),
        )


#: A sentinel key so ``required_by_job.get(None)`` cannot match a real job.
_NEVER = UUID(int=0)


def _dominant_category(requirements: list[tuple[str | None, str, float]]) -> str | None:
    """The taxonomy category of the posting's heaviest required skills.

    Weighted rather than "first match": a posting that lists one required AI skill and four
    preferred embedded ones is an embedded role, and a category that says otherwise would send
    the candidate's analytics in the wrong direction. ``None`` when the taxonomy resolved
    nothing — reported as ``unknown`` instead of guessed.
    """
    # ``defaultdict(float)`` rather than a ``Counter``: the weights are fractional, and a Counter
    # is typed over ``int`` — mypy caught the assignment, which is the kind of thing that would
    # otherwise silently truncate every preferred-skill weight to 0.
    weights: dict[str, float] = defaultdict(float)
    for canonical, requirement, weight in requirements:
        if not canonical:
            continue
        skill = SKILL_BY_ID.get(canonical)
        if skill is None:
            continue
        # Required counts full, preferred counts for its own weight: a requirement the posting
        # insisted on is a stronger statement about the role than one it merely welcomed.
        scale = 1.0 if requirement == "required" else max(0.25, weight)
        weights[skill.category.value] += scale
    if not weights:
        return None
    return max(weights.items(), key=lambda item: (item[1], item[0]))[0]


def _display_names() -> dict[str, str]:
    """Canonical id → the name a human reads, for the correlation table."""
    return {identifier: skill.display_name for identifier, skill in SKILL_BY_ID.items()}
