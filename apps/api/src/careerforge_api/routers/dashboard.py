"""``GET /dashboard`` — the home page in one request (``docs/API.md`` §2.10).

Synchronous and uncached, which is a deliberate deviation from the documented "含缓存":
every number here is derived from rows that a user can change seconds earlier (upload a
résumé, run a match), and a cached dashboard that disagrees with the page you just came from
is worse than a query that takes 30 ms. The cache belongs on the expensive aggregations
(``/analytics/*``), which is where the plan puts it.
"""

from __future__ import annotations

import time

from fastapi import APIRouter

from careerforge_api.deps import CurrentUser, DbSession
from careerforge_api.schemas.dashboard import (
    DashboardMeta,
    DashboardNextAction,
    DashboardProfileStrength,
    DashboardRecentJob,
    DashboardResponse,
    DashboardStats,
    SkillRadarPoint,
)
from careerforge_api.services.dashboard_service import DashboardService

__all__ = ["router"]

router = APIRouter(tags=["analytics"])


@router.get("/dashboard", summary="Aggregated home page")
async def get_dashboard(session: DbSession, user: CurrentUser) -> DashboardResponse:
    started = time.perf_counter()
    payload = await DashboardService(session).build(user=user)
    took_ms = int((time.perf_counter() - started) * 1000)

    return DashboardResponse(
        profile_strength=DashboardProfileStrength(**payload.profile_strength),
        stats=DashboardStats(**payload.stats),
        skills_radar=[SkillRadarPoint(**point) for point in payload.skills_radar],
        recent_jobs=[DashboardRecentJob(**job) for job in payload.recent_jobs],
        next_actions=[DashboardNextAction(**action) for action in payload.next_actions],
        meta=DashboardMeta(
            cache_hit=False,
            took_ms=took_ms,
            unavailable=payload.unavailable,
            definitions=payload.definitions,
        ),
    )
