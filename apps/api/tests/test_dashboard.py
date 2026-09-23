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


async def test_metrics_without_a_data_source_are_named_not_silently_zeroed(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """A zero on a dashboard reads as "you have none". The tracker has never seen one."""
    data = envelope(await client.get("/api/v1/dashboard", headers=demo.headers))["data"]
    unavailable = data["meta"]["unavailable"]
    assert set(unavailable) >= {"applications", "interviews", "offers"}
    assert all("PHASE" in phase for phase in unavailable.values())
    # Every metric the API reports carries the definition it was computed with.
    assert set(data["meta"]["definitions"]) >= set(data["stats"])


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
