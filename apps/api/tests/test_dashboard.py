"""``GET /dashboard`` — the aggregate the home page renders.

This endpoint's contract was frozen in PHASE 0 as TypeScript in
``packages/shared/src/api/types.ts``, and the assertions here mirror it field for field. That
is the point of the test: the frontend validated the response before the endpoint existed, so
a shape mismatch would surface as a blank dashboard rather than an error.

The honesty properties matter as much as the shape: a metric with no data source must be
named rather than silently zeroed.
"""

from __future__ import annotations

import asyncio
import itertools

from fastapi import FastAPI
from httpx import AsyncClient
import pytest

from tests.conftest import EnvelopeCheck, Session, UserFactory

JD_TEXT = """某某科技有限公司
岗位：嵌入式软件工程师

任职要求：
1. 熟悉 STM32 与 FreeRTOS；
2. 熟悉 CAN 总线通信协议。
"""

RESUME = """教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 使用 STM32 与 FreeRTOS 开发电机控制固件，
负责 CAN 总线节点通信调试。
"""

_counter = itertools.count()


async def _evidence_ready(client: AsyncClient, session: Session) -> None:
    payload = f"{RESUME}\n<!-- fixture {next(_counter)} -->\n".encode()
    body = await client.post(
        "/api/v1/documents",
        files={"file": ("resume.txt", payload, "text/plain")},
        data={"kind": "resume"},
        headers=session.headers,
    )
    assert body.status_code == 202, body.text
    accepted = body.json()["data"]
    for _ in range(200):
        task = (
            await client.get(f"/api/v1/tasks/{accepted['taskId']}", headers=session.headers)
        ).json()["data"]
        if task["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.02)
    assert task["status"] == "succeeded", task
    response = await client.post(
        f"/api/v1/documents/{accepted['documentId']}/analyze", headers=session.headers
    )
    assert response.status_code == 200, response.text


async def test_dashboard_matches_the_frozen_client_shape(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """Field for field against ``DashboardResponse`` in packages/shared."""
    data = envelope(await client.get("/api/v1/dashboard", headers=demo.headers))["data"]

    assert set(data) == {
        "profileStrength",
        "stats",
        "skillsRadar",
        "recentJobs",
        "nextActions",
        "meta",
    }
    assert isinstance(data["profileStrength"]["score"], int | float)
    assert set(data["profileStrength"]) == {"score", "delta7d", "dimensions", "algorithmVersion"}
    stats = data["stats"]
    assert set(stats) == {
        "evidenceCoverage",
        "skillCoverage",
        "resumeMatch",
        "applications",
        "interviews",
        "offers",
    }
    for key, value in stats.items():
        assert isinstance(value, int | float), key
        assert value >= 0
    assert all(
        0.0 <= stats[key] <= 1.0 for key in ("evidenceCoverage", "skillCoverage", "resumeMatch")
    )
    assert isinstance(data["skillsRadar"], list)
    assert isinstance(data["recentJobs"], list)
    assert isinstance(data["nextActions"], list)


async def test_the_strength_breakdown_adds_up_to_the_strength_score(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """The headline number is checkable, not merely announced.

    The engine has always produced the five dimensions, their weights and their weighted
    contributions; this endpoint used to drop them and send the total alone, while the dashboard told
    the reader the breakdown would arrive later. A breakdown is only worth forwarding if it is the
    *same* arithmetic as the total, so this asserts the sum rather than the presence of five objects.

    The account is its own (`make_user`), not the shared demo one: `_evidence_ready` ingests material
    once, and doing that to the demo account makes `evidenceCoverage` read 1.0 before
    `test_numbers_come_from_stored_rows` can observe it rise — which is exactly how this test broke
    that one the first time it was written.
    """
    account = await make_user(display_name="Strength Breakdown")
    await _evidence_ready(client, account)

    response = await client.get("/api/v1/dashboard", headers=account.headers)
    assert response.status_code == 200, response.text
    strength = envelope(response)["data"]["profileStrength"]

    dimensions = strength["dimensions"]
    assert len(dimensions) == 5, "the engine scores five weighted dimensions"
    assert strength["algorithmVersion"], "a score without its algorithm version is unattributable"
    for dimension in dimensions:
        assert set(dimension) == {"key", "label", "raw", "weight", "weighted"}
        assert dimension["label"], f"{dimension['key']} must carry the engine's own label"
        assert 0.0 <= dimension["raw"] <= 1.0
        # weighted = raw * weight * 100, recomputed here on purpose: if the service ever starts
        # deriving the contributions separately from the total, this is where the two disagree.
        assert dimension["weighted"] == pytest.approx(
            dimension["raw"] * dimension["weight"] * 100, abs=0.01
        )
    assert sum(dimension["weighted"] for dimension in dimensions) == pytest.approx(
        strength["score"], abs=0.6
    )
    assert sum(dimension["weight"] for dimension in dimensions) == pytest.approx(1.0, abs=1e-6)
    # An account with evidence must actually score above zero, or the arithmetic above would hold
    # just as well on five zeros.
    assert strength["score"] > 0
    assert any(dimension["weighted"] > 0 for dimension in dimensions)


async def test_tracker_metrics_are_the_boards_real_counts(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """PHASE 8 replaced three zeros with counts, so they must be *checked* counts.

    The definition shipped beside the numbers claims a specific arithmetic — every
    non-archived card for ``applications``, ``interview``+``final``+``offer`` for
    ``interviews`` — and this asserts the arithmetic rather than the presence of a key.
    """
    account = await make_user(display_name="Tracker Metrics")

    async def track(company: str, status: str) -> str:
        created = await client.post(
            "/api/v1/applications",
            json={"company": company, "role": "嵌入式软件工程师", "status": status},
            headers=account.headers,
        )
        assert created.status_code == 201, created.text
        return created.json()["data"]["id"]

    async def move(application_id: str, status: str) -> None:
        moved = await client.patch(
            f"/api/v1/applications/{application_id}",
            json={"status": status},
            headers=account.headers,
        )
        assert moved.status_code == 200, moved.text

    await track("A", "wishlist")
    interviewed = await track("B", "wishlist")
    await move(interviewed, "applied")
    await move(interviewed, "interview")
    offering = await track("C", "wishlist")
    await move(offering, "applied")
    await move(offering, "final")
    await move(offering, "offer")
    rejected = await track("D", "wishlist")
    await move(rejected, "applied")
    await move(rejected, "rejected")

    data = envelope(await client.get("/api/v1/dashboard", headers=account.headers))["data"]
    assert data["stats"]["applications"] == 4.0
    # interview + final + offer = 2. The rejected card was interviewed-then-rejected and is
    # deliberately not counted: this is the board's snapshot, not the ever-reached funnel.
    assert data["stats"]["interviews"] == 2.0
    assert data["stats"]["offers"] == 1.0

    # Archiving removes a card from every metric, which is what archiving is for.
    archived = await client.patch(
        f"/api/v1/applications/{await track('E', 'wishlist')}",
        json={"archived": True},
        headers=account.headers,
    )
    assert archived.status_code == 200, archived.text
    after = envelope(await client.get("/api/v1/dashboard", headers=account.headers))["data"]
    assert after["stats"]["applications"] == 4.0


async def test_every_reported_metric_carries_its_definition(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """A number without its definition is a number nobody can check.

    The tracker metrics used to be named in ``meta.unavailable`` because no data source
    existed; since PHASE 8 they are real, so the assertion is now that nothing is
    *withheld* and every metric is still *explained*.
    """
    data = envelope(await client.get("/api/v1/dashboard", headers=demo.headers))["data"]
    assert data["meta"]["unavailable"] == {}
    assert set(data["meta"]["definitions"]) >= set(data["stats"])
    # The snapshot-vs-funnel distinction is the one a reader would otherwise get wrong.
    assert "看板快照" in data["meta"]["definitions"]["interviews"]


async def test_an_empty_account_gets_zeros_and_a_first_action(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """A brand-new account must render, with a next step rather than an empty screen."""
    account = await make_user(display_name="Fresh Candidate")
    data = envelope(await client.get("/api/v1/dashboard", headers=account.headers))["data"]

    assert data["stats"]["evidenceCoverage"] == 0.0
    assert data["stats"]["resumeMatch"] == 0.0
    assert data["profileStrength"]["score"] >= 0
    assert data["recentJobs"] == []
    assert data["nextActions"], "a new account must be told what to do first"
    assert any(action["type"] == "upload" for action in data["nextActions"])


async def test_numbers_come_from_stored_rows(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    """Uploading and matching must move the metrics — checked by observing the change."""
    before = envelope(await client.get("/api/v1/dashboard", headers=demo.headers))["data"]

    await _evidence_ready(client, demo)
    middle = envelope(await client.get("/api/v1/dashboard", headers=demo.headers))["data"]
    assert middle["stats"]["evidenceCoverage"] > before["stats"]["evidenceCoverage"]
    assert middle["skillsRadar"], "evidence yielding skills must fill the radar"

    response = await client.post(
        "/api/v1/jobs/analyze",
        json={"text": f"{JD_TEXT}\n<!-- fixture {next(_counter)} -->"},
        headers=demo.headers,
    )
    job = envelope(response)["data"]
    matched = await client.post(f"/api/v1/jobs/{job['id']}/match", headers=demo.headers)
    assert matched.status_code == 200, matched.text

    after = envelope(await client.get("/api/v1/dashboard", headers=demo.headers))["data"]
    assert after["stats"]["resumeMatch"] > 0.0
    assert after["stats"]["skillCoverage"] > 0.0
    assert after["recentJobs"]
    assert after["recentJobs"][0]["matchScore"] > 0.0
    # The strength score is computed by the scoring engine, not invented here.
    assert after["profileStrength"]["score"] >= middle["profileStrength"]["score"]


async def test_dashboard_requires_authentication(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_dashboard_is_scoped_to_the_caller(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session, make_user: UserFactory
) -> None:
    """One user's jobs and evidence must never appear in another's dashboard."""
    await _evidence_ready(client, demo)
    response = await client.post(
        "/api/v1/jobs/analyze",
        json={"text": f"{JD_TEXT}\n<!-- fixture {next(_counter)} -->"},
        headers=demo.headers,
    )
    job = envelope(response)["data"]

    other = await make_user(display_name="Other Candidate")
    data = envelope(await client.get("/api/v1/dashboard", headers=other.headers))["data"]
    assert data["recentJobs"] == []
    assert all(item["jobId"] != job["id"] for item in data["recentJobs"])
    assert data["stats"]["evidenceCoverage"] == 0.0
