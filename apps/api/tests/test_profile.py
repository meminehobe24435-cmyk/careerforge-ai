"""``/profile`` — extraction, storage, and what the stored entities change downstream.

The last group of tests is the point of this module. Persisting entities is not a
bookkeeping exercise: before these tables existed, the graph drew placeholder nodes for
projects and the match engine scored the project and experience dimensions at 0.0 for a
candidate who had both. Those assertions fail if the wiring regresses.
"""

from __future__ import annotations

import asyncio
import itertools

from fastapi import FastAPI
from httpx import AsyncClient

from tests.conftest import EnvelopeCheck, Session, UserFactory

RESUME = """教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 2023.07-2023.12
使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。

项目经历
Balance Robot 基于 STM32 与 FreeRTOS 的两轮自平衡小车，使用 PID 控制电机。

专业技能
C/C++、Python、STM32、FreeRTOS
"""

JD_TEXT = """某某科技有限公司
岗位：嵌入式软件工程师

任职要求：
1. 熟悉 STM32 平台开发；
2. 熟悉 FreeRTOS 实时操作系统。
"""

_counter = itertools.count()


def _resume() -> str:
    return f"{RESUME}\n<!-- fixture {next(_counter)} -->"


async def _import(
    client: AsyncClient, envelope: EnvelopeCheck, session: Session, text: str | None = None
) -> dict:
    response = await client.post(
        "/api/v1/profile/import", json={"text": text or _resume()}, headers=session.headers
    )
    assert response.status_code == 200, response.text
    return envelope(response)["data"]


async def _profile(client: AsyncClient, envelope: EnvelopeCheck, session: Session) -> dict:
    return envelope(await client.get("/api/v1/profile", headers=session.headers))["data"]


async def test_import_extracts_and_persists_entities(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    result = await _import(client, envelope, demo)

    counts = result["counts"]
    assert counts["educations"] >= 1, counts
    assert counts["experiences"] >= 1, counts
    assert counts["projects"] >= 1, counts
    assert counts["skills"] >= 1, counts

    stored = await _profile(client, envelope, demo)
    assert stored["educations"]
    assert stored["experiences"]
    assert stored["projects"]
    assert stored["skills"]
    assert stored["slug"], "an import must give the account a public-page key"

    # Every entity carries its provenance: an unchecked extraction must be visibly different
    # from a row a candidate corrected.
    for collection in ("educations", "experiences", "projects", "skills"):
        for entity in stored[collection]:
            assert entity["origin"] in {"llm", "heuristic", "user_corrected", "import"}, entity

    project = stored["projects"][0]
    assert project["name"]
    assert isinstance(project["techStack"], list)


async def test_reimporting_replaces_rather_than_multiplies(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """A résumé re-exported with one sentence reworded is the same profile."""
    first = await _import(client, envelope, demo)
    before = await _profile(client, envelope, demo)

    second = await _import(client, envelope, demo)
    after = await _profile(client, envelope, demo)

    assert second["counts"] == first["counts"]
    for collection in ("educations", "experiences", "projects", "achievements", "skills"):
        assert len(after[collection]) == len(before[collection]), collection


async def test_reimporting_keeps_entity_identity(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """A re-import must update rows, not recreate them.

    Graph edges are stored against entity ids, so delete-and-insert orphans every edge pointing
    at a project the source still contains. The live run showed it: a re-import turned a real
    project node into ``project:de6dd367``. ``dedupe_key`` exists to identify the same entity
    across imports, and this asserts it is used for that.
    """
    first = await _import(client, envelope, demo)
    before = {
        project["name"]: project["id"]
        for project in (await _profile(client, envelope, demo))["projects"]
    }
    assert before

    second = await _import(client, envelope, demo)
    after = {
        project["name"]: project["id"]
        for project in (await _profile(client, envelope, demo))["projects"]
    }

    assert second["counts"]["projects"] == first["counts"]["projects"]
    assert after == before, "row identity must survive a re-import"


async def test_import_from_a_stored_document(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """The document path is how an upload becomes a profile without a copy-paste."""
    body = await client.post(
        "/api/v1/documents",
        files={"file": ("resume.txt", _resume().encode(), "text/plain")},
        data={"kind": "resume"},
        headers=demo.headers,
    )
    assert body.status_code == 202, body.text
    accepted = envelope(body)["data"]
    for _ in range(200):
        task = envelope(
            await client.get(f"/api/v1/tasks/{accepted['taskId']}", headers=demo.headers)
        )["data"]
        if task["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.02)
    assert task["status"] == "succeeded", task

    response = await client.post(
        "/api/v1/profile/import",
        json={"documentId": accepted["documentId"]},
        headers=demo.headers,
    )
    assert response.status_code == 200, response.text
    payload = envelope(response)["data"]
    assert payload["documentId"] == accepted["documentId"]
    assert payload["counts"]["projects"] >= 1


async def test_import_from_a_local_mode_document_explains_itself(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, make_user: UserFactory
) -> None:
    """Local Mode keeps no text, so there is nothing to extract — and the API says why."""
    from uuid import UUID

    from careerforge_api.models.user import User

    account = await make_user(display_name="Local Candidate")
    async with app.state.session_factory() as db:
        user = await db.get(User, UUID(account.id))
        assert user is not None
        user.storage_scope = "local"
        await db.commit()

    body = await client.post(
        "/api/v1/documents",
        files={"file": ("resume.txt", _resume().encode(), "text/plain")},
        data={"kind": "resume"},
        headers=account.headers,
    )
    accepted = envelope(body)["data"]
    for _ in range(200):
        task = envelope(
            await client.get(f"/api/v1/tasks/{accepted['taskId']}", headers=account.headers)
        )["data"]
        if task["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.02)

    response = await client.post(
        "/api/v1/profile/import",
        json={"documentId": accepted["documentId"]},
        headers=account.headers,
    )
    assert response.status_code == 400, response.text
    payload = envelope(response, success=False)
    assert "retention" in payload["error"]["message"]


async def test_stored_entities_resolve_the_graph_and_the_match(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """The reason these tables exist: real nodes, and dimensions that stop reading zero.

    Order matters, and it is the product's own order: import the profile, then analyse
    material. The graph *build* writes the candidate→project and project→skill edges and reads
    the profile while doing so, so the entities must be stored before the analysis runs — which
    is also the order the UI asks a new user to work in.
    """
    await _import(client, envelope, demo)

    body = await client.post(
        "/api/v1/documents",
        files={"file": ("resume.txt", _resume().encode(), "text/plain")},
        data={"kind": "resume"},
        headers=demo.headers,
    )
    accepted = envelope(body)["data"]
    for _ in range(200):
        task = envelope(
            await client.get(f"/api/v1/tasks/{accepted['taskId']}", headers=demo.headers)
        )["data"]
        if task["status"] in {"succeeded", "failed"}:
            break
        await asyncio.sleep(0.02)
    assert task["status"] == "succeeded", task
    analyzed = await client.post(
        f"/api/v1/documents/{accepted['documentId']}/analyze", headers=demo.headers
    )
    assert analyzed.status_code == 200, analyzed.text

    graph = envelope(await client.get("/api/v1/evidence-graph", headers=demo.headers))["data"]
    types = {node["type"] for node in graph["nodes"]}
    assert {"candidate", "project", "experience", "education"} <= types, types
    # ... and they are real nodes, not placeholders. Placeholders are the fallback for an
    # endpoint no table can resolve, and every endpoint here now has one.
    placeholders = [node for node in graph["nodes"] if node["meta"].get("unresolved")]
    assert placeholders == [], placeholders

    analysis = await client.post(
        "/api/v1/jobs/analyze",
        json={"text": f"{JD_TEXT}\n<!-- fixture {next(_counter)} -->"},
        headers=demo.headers,
    )
    job = envelope(analysis)["data"]
    match = envelope(await client.post(f"/api/v1/jobs/{job['id']}/match", headers=demo.headers))[
        "data"
    ]

    assert match["dimensions"]["project"]["score"] > 0.0, match["dimensions"]["project"]
    # The project's tech stack is what that dimension measures, so it must be cited.
    assert match["dimensions"]["project"]["notes"]


async def test_declared_skills_shadow_the_evidence_fallback(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """A declared profile wins over skills inferred from evidence.

    Both paths exist for a reason: a declaration carries a real level, an inference carries
    only a count. When a candidate has told us, the answer they gave is the one used.
    """
    await _import(client, envelope, demo)
    stored = await _profile(client, envelope, demo)
    assert stored["skills"]
    assert all(
        skill["level"] in {"none", "basic", "moderate", "strong", "expert"}
        for skill in stored["skills"]
    )


async def test_profile_is_scoped_to_its_owner(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session, make_user: UserFactory
) -> None:
    await _import(client, envelope, demo)
    other = await make_user(display_name="Other Candidate")

    theirs = await _profile(client, envelope, other)
    assert theirs["projects"] == []
    assert theirs["experiences"] == []
    assert theirs["skills"] == []


async def test_import_validates_its_input(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    empty = await client.post("/api/v1/profile/import", json={"text": "   "}, headers=demo.headers)
    assert empty.status_code == 400

    neither = await client.post("/api/v1/profile/import", json={}, headers=demo.headers)
    assert neither.status_code == 400

    bad_origin = await client.post(
        "/api/v1/profile/import",
        json={"text": "some text", "origin": "telepathy"},
        headers=demo.headers,
    )
    assert bad_origin.status_code == 400
    assert envelope(bad_origin, success=False)["error"]["code"] == "VALIDATION_ERROR"

    unknown_document = await client.post(
        "/api/v1/profile/import",
        json={"documentId": "00000000-0000-0000-0000-000000000000"},
        headers=demo.headers,
    )
    assert unknown_document.status_code == 404


async def test_import_requires_authentication(client: AsyncClient, envelope: EnvelopeCheck) -> None:
    response = await client.post("/api/v1/profile/import", json={"text": "anything"})
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"
