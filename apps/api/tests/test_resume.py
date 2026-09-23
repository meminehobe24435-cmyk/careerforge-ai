"""``/resume`` and the Claim Validator — the gate, made durable.

The assertions concentrate on the property the product claims: **a supported sentence can name
the evidence that supports it, and an unsupported one is refused rather than reworded.** A test
that only checked status codes would pass on a gate that approved everything.
"""

from __future__ import annotations

import asyncio
import itertools

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from careerforge_api.models.resume import ClaimEvidence, ResumeClaim
from tests.conftest import EnvelopeCheck, Session, UserFactory

RESUME = """教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 2023.07-2023.12
使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。

项目经历
Balance Robot 基于 STM32 与 FreeRTOS 的两轮自平衡小车。

专业技能
C/C++、Python、STM32、FreeRTOS、CAN
"""

JD_TEXT = """某某科技有限公司
岗位：嵌入式软件工程师

任职要求：
1. 熟悉 STM32 平台开发；
2. 熟悉 FreeRTOS 实时操作系统。
"""

#: A sentence the evidence cannot support: it names a technology nothing the candidate supplied
#: mentions, and it carries a number with nothing to compare it against.
UNSUPPORTED_CLAIM = "使用 Kubernetes 将部署效率提升了 300%，并主导了 TensorFlow 模型上线。"

_counter = itertools.count()


def _resume() -> bytes:
    return f"{RESUME}\n<!-- fixture {next(_counter)} -->\n".encode()


async def _evidence_ready(client: AsyncClient, envelope: EnvelopeCheck, session: Session) -> None:
    """Upload, parse, analyse, and import the profile — everything the gate can cite."""
    body = await client.post(
        "/api/v1/documents",
        files={"file": ("resume.txt", _resume(), "text/plain")},
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


async def test_a_supported_claim_names_its_evidence(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """The core promise: traceability, not a badge."""
    await _evidence_ready(client, envelope, demo)

    response = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "使用 STM32 与 FreeRTOS 开发电机控制固件。"},
        headers=demo.headers,
    )
    assert response.status_code == 200, response.text
    payload = envelope(response)["data"]
    validation = payload["claim"]

    assert payload["claimId"], "a validated claim is stored and can be cited later"
    assert validation["status"] in {"supported", "partially_supported"}, validation
    assert validation["confidence"] > 0
    assert validation["sources"], "a supported claim must name what supports it"
    for source in validation["sources"]:
        assert source["evidenceId"]
        assert 0.0 <= source["relevance"] <= 1.0
        assert source["channel"] in {"semantic", "keyword", "both", "manual"}


async def test_an_unsupported_claim_is_refused_not_reworded(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """The difference between this product and a paraphraser."""
    await _evidence_ready(client, envelope, demo)

    response = await client.post(
        "/api/v1/evidence/validate",
        json={"text": UNSUPPORTED_CLAIM},
        headers=demo.headers,
    )
    assert response.status_code == 200, response.text
    validation = envelope(response)["data"]["claim"]

    assert validation["status"] in {"unsupported", "contradicted"}, validation
    assert validation["reasons"], "a refusal must explain itself"
    assert any(reason["rule"] for reason in validation["reasons"])
    assert validation["hasQuantifiedClaim"] is True
    # Every numeric claim without comparable evidence is a blocker, and the response says which
    # rule fired rather than only that something went wrong.
    rules = {reason["rule"] for reason in validation["reasons"]}
    assert rules & {"numeric_without_evidence", "no_evidence_match", "skill_not_in_graph"}, rules


async def test_batch_validation_stores_each_claim(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    await _evidence_ready(client, envelope, demo)

    response = await client.post(
        "/api/v1/evidence/validate/batch",
        json=[
            {"text": "使用 STM32 与 FreeRTOS 开发电机控制固件。"},
            {"text": UNSUPPORTED_CLAIM, "section": "project"},
        ],
        headers=demo.headers,
    )
    assert response.status_code == 200, response.text
    items = envelope(response)["data"]
    assert len(items) == 2
    # Each item is ``{claimId, claim}``; the verdict lives on ``claim``.
    assert items[0]["claim"]["status"] != items[1]["claim"]["status"], items

    async with app.state.session_factory() as db:
        stored = await db.scalar(select(func.count()).select_from(ResumeClaim))
    assert stored >= 2


async def test_batch_is_bounded_and_reports_the_limit(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    too_many = [{"text": f"claim {index}"} for index in range(21)]
    response = await client.post(
        "/api/v1/evidence/validate/batch", json=too_many, headers=demo.headers
    )
    assert response.status_code == 400
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "20" in payload["error"]["message"]

    empty = await client.post("/api/v1/evidence/validate/batch", json=[], headers=demo.headers)
    assert empty.status_code == 400


async def test_optimize_gates_every_bullet_and_stores_the_version(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    await _evidence_ready(client, envelope, demo)

    analysis = await client.post(
        "/api/v1/jobs/analyze",
        json={"text": f"{JD_TEXT}\n<!-- fixture {next(_counter)} -->"},
        headers=demo.headers,
    )
    job = envelope(analysis)["data"]

    response = await client.post(
        "/api/v1/resume/optimize",
        json={
            "jobId": job["id"],
            "label": "嵌入式岗定制版",
            "bullets": [
                {
                    "section": "experience",
                    "original": "使用 STM32 与 FreeRTOS 开发电机控制固件。",
                },
                {"section": "project", "original": UNSUPPORTED_CLAIM},
            ],
        },
        headers=demo.headers,
    )
    assert response.status_code == 200, response.text
    version = envelope(response)["data"]

    assert version["id"]
    assert version["targetJobId"] == job["id"]
    assert version["label"] == "嵌入式岗定制版"
    assert 0.0 <= version["integrityScore"] <= 1.0
    stats = version["claimStats"]
    assert sum(stats.values()) >= 1, stats

    claims = version["claims"]
    assert claims, "every bullet is stored as a claim with its verdict"
    for claim in claims:
        assert claim["status"] in {
            "pending",
            "supported",
            "partially_supported",
            "unsupported",
            "contradicted",
        }
        assert claim["originalText"], "the candidate's own wording is kept for the diff"
        # A supported claim carries its citations; an unsupported one carries its reasons.
        if claim["status"] in {"supported", "partially_supported"}:
            assert claim["evidence"], claim
        else:
            assert claim["reasons"], claim

    listed = envelope(await client.get("/api/v1/resume/versions", headers=demo.headers))["data"]
    assert any(item["id"] == version["id"] for item in listed)

    fetched = envelope(
        await client.get(f"/api/v1/resume/versions/{version['id']}", headers=demo.headers)
    )["data"]
    assert len(fetched["claims"]) == len(claims)
    assert fetched["contentMd"]


async def test_integrity_score_reflects_what_is_supported(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    """The number must agree with the claims it summarises, not be computed separately."""
    await _evidence_ready(client, envelope, demo)

    response = await client.post(
        "/api/v1/resume/optimize",
        json={
            "bullets": [
                {"section": "experience", "original": "使用 STM32 开发电机控制固件。"},
                {"section": "project", "original": UNSUPPORTED_CLAIM},
            ]
        },
        headers=demo.headers,
    )
    version = envelope(response)["data"]
    supported = sum(
        1 for claim in version["claims"] if claim["status"] in {"supported", "partially_supported"}
    )
    expected = round(supported / len(version["claims"]), 4) if version["claims"] else 0.0
    assert abs(version["integrityScore"] - expected) <= 0.001, (version["integrityScore"], expected)

    async with app.state.session_factory() as db:
        citations = await db.scalar(select(func.count()).select_from(ClaimEvidence))
    assert citations >= 1, "a supported claim must have written its citations"


async def test_a_claim_can_exist_without_a_version(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    """The Validator page checks a sentence before there is any version to attach it to."""
    await _evidence_ready(client, envelope, demo)
    response = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "使用 STM32 开发固件。"},
        headers=demo.headers,
    )
    claim_id = envelope(response)["data"]["claimId"]

    async with app.state.session_factory() as db:
        claim = await db.scalar(
            select(ResumeClaim).where(ResumeClaim.id == __import__("uuid").UUID(claim_id))
        )
    assert claim is not None
    assert claim.resume_version_id is None


async def test_deleting_a_version_removes_its_claims_and_citations(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    await _evidence_ready(client, envelope, demo)
    response = await client.post(
        "/api/v1/resume/optimize",
        json={"bullets": [{"section": "experience", "original": "使用 STM32 开发固件。"}]},
        headers=demo.headers,
    )
    version = envelope(response)["data"]

    from uuid import UUID

    deleted = await client.delete(f"/api/v1/resume/versions/{version['id']}", headers=demo.headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert (
        await client.get(f"/api/v1/resume/versions/{version['id']}", headers=demo.headers)
    ).status_code == 404

    async with app.state.session_factory() as db:
        claims = await db.scalar(
            select(func.count())
            .select_from(ResumeClaim)
            .where(ResumeClaim.resume_version_id == UUID(version["id"]))
        )
    assert claims == 0, "claims cascade with their version"


async def test_resume_is_scoped_to_its_owner(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session, make_user: UserFactory
) -> None:
    await _evidence_ready(client, envelope, demo)
    response = await client.post(
        "/api/v1/resume/optimize",
        json={"bullets": [{"section": "experience", "original": "使用 STM32 开发固件。"}]},
        headers=demo.headers,
    )
    version = envelope(response)["data"]

    other = await make_user(display_name="Other Candidate")
    assert (
        await client.get(f"/api/v1/resume/versions/{version['id']}", headers=other.headers)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/resume/versions/{version['id']}", headers=other.headers)
    ).status_code == 404
    assert (
        envelope(await client.get("/api/v1/resume/versions", headers=other.headers))["data"] == []
    )


async def test_validation_refuses_a_bad_section_and_requires_auth(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    bad = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "some claim", "section": "hobbies"},
        headers=demo.headers,
    )
    assert bad.status_code == 400
    assert envelope(bad, success=False)["error"]["code"] == "VALIDATION_ERROR"

    anonymous = await client.post("/api/v1/evidence/validate", json={"text": "some claim"})
    assert anonymous.status_code == 401

    extra = await client.post(
        "/api/v1/evidence/validate",
        json={"text": "some claim", "confidence": 0.99},
        headers=demo.headers,
    )
    assert extra.status_code == 400, "a client must not be able to supply its own confidence"
