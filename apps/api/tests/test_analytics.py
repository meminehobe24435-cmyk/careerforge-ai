"""``/analytics/*`` — the funnel must agree with the rows it claims to summarise.

The phase's exit criterion is exact: *the funnel numbers match the ``applications`` /
``application_events`` data*. So the central test here does not assert a hard-coded number —
it builds a board through the real HTTP API, reads the same rows back from the database, counts
them by hand, and requires the endpoint to agree. A funnel that drifts from the event log is
worse than no funnel, because it is the page a candidate would use to decide what to do next.

The other two criteria are asserted directly: ``n < 5`` marks a rate insufficient, and the range
parameter changes what is included.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from careerforge_api.models.application import Application, ApplicationEvent
from careerforge_api.models.user import User
from careerforge_api.services.analytics_service import AnalyticsService
from tests.conftest import Session, UserFactory

JD_TEXT = """智远科技
嵌入式软件工程师
工作地点：苏州

任职要求：
1. 熟悉 STM32 与 FreeRTOS；
2. 熟悉 CAN 总线通信协议。
"""


async def _track(
    client: AsyncClient, session: Session, company: str, status: str = "wishlist"
) -> str:
    response = await client.post(
        "/api/v1/applications",
        json={"company": company, "role": "嵌入式软件工程师", "status": status},
        headers=session.headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


async def _move(client: AsyncClient, session: Session, application_id: str, status: str) -> None:
    response = await client.patch(
        f"/api/v1/applications/{application_id}",
        json={"status": status},
        headers=session.headers,
    )
    assert response.status_code == 200, response.text


async def _funnel(client: AsyncClient, session: Session, range_key: str = "all") -> dict:
    response = await client.get(
        f"/api/v1/analytics/funnel?range={range_key}", headers=session.headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _stages(client: AsyncClient, session: Session, range_key: str = "all") -> dict[str, dict]:
    data = await _funnel(client, session, range_key)
    return {stage["key"]: stage for stage in data["stages"]}


# ── the exit criterion: the funnel matches the rows ───────────────────────────


async def test_the_funnel_equals_a_hand_count_of_the_stored_rows(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """Built through HTTP, counted from the database, compared stage by stage."""
    account = await make_user(display_name="Analytics")

    # wishlist only → not an application
    await _track(client, account, "只看不投")
    # applied → no reply
    plain = await _track(client, account, "被无视的")
    await _move(client, account, plain, "applied")
    # applied → interview → rejected: on the board this is rejected, in the funnel it is an
    # interview. This is the card that makes the distinction observable.
    rejected = await _track(client, account, "面完被拒的")
    await _move(client, account, rejected, "applied")
    await _move(client, account, rejected, "interview")
    await _move(client, account, rejected, "rejected")
    # applied → interview → final → offer
    offered = await _track(client, account, "拿到 offer 的")
    await _move(client, account, offered, "applied")
    await _move(client, account, offered, "interview")
    await _move(client, account, offered, "final")
    await _move(client, account, offered, "offer")
    # applied → oa → rejected: a reply, no interview
    oa = await _track(client, account, "笔试后挂的")
    await _move(client, account, oa, "applied")
    await _move(client, account, oa, "oa")
    await _move(client, account, oa, "rejected")

    async with app.state.session_factory() as db:
        rows = (
            await db.execute(
                select(Application.id, Application.status).where(Application.user_id == account.id)
            )
        ).all()
        events = (
            await db.execute(
                select(ApplicationEvent.application_id, ApplicationEvent.to_status).where(
                    ApplicationEvent.user_id == account.id
                )
            )
        ).all()

    # The hand count, from the database only.
    seen: dict[str, set[str]] = {}
    for application_id, to_status in events:
        seen.setdefault(str(application_id), set()).add(to_status)
    boards = [set() for _ in rows]
    for index, (application_id, _status) in enumerate(rows):
        boards[index] = seen.get(str(application_id), set())

    applied = [states for states in boards if states - {"wishlist"}]
    expected = {
        "applications": len(applied),
        "replies": sum(
            1 for s in applied if s & {"oa", "interview", "final", "offer"} or "rejected" in s
        ),
        "interviews": sum(1 for s in applied if s & {"interview", "final", "offer"}),
        "finals": sum(1 for s in applied if s & {"final", "offer"}),
        "offers": sum(1 for s in applied if "offer" in s),
    }
    assert expected == {
        "applications": 4,
        "replies": 3,
        "interviews": 2,
        "finals": 1,
        "offers": 1,
    }, "the fixture itself drifted; fix the fixture before blaming the endpoint"

    stages = await _stages(client, account)
    assert {key: stage["count"] for key, stage in stages.items()} == expected

    # A rejected-after-interview card is counted as interviewed, which is the whole point.
    assert stages["interviews"]["count"] == 2


async def test_the_funnel_reports_its_own_window_and_basis(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    await _track(client, account, "甲")
    data = await _funnel(client, account, "30d")
    meta = data["meta"]
    assert meta["range"] == "30d"
    assert meta["cohortSize"] == 1
    assert meta["minimumSample"] == 5
    assert meta["fromAt"] is not None and meta["toAt"] is not None
    assert meta["notes"], "the window's meaning travels with the numbers"
    for stage in data["stages"]:
        assert stage["basis"], f"{stage['key']} does not say how it was counted"


async def test_a_stage_with_an_empty_predecessor_reports_no_step_rate(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """0 offers out of 0 finals is not a 100% conversion, and the field says so."""
    account = await make_user()
    card = await _track(client, account, "只是投了")
    await _move(client, account, card, "applied")
    stages = await _stages(client, account)

    assert stages["applications"]["stepRate"] == 1.0
    assert stages["replies"]["stepRate"] == 0.0
    assert stages["offers"]["stepRate"] is None
    assert stages["offers"]["count"] == 0


# ── the rates ─────────────────────────────────────────────────────────────────


async def test_rates_carry_counts_intervals_and_the_sample_verdict(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    for index in range(4):
        card = await _track(client, account, f"公司{index}")
        await _move(client, account, card, "applied")
    interview = await _track(client, account, "面了的")
    await _move(client, account, interview, "applied")
    await _move(client, account, interview, "interview")

    response = await client.get("/api/v1/analytics/rates?range=all", headers=account.headers)
    assert response.status_code == 200, response.text
    cards = {card["key"]: card for card in response.json()["data"]["cards"]}

    interview_card = cards["interviewRate"]
    assert interview_card["numerator"] == 1
    assert interview_card["denominator"] == 5
    assert interview_card["rate"] == 0.2
    assert interview_card["sufficient"] is True, "five is the documented minimum"
    assert interview_card["intervalLow"] < 0.2 < interview_card["intervalHigh"]
    assert "分母" in interview_card["definition"]

    # Four applications would have been insufficient; five is the boundary, so assert it too.
    assert cards["offerRate"]["denominator"] == 5
    assert cards["offerRate"]["sufficient"] is True
    assert cards["cohortSize"]["rate"] is None, "a cohort size is a count, not a ratio"


async def test_a_brand_new_account_gets_no_rate_rather_than_zero_percent(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """An empty account must not be told it has a 0% interview rate — it has no rate at all."""
    account = await make_user()
    response = await client.get("/api/v1/analytics/rates?range=30d", headers=account.headers)
    cards = {card["key"]: card for card in response.json()["data"]["cards"]}

    assert cards["interviewRate"]["rate"] is None
    assert cards["interviewRate"]["denominator"] == 0
    assert cards["interviewRate"]["sufficient"] is False
    assert cards["averageMatchScore"]["rate"] is None


async def test_an_unknown_range_is_refused(client: AsyncClient, make_user: UserFactory) -> None:
    account = await make_user()
    response = await client.get("/api/v1/analytics/funnel?range=1y", headers=account.headers)
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


# ── the range ─────────────────────────────────────────────────────────────────


async def test_the_range_selects_the_cohort(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """Cards created outside the window are excluded — checked by moving a card's creation date
    back in the database rather than by waiting."""
    account = await make_user()
    recent = await _track(client, account, "最近的")
    old = await _track(client, account, "很久以前的")
    for card in (recent, old):
        await _move(client, account, card, "applied")
    await _move(client, account, old, "interview")

    async with app.state.session_factory() as db:
        row = await db.get(Application, old)
        assert row is not None
        row.created_at = datetime.now(UTC) - timedelta(days=100)
        await db.commit()

    week = await _stages(client, account, "7d")
    assert week["applications"]["count"] == 1, "only the recent card is in the 7-day cohort"
    assert week["interviews"]["count"] == 0, "the old card's interview is outside the cohort"

    quarter = await _stages(client, account, "90d")
    assert quarter["interviews"]["count"] == 0, "100 days is outside a 90-day cohort"

    everything = await _stages(client, account, "all")
    assert everything["applications"]["count"] == 2
    assert everything["interviews"]["count"] == 1, "the interview is still visible in 'all'"


# ── the categories and the correlation ────────────────────────────────────────


async def test_categories_come_from_the_postings_skills(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    analyzed = await client.post(
        "/api/v1/jobs/analyze", json={"text": JD_TEXT}, headers=account.headers
    )
    assert analyzed.status_code == 200, analyzed.text
    job_id = analyzed.json()["data"]["id"]
    tracked = await client.post(f"/api/v1/jobs/{job_id}/applications", headers=account.headers)
    assert tracked.status_code == 201, tracked.text
    await _move(client, account, tracked.json()["data"]["id"], "applied")

    response = await client.get("/api/v1/analytics/categories?range=all", headers=account.headers)
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert rows, "the tracked posting must produce a category row"
    assert rows[0]["applications"] == 1
    assert rows[0]["category"] != "unknown", "STM32/FreeRTOS is embedded, per the taxonomy"
    assert rows[0]["sufficient"] is False, "one application is not a category trend"


async def test_a_manual_card_is_reported_as_unknown_rather_than_dropped(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    card = await _track(client, account, "内推机会")
    await _move(client, account, card, "applied")

    response = await client.get("/api/v1/analytics/categories?range=all", headers=account.headers)
    rows = response.json()["data"]
    assert [row["category"] for row in rows] == ["unknown"]


async def test_the_correlation_needs_both_groups_and_says_so(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """With one application there is nothing to correlate, and the endpoint returns an empty
    list rather than a table of meaningless 100%s."""
    account = await make_user()
    card = await _track(client, account, "唯一的")
    await _move(client, account, card, "applied")

    response = await client.get(
        "/api/v1/analytics/skill-correlation?range=all", headers=account.headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


# ── the timeline ──────────────────────────────────────────────────────────────


async def test_the_timeline_lists_milestones_and_fills_idle_months(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    card = await _track(client, account, "会拿 offer 的")
    for status in ("applied", "interview", "offer"):
        await _move(client, account, card, status)

    response = await client.get("/api/v1/analytics/timeline?range=all", headers=account.headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    kinds = [entry["kind"] for entry in data["entries"]]
    assert kinds[:3] == ["offer", "interview", "application"], "newest first"
    assert data["meta"]["windowBasis"] == "events"
    assert data["meta"]["notes"], "the different window basis is stated, not implied"

    months = data["buckets"]
    assert len(months) >= 3, "the trend covers at least the default span"
    assert months[-1]["applications"] == 1 and months[-1]["interviews"] == 1
    assert any(bucket["applications"] == 0 for bucket in months), "idle months are kept"


# ── tenancy ───────────────────────────────────────────────────────────────────


async def test_analytics_never_crosses_accounts(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Two accounts with very different histories must not see each other's numbers."""
    busy = await make_user(display_name="Busy")
    quiet = await make_user(display_name="Quiet")
    for index in range(3):
        card = await _track(client, busy, f"忙碌公司{index}")
        await _move(client, busy, card, "applied")
        await _move(client, busy, card, "interview")

    busy_stages = await _stages(client, busy)
    quiet_stages = await _stages(client, quiet)
    assert busy_stages["applications"]["count"] == 3
    assert busy_stages["interviews"]["count"] == 3
    assert quiet_stages["applications"]["count"] == 0
    assert quiet_stages["interviews"]["count"] == 0


# ── archived cards ────────────────────────────────────────────────────────────


async def test_archiving_removes_a_card_from_the_funnel(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Archiving means "stop showing me this", and the funnel is a view of the same data."""
    account = await make_user()
    card = await _track(client, account, "归档的")
    await _move(client, account, card, "applied")
    assert (await _stages(client, account))["applications"]["count"] == 1

    archived = await client.patch(
        f"/api/v1/applications/{card}", json={"archived": True}, headers=account.headers
    )
    assert archived.status_code == 200, archived.text
    assert (await _stages(client, account))["applications"]["count"] == 0


async def test_deleting_a_card_removes_its_events_too(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    account = await make_user()
    card = await _track(client, account, "要删掉的")
    await _move(client, account, card, "applied")
    assert (
        await client.delete(f"/api/v1/applications/{card}", headers=account.headers)
    ).status_code == 204

    assert (await _stages(client, account))["applications"]["count"] == 0
    async with app.state.session_factory() as db:
        remaining = await db.scalar(
            select(func.count())
            .select_from(ApplicationEvent)
            .where(
                ApplicationEvent.user_id == account.id,
                ApplicationEvent.to_status == "applied",
            )
        )
    assert remaining == 0


# ── the service's internal contract ───────────────────────────────────────────


async def test_one_snapshot_serves_every_endpoint(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """The funnel and the correlation table must describe the same applications."""
    account = await make_user()
    card = await _track(client, account, "同一个窗口")
    await _move(client, account, card, "applied")

    async with app.state.session_factory() as db:
        user = await db.get(User, account.id)
        assert user is not None
        snapshot = await AnalyticsService(db).snapshot(user=user, range_key="all")
    assert snapshot.cohort.applications == len(snapshot.records) == 1
    assert snapshot.range_key == "all"


async def test_analytics_requires_authentication(client: AsyncClient) -> None:
    for path in (
        "/api/v1/analytics/funnel",
        "/api/v1/analytics/rates",
        "/api/v1/analytics/skill-correlation",
        "/api/v1/analytics/categories",
        "/api/v1/analytics/timeline",
    ):
        assert (await client.get(path)).status_code == 401, path
