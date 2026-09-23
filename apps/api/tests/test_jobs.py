"""``/jobs`` — JD analysis, the skill tree and explainable matching.

The path under test is the second half of the product: paste a posting, get its
requirements with the sentences that justify them, then see an explainable score against
the evidence already stored.

The assertions concentrate on the honesty properties — that every requirement quotes the
posting, that the five dimensions add up to the score, and that a match computed with no
evidence says so instead of quietly scoring the evidence dimension as zero.
"""

from __future__ import annotations

import asyncio
import itertools
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from careerforge_api.models.job_posting import JobMatch, JobSkill
from tests.conftest import EnvelopeCheck, Session, UserFactory

#: A realistic Chinese embedded JD. Company-blurb sentences are included on purpose: the
#: parser must not promote technology named in the blurb into a requirement.
JD_TEXT = """某某智能科技有限公司

公司简介：我们是一家专注于工业自动化与机器人控制的高科技企业，
团队使用 Kubernetes 与 TensorFlow 构建云端调度平台。

岗位：嵌入式软件工程师（中级）
工作地点：深圳
薪资：18k-30k
学历要求：本科及以上
经验要求：3 年以上嵌入式开发经验

岗位职责：
1. 负责电机控制固件的设计与开发；
2. 负责 CAN 总线节点通信与调试。

任职要求：
1. 精通 C 语言，熟悉 STM32 平台开发；
2. 熟悉 FreeRTOS 实时操作系统，理解任务调度与优先级；
3. 熟悉 CAN、SPI、I2C 等通信协议。

加分项：
1. 了解 AUTOSAR 规范；
2. 有 Linux 驱动开发经验。
"""

RESUME = """教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 2023.07-2023.12
使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试，
并完成 PID 参数整定使控制周期稳定在 1kHz。
"""

_counter = itertools.count()


async def _evidence_ready(client: AsyncClient, envelope: EnvelopeCheck, session: Session) -> None:
    """Upload, parse and analyse a résumé so the user has a graph to match against.

    The bytes differ on every call: the database is shared for the whole session and
    documents de-duplicate on their hash, so identical fixture text would make the second
    upload a no-op — with no task id to poll.
    """
    payload = f"{RESUME}\n<!-- fixture {next(_counter)} -->\n".encode()
    body = await client.post(
        "/api/v1/documents",
        files={"file": ("resume.txt", payload, "text/plain")},
        data={"kind": "resume"},
        headers=session.headers,
    )
    assert body.status_code == 202, body.text
    accepted = envelope(body)["data"]
    for _ in range(200):
        task = envelope(
            await client.get(f"/api/v1/tasks/{accepted['taskId']}", headers=session.headers)
        )["data"]
        if task["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.02)
    assert task["status"] == "succeeded", task

    analyzed = await client.post(
        f"/api/v1/documents/{accepted['documentId']}/analyze", headers=session.headers
    )
    assert analyzed.status_code == 200, analyzed.text


def _jd() -> str:
    """Posting text unique per call.

    Jobs de-duplicate on their description hash and the database is shared for the whole
    session, so two tests analysing "the same" posting would share one job row — and its
    match history. The one test that deliberately exercises de-duplication passes an
    explicit text to both calls instead.
    """
    return f"{JD_TEXT}\n<!-- fixture {next(_counter)} -->"


async def _analyze(
    client: AsyncClient, envelope: EnvelopeCheck, session: Session, text: str | None = None
) -> dict:
    response = await client.post(
        "/api/v1/jobs/analyze", json={"text": text or _jd()}, headers=session.headers
    )
    assert response.status_code == 200, response.text
    return envelope(response)["data"]


async def test_analyze_parses_a_posting_and_stores_its_requirements(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    job = await _analyze(client, envelope, demo)

    assert job["role"], "a posting with an explicit 岗位 must yield a role"
    assert job["parseConfidence"] > 0
    assert job["parseStatus"] in {"parsed", "heuristic_fallback"}
    assert job["requiredCount"] >= 3, job
    assert job["skills"]
    for skill in job["skills"]:
        # Every requirement quotes the posting: that is what makes it checkable.
        assert skill["jdEvidence"], skill
        assert skill["requirement"] in {"required", "preferred", "bonus"}

    # The analysis is returned as the parser produced it, so a correction can be audited.
    assert job["analysis"]["role"]

    listing = envelope(await client.get("/api/v1/jobs", headers=demo.headers))["data"]
    assert any(item["id"] == job["id"] for item in listing["items"])
    assert listing["total"] >= 1


async def test_pasting_the_same_posting_updates_one_job(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """A re-paste must not fork the match history onto a second card."""
    text = _jd()  # one explicit text, analysed twice
    first = await _analyze(client, envelope, demo, text=text)
    before = envelope(await client.get("/api/v1/jobs", headers=demo.headers))["data"]["total"]

    second = await _analyze(client, envelope, demo, text=text)
    assert second["id"] == first["id"]

    after = envelope(await client.get("/api/v1/jobs", headers=demo.headers))["data"]["total"]
    assert after == before


async def test_skill_tree_reports_three_levels_and_unmatched_requirements(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    job = await _analyze(client, envelope, demo)
    tree = envelope(await client.get(f"/api/v1/jobs/{job['id']}/skill-tree", headers=demo.headers))[
        "data"
    ]

    assert tree["jobId"] == job["id"]
    assert tree["required"], "the 任职要求 section must produce required skills"
    assert all(item["requirement"] == "required" for item in tree["required"])
    assert all(item["jdEvidence"] for item in tree["required"])
    # 加分项 is a separate level, not merged into required.
    assert all(item["requirement"] == "bonus" for item in tree["bonus"])
    assert tree["unmatchedCount"] >= 0

    canonical = {item["canonicalId"] for item in tree["required"]}
    assert {"stm32", "free_rtos", "c"} & canonical, canonical


async def test_match_scores_against_the_stored_evidence_graph(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    await _evidence_ready(client, envelope, demo)
    job = await _analyze(client, envelope, demo)

    response = await client.post(f"/api/v1/jobs/{job['id']}/match", headers=demo.headers)
    assert response.status_code == 200, response.text
    match = envelope(response)["data"]

    assert 0.0 <= match["score"] <= 100.0
    assert set(match["dimensions"]) == {
        "skill",
        "experience",
        "project",
        "education",
        "evidence",
    }
    # The displayed arithmetic must add up: weight × score, summed, is the score.
    total = sum(item["weighted"] for item in match["dimensions"].values())
    assert abs(total - match["score"]) <= 0.5, (total, match["score"])
    assert abs(sum(item["weight"] for item in match["dimensions"].values()) - 1.0) <= 0.001
    assert match["why"]["formula"]
    assert match["why"]["algorithmVersion"]
    # The zero-key path is degraded by design, and the response says so. What must *not*
    # appear is the warning that changes what the score means: an unmeasured evidence
    # dimension.
    assert not any("证据" in warning for warning in match["warnings"]), match["warnings"]
    assert match["degraded"] is True

    # The résumé proves STM32 and FreeRTOS, so the engine must treat them as met. It does
    # not have to list them under `strengths`: that list has a threshold — a skill becomes a
    # highlight only when its effective level reaches 0.5, and effective level is the
    # declared level (MODERATE → 0.6) scaled by how much evidence supports it (one chunk →
    # 0.73), which lands at 0.44. The property that matters here is that an evidenced
    # requirement is not reported as a gap.
    gapped = {item["canonicalId"] for item in match["gaps"]}
    assert "stm32" not in gapped and "free_rtos" not in gapped, gapped
    assert match["dimensions"]["skill"]["score"] > 0
    assert match["dimensions"]["skill"]["evidenceIds"], "met requirements must cite evidence"
    assert all(item["reason"] for item in match["strengths"])

    # Requirements the résumé does not cover are gaps — that is the product's point.
    assert gapped, "a posting asking for CAN/SPI/AUTOSAR must produce gaps"

    async with app.state.session_factory() as db:
        stored = await db.scalar(select(func.count()).select_from(JobMatch))
    assert stored >= 1

    latest = envelope(await client.get(f"/api/v1/jobs/{job['id']}/match", headers=demo.headers))[
        "data"
    ]
    assert latest["score"] == match["score"]
    assert latest["why"]["formula"] == match["why"]["formula"]


async def test_match_without_evidence_says_the_dimension_is_unmeasured(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """A fresh account has no graph. The score must not silently imply it was measured."""
    account = await make_user(display_name="No Evidence Candidate")
    job = await _analyze(client, envelope, account)

    response = await client.post(f"/api/v1/jobs/{job['id']}/match", headers=account.headers)
    assert response.status_code == 200, response.text
    match = envelope(response)["data"]
    assert any("证据" in warning for warning in match["warnings"]), match["warnings"]
    assert match["dimensions"]["evidence"]["score"] == 0.0


async def test_matching_twice_keeps_the_history(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    """Keeping every run is what makes a changed score auditable."""
    await _evidence_ready(client, envelope, demo)
    job = await _analyze(client, envelope, demo)

    async def match_count() -> int:
        async with app.state.session_factory() as db:
            return int(
                await db.scalar(
                    select(func.count())
                    .select_from(JobMatch)
                    .where(JobMatch.job_id == UUID(job["id"]))
                )
                or 0
            )

    before = await match_count()
    for _ in range(2):
        response = await client.post(f"/api/v1/jobs/{job['id']}/match", headers=demo.headers)
        assert response.status_code == 200, response.text

    assert await match_count() == before + 2


async def test_a_job_is_scoped_to_its_owner(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session, make_user: UserFactory
) -> None:
    job = await _analyze(client, envelope, demo)
    other = await make_user(display_name="Other Candidate")

    for path in (
        f"/api/v1/jobs/{job['id']}",
        f"/api/v1/jobs/{job['id']}/skill-tree",
    ):
        response = await client.get(path, headers=other.headers)
        assert response.status_code == 404, path
        assert envelope(response, success=False)["error"]["code"] == "NOT_FOUND"

    assert (
        await client.post(f"/api/v1/jobs/{job['id']}/match", headers=other.headers)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/jobs/{job['id']}", headers=other.headers)
    ).status_code == 404

    theirs = envelope(await client.get("/api/v1/jobs", headers=other.headers))["data"]
    assert all(item["id"] != job["id"] for item in theirs["items"])


async def test_analyze_refuses_empty_text_and_unknown_sources(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    empty = await client.post("/api/v1/jobs/analyze", json={"text": ""}, headers=demo.headers)
    assert empty.status_code == 400

    unknown = await client.post(
        "/api/v1/jobs/analyze",
        json={"text": "Some posting", "source": "carrier-pigeon"},
        headers=demo.headers,
    )
    assert unknown.status_code == 400
    assert envelope(unknown, success=False)["error"]["code"] == "VALIDATION_ERROR"

    # An unknown field is refused rather than ignored, as with manual evidence.
    extra = await client.post(
        "/api/v1/jobs/analyze",
        json={"text": "Some posting", "matchScore": 99},
        headers=demo.headers,
    )
    assert extra.status_code == 400


async def test_matching_an_unmatched_job_is_a_404(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    job = await _analyze(client, envelope, demo)
    response = await client.get(f"/api/v1/jobs/{job['id']}/match", headers=demo.headers)
    assert response.status_code == 404
    assert envelope(response, success=False)["error"]["code"] == "NOT_FOUND"


async def test_deleting_a_job_removes_its_requirements_and_matches(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    await _evidence_ready(client, envelope, demo)
    job = await _analyze(client, envelope, demo)
    await client.post(f"/api/v1/jobs/{job['id']}/match", headers=demo.headers)
    job_id = UUID(job["id"])

    deleted = await client.delete(f"/api/v1/jobs/{job['id']}", headers=demo.headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert (await client.get(f"/api/v1/jobs/{job['id']}", headers=demo.headers)).status_code == 404

    async with app.state.session_factory() as db:
        skills = await db.scalar(
            select(func.count()).select_from(JobSkill).where(JobSkill.job_id == job_id)
        )
        matches = await db.scalar(
            select(func.count()).select_from(JobMatch).where(JobMatch.job_id == job_id)
        )
    assert skills == 0, "the FK cascade must remove requirement rows"
    assert matches == 0, "the FK cascade must remove match history"
