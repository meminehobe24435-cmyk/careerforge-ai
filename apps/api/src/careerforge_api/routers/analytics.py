"""``/analytics/*`` — the funnel, the rates, the correlation, the categories, the timeline.

Everything here is arithmetic over the candidate's own rows (``docs/API.md`` §2.11, PRD FR-14),
and every response carries its own window and sample policy in ``meta``. That last part is not
decoration: the same endpoint answers differently for a 7-day and a 90-day cohort, and a number
whose window is implicit is a number that will be read as being about something else.

The five endpoints share one implementation and one cohort read (``AnalyticsService.snapshot``),
so the funnel and the correlation table on one page cannot describe two different sets of
applications.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from careerforge_ai.analytics import MIN_SAMPLE
from careerforge_ai.schemas.analytics import FunnelCohort
from careerforge_api.deps import CurrentUser, DbSession
from careerforge_api.schemas.analytics import (
    AnalyticsMeta,
    CategoryPerformanceResponse,
    FunnelResponse,
    FunnelStageResponse,
    RateCardResponse,
    RatesResponse,
    SkillCorrelationResponse,
    TimelineBucketResponse,
    TimelineEntryResponse,
    TimelineResponse,
)
from careerforge_api.services.analytics_service import AnalyticsService

__all__ = ["router"]

router = APIRouter(prefix="/analytics", tags=["analytics"])

#: Documented in one place so the OpenAPI schema and the UI agree on what may be asked for.
_RANGE = Query(default="30d", alias="range", pattern="^(7d|30d|90d|all)$")

_WINDOW_NOTE = (
    "range 过滤的是**投递的创建时间**（同期群）：分母与分子来自同一批投递。"
    "想看「本周发生了什么」请用 /analytics/timeline，它按事件发生时间过滤。"
)


def _meta(
    cohort: FunnelCohort, *, basis: str = "applications", notes: list[str] | None = None
) -> AnalyticsMeta:
    return AnalyticsMeta(
        range=cohort.range,
        from_at=cohort.from_at,
        to_at=cohort.to_at,
        cohort_size=cohort.applications,
        minimum_sample=MIN_SAMPLE,
        window_basis=basis,
        notes=notes or [],
    )


@router.get("/funnel", summary="Applications → Replies → Interviews → Finals → Offers")
async def get_funnel(
    session: DbSession,
    user: CurrentUser,
    range_key: str = _RANGE,
) -> FunnelResponse:
    """Counted from ``application_events``, so a card that reached an interview and was later
    rejected is still an interview. The board's snapshot and this funnel differ on purpose."""
    cohort, stages = await AnalyticsService(session).funnel(user=user, range_key=range_key)
    return FunnelResponse(
        meta=_meta(cohort, notes=[_WINDOW_NOTE]),
        stages=[
            FunnelStageResponse(
                key=stage.key,
                label=stage.label,
                count=stage.count,
                share_of_first=stage.share_of_first,
                step_rate=stage.step_rate,
                basis=stage.basis,
            )
            for stage in stages
        ],
    )


@router.get("/rates", summary="Response / Interview / Offer rate and average match score")
async def get_rates(
    session: DbSession,
    user: CurrentUser,
    range_key: str = _RANGE,
) -> RatesResponse:
    """Each card ships its numerator, denominator, 95% interval and ``sufficient`` flag."""
    cohort, cards = await AnalyticsService(session).rates(user=user, range_key=range_key)
    return RatesResponse(
        meta=_meta(
            cohort,
            notes=[
                _WINDOW_NOTE,
                f"分母小于 {MIN_SAMPLE} 时 sufficient=false，界面显示「样本不足，仅供参考」。",
            ],
        ),
        cards=[
            RateCardResponse(
                key=card.key,
                label=card.label,
                rate=card.rate,
                numerator=card.numerator,
                denominator=card.denominator,
                sufficient=card.sufficient,
                interval_low=card.interval_low,
                interval_high=card.interval_high,
                definition=card.definition,
            )
            for card in cards
        ],
    )


@router.get("/skill-correlation", summary="Which skills the interviews actually happened with")
async def get_skill_correlation(
    session: DbSession,
    user: CurrentUser,
    range_key: str = _RANGE,
) -> list[SkillCorrelationResponse]:
    """Both groups are reported, and a difference is only ``notable`` when each side clears the
    sample minimum and their 95% intervals do not overlap. Correlation is not causation, and
    the note says so in the payload rather than in a footnote."""
    rows = await AnalyticsService(session).skill_correlation(user=user, range_key=range_key)
    return [
        SkillCorrelationResponse(
            skill_id=row.skill_id,
            display_name=row.display_name,
            with_skill_total=row.with_skill_total,
            with_skill_successes=row.with_skill_successes,
            with_skill_rate=row.with_skill_rate,
            without_skill_total=row.without_skill_total,
            without_skill_successes=row.without_skill_successes,
            without_skill_rate=row.without_skill_rate,
            lift=row.lift,
            sufficient=row.sufficient,
            notable=row.notable,
            note=row.note,
        )
        for row in rows
    ]


@router.get("/categories", summary="Performance by role family")
async def get_categories(
    session: DbSession,
    user: CurrentUser,
    range_key: str = _RANGE,
) -> list[CategoryPerformanceResponse]:
    """A category comes from the posting's required skills and the skill taxonomy, never from a
    label a model typed. Unclassifiable cards are reported as ``unknown``."""
    rows = await AnalyticsService(session).categories(user=user, range_key=range_key)
    return [
        CategoryPerformanceResponse(
            category=row.category,
            applications=row.applications,
            interviews=row.interviews,
            offers=row.offers,
            interview_rate=row.interview_rate,
            average_match_score=row.average_match_score,
            sufficient=row.sufficient,
        )
        for row in rows
    ]


@router.get("/timeline", summary="Milestones and the monthly trend")
async def get_timeline(
    session: DbSession,
    user: CurrentUser,
    range_key: str = Query(default="all", alias="range", pattern="^(7d|30d|90d|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
) -> TimelineResponse:
    """Filtered by when each milestone happened — the one endpoint where the window means events
    rather than the cohort, because a milestone reached today belongs in today's view."""
    entries, buckets = await AnalyticsService(session).timeline(
        user=user, range_key=range_key, limit=limit
    )
    return TimelineResponse(
        meta=AnalyticsMeta(
            range=range_key,
            from_at=None,
            to_at=None,
            cohort_size=len(entries),
            minimum_sample=MIN_SAMPLE,
            window_basis="events",
            notes=[
                "range 过滤的是**事件发生时间**（本周做了什么），与 /analytics/funnel 的同期群口径不同。",
                "空月份会保留为 0：跳过一个没有活动的月份，趋势图会把三个月的空窗压缩成零距离。",
            ],
        ),
        entries=[
            TimelineEntryResponse(
                kind=entry.kind,
                title=entry.title,
                occurred_at=entry.occurred_at,
                status=entry.status,
                ref_id=entry.ref_id,
            )
            for entry in entries
        ],
        buckets=[
            TimelineBucketResponse(
                month=bucket.month,
                applications=bucket.applications,
                interviews=bucket.interviews,
                offers=bucket.offers,
            )
            for bucket in buckets
        ],
    )
