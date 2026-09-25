"""``/evidence`` and ``/evidence-graph`` — the product's core surface.

The path under test is the one the product exists for: upload a résumé, let the worker
parse it, then analyse it into evidence with a confidence and a link to the skill it
supports. The assertions concentrate on what makes the number trustworthy — that it can be
recomputed from the stored factors, that a citation survives a round trip, and that
analysing twice cannot inflate the graph.

The database is shared for the whole session, so each test's fixture text is unique: the
résumé hash decides de-duplication, and identical bytes would make a second upload a no-op.
"""

from __future__ import annotations

import asyncio
import itertools
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from careerforge_api.models.document import DocumentChunk
from careerforge_api.models.evidence import Evidence, EvidenceLinkRow
from careerforge_api.models.user import User
from tests.conftest import EnvelopeCheck, Session, UserFactory

_BODY = """教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 2023.07-2023.12
使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试，
并完成 PID 参数整定使控制周期稳定在 1kHz。

专业技能
C/C++、Python、STM32、FreeRTOS、Git
"""

_counter = itertools.count()


def _resume() -> bytes:
    return f"{_BODY}\n<!-- fixture {next(_counter)} -->\n".encode()


async def _upload_and_parse(client: AsyncClient, envelope: EnvelopeCheck, session: Session) -> str:
    """Upload a résumé and wait for the worker to store it; returns the document id."""
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
    return accepted["documentId"]


async def _analyze(
    client: AsyncClient, envelope: EnvelopeCheck, session: Session, document_id: str
) -> dict:
    response = await client.post(
        f"/api/v1/documents/{document_id}/analyze", headers=session.headers
    )
    assert response.status_code == 200, response.text
    return envelope(response)["data"]


async def test_analyze_turns_a_stored_resume_into_evidence_and_skill_links(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    document_id = await _upload_and_parse(client, envelope, demo)
    result = await _analyze(client, envelope, demo, document_id)

    assert result["documentId"] == document_id
    assert result["evidenceCreated"] >= 1
    assert result["skillCount"] >= 1, "a résumé naming STM32 and FreeRTOS must yield skills"
    assert result["linksWritten"] >= 1
    assert 0.0 < result["meanConfidence"] <= 1.0
    assert result["warnings"] == []

    listing = envelope(await client.get("/api/v1/evidence", headers=demo.headers))["data"]
    assert listing["total"] >= 1
    ours = [item for item in listing["items"] if item["metadata"].get("documentId") == document_id]
    assert ours

    item = ours[0]
    assert item["kind"] == "document_chunk"
    # A citation has to be followable: filename, chunk index and a character range, all in
    # the same camelCase vocabulary as the rest of the payload.
    assert item["metadata"]["filename"] == "resume.txt"
    assert item["locator"]["charStart"] == 0
    assert item["locator"]["charEnd"] > 0
    assert item["documentChunkId"]

    graph = envelope(await client.get("/api/v1/evidence-graph", headers=demo.headers))["data"]
    assert graph["nodeCount"] >= 1
    skill_nodes = [node for node in graph["nodes"] if node["type"] == "skill"]
    assert skill_nodes
    canonical = {node["meta"].get("canonicalId") for node in skill_nodes}
    assert {"stm32", "free_rtos"} & canonical, canonical
    assert any(node["type"] == "candidate" for node in graph["nodes"])
    assert graph["unresolvedNodeCount"] == 0


async def test_confidence_can_be_recomputed_from_the_stored_factors(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """The number is only meaningful if the row it came from reproduces it."""
    document_id = await _upload_and_parse(client, envelope, demo)
    await _analyze(client, envelope, demo, document_id)

    listing = envelope(await client.get("/api/v1/evidence", headers=demo.headers))["data"]
    ours = [item for item in listing["items"] if item["metadata"].get("documentId") == document_id]
    assert ours
    for item in ours:
        factors = item["factors"]
        assert factors is not None
        expected = round(
            0.30 * factors["sourceAuthority"]
            + 0.15 * factors["recency"]
            + 0.20 * factors["specificity"]
            + 0.20 * factors["corroboration"]
            + 0.15 * factors["extractionQuality"],
            3,
        )
        assert abs(expected - item["confidence"]) <= 0.002, (expected, item["confidence"])
        assert abs(factors["recomputed"] - item["confidence"]) <= 0.002
        assert factors["corroboration"] == min(
            1.0, round(0.4 + 0.2 * factors["corroborationSources"], 3)
        )


async def test_analysis_is_idempotent(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    """A "recompute" button must not be able to double the graph."""
    document_id = await _upload_and_parse(client, envelope, demo)
    first = await _analyze(client, envelope, demo, document_id)
    second = await _analyze(client, envelope, demo, document_id)

    assert first["evidenceCreated"] >= 1
    assert second["evidenceCreated"] == 0
    assert second["evidenceUpdated"] == first["evidenceCreated"]
    assert second["linksWritten"] == 0

    # Counted for *this* document: the database is shared across the session, so a global
    # count would be measuring every other test's résumé too.
    document_chunks = select(DocumentChunk.id).where(DocumentChunk.document_id == UUID(document_id))
    async with app.state.session_factory() as db:
        evidence_ids = select(Evidence.id).where(Evidence.document_chunk_id.in_(document_chunks))
        evidence_count = await db.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.id.in_(evidence_ids))
        )
        link_count = await db.scalar(
            select(func.count())
            .select_from(EvidenceLinkRow)
            .where(EvidenceLinkRow.to_id.in_(evidence_ids))
        )
    assert evidence_count == first["evidenceCreated"]
    assert link_count == first["linksWritten"]


async def test_evidence_detail_reports_what_cites_it(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    document_id = await _upload_and_parse(client, envelope, demo)
    await _analyze(client, envelope, demo, document_id)

    listing = envelope(await client.get("/api/v1/evidence", headers=demo.headers))["data"]
    ours = [item for item in listing["items"] if item["metadata"].get("documentId") == document_id]
    cited = [item for item in ours if item["confidence"] > 0]
    assert cited
    target = cited[0]["id"]

    trace = envelope(await client.get(f"/api/v1/evidence/{target}/trace", headers=demo.headers))[
        "data"
    ]
    assert trace["evidenceId"] == target
    assert trace["citedBy"], "evidence supporting a skill must report that edge"
    assert all(entry["relation"] for entry in trace["citedBy"])
    assert all(entry["fromId"] for entry in trace["citedBy"])

    detail = envelope(await client.get(f"/api/v1/evidence/{target}", headers=demo.headers))["data"]
    assert detail["citedByCount"] == len(trace["citedBy"])


async def test_graph_focus_traverses_from_a_skill_to_its_evidence(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """Clicking a skill must show the evidence that supports it, and nothing further."""
    document_id = await _upload_and_parse(client, envelope, demo)
    await _analyze(client, envelope, demo, document_id)

    full = envelope(await client.get("/api/v1/evidence-graph", headers=demo.headers))["data"]
    assert full["edgeCount"] >= 1

    focused = envelope(
        await client.get(
            "/api/v1/evidence-graph?focus=skill:stm32&depth=1&types=skill,document",
            headers=demo.headers,
        )
    )["data"]
    assert focused["focus"] == "skill:stm32"
    assert focused["nodeCount"] <= full["nodeCount"]
    assert any(
        node["type"] == "skill" and node["meta"].get("canonicalId") == "stm32"
        for node in focused["nodes"]
    )
    # Depth 1 keeps the skill and its immediate neighbours; the candidate node is two hops
    # away through the skill, so it must not appear.
    assert not any(node["type"] == "candidate" for node in focused["nodes"])


async def test_graph_stats_describe_the_returned_slice(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """A summary strip must not disagree with the canvas it sits above.

    ``stats`` used to be computed over the whole graph while the payload carried a
    subgraph, so the UI could show "129 nodes" over a ten-node canvas.
    """
    document_id = await _upload_and_parse(client, envelope, demo)
    await _analyze(client, envelope, demo, document_id)

    graph = envelope(await client.get("/api/v1/evidence-graph", headers=demo.headers))["data"]
    assert graph["stats"]["nodes"] == graph["nodeCount"]
    assert graph["stats"]["edges"] == graph["edgeCount"]
    # The whole graph is still reported, separately, so "showing 10 of 129" is possible.
    assert graph["totals"]["nodes"] >= graph["nodeCount"]

    with_orphans = envelope(
        await client.get("/api/v1/evidence-graph?includeOrphans=true", headers=demo.headers)
    )["data"]
    assert with_orphans["nodeCount"] >= graph["nodeCount"]


async def test_an_unknown_focus_falls_back_to_the_whole_graph(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """A stale bookmark is a normal event, not an error."""
    document_id = await _upload_and_parse(client, envelope, demo)
    await _analyze(client, envelope, demo, document_id)

    graph = envelope(
        await client.get("/api/v1/evidence-graph?focus=skill:does-not-exist", headers=demo.headers)
    )["data"]
    assert graph["nodeCount"] >= 1


async def test_graph_rejects_an_unknown_node_type(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    response = await client.get("/api/v1/evidence-graph?types=skill,unicorn", headers=demo.headers)
    assert response.status_code == 400
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "unicorn" in payload["error"]["message"]


async def test_manual_evidence_gets_a_computed_confidence(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """Manual evidence is the weakest tier, and it still cannot choose its own score."""
    response = await client.post(
        "/api/v1/evidence",
        json={
            "title": "上线了一个内部工具",
            "snippet": "用 Python 写了一个自动生成周报的脚本，团队每周节省两小时。",
            "locator": {"url": "https://example.com/tool"},
        },
        headers=demo.headers,
    )
    assert response.status_code == 201, response.text
    created = envelope(response)["data"]
    assert created["created"] is True, "this call is the one that inserted the row"
    assert created["kind"] == "manual"
    # 0.55 is the self-report tier (``AUTHORITY_SCORES[RESUME_SELF_REPORT]``), strictly
    # below the uploaded-document tier (0.80). Hand-typed evidence must never be scored as
    # though a reviewer could open it.
    assert created["factors"]["sourceAuthority"] == 0.55
    assert 0.0 < created["confidence"] <= 1.0

    # An unknown field is refused rather than ignored: a client that sends `confidence`
    # must be told it is not accepted, not silently have it dropped.
    rejected = await client.post(
        "/api/v1/evidence",
        json={"title": "x", "confidence": 0.99},
        headers=demo.headers,
    )
    assert rejected.status_code == 400


async def test_adding_the_same_evidence_twice_is_not_a_server_error(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    """``POST /evidence`` is ``get_or_create`` (PHASE 14), not a blind insert.

    ``evidence`` is unique on ``(user_id, kind, content_hash)`` and the insert did not honour it,
    so a replay was a ``500 INTERNAL_ERROR`` — measured, and reported as a backend bug by both
    clients that add manual evidence (``apps/web/e2e/helpers/pages.ts``,
    ``apps/web/scripts/capture-pages.mts``), which is why each of them reads before writing. An
    ingestion pipeline is *expected* to replay; the honest answer to "store this" is the row that
    already holds it.
    """
    payload = {
        "title": "重复提交的证据",
        "snippet": "同一段内容提交两次，必须只落一行，并且第二次不是错误。",
        "locator": {"path": "notes.md", "line": 7},
    }
    first = await client.post("/api/v1/evidence", json=payload, headers=demo.headers)
    assert first.status_code == 201, first.text
    created = envelope(first)["data"]
    assert created["created"] is True

    second = await client.post("/api/v1/evidence", json=payload, headers=demo.headers)
    assert second.status_code == 200, (
        f"a repeat insert answered {second.status_code}: {second.text}"
    )
    repeated = envelope(second)["data"]
    assert repeated["created"] is False, "the second call created nothing"
    assert repeated["id"] == created["id"], "the same content is the same row"
    assert repeated["confidence"] == created["confidence"]

    # Exactly one row exists for that content — the constraint and the response agree. The count
    # is taken through the ORM rather than the API, so a response that merely *reported* an
    # existing row cannot pass.
    async with app.state.session_factory() as db:
        count = await db.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.title == payload["title"])
        )
    assert count == 1, f"{count} rows for one payload"
    assert UUID(created["id"])


async def test_deleting_evidence_removes_the_edges_that_reference_it(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    """An edge to evidence that no longer exists would render a node that cannot be opened."""
    document_id = await _upload_and_parse(client, envelope, demo)
    await _analyze(client, envelope, demo, document_id)

    listing = envelope(await client.get("/api/v1/evidence", headers=demo.headers))["data"]
    ours = [item for item in listing["items"] if item["metadata"].get("documentId") == document_id]
    target = ours[0]["id"]

    deleted = await client.delete(f"/api/v1/evidence/{target}", headers=demo.headers)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert (await client.get(f"/api/v1/evidence/{target}", headers=demo.headers)).status_code == 404

    async with app.state.session_factory() as db:
        remaining = await db.scalar(
            select(func.count())
            .select_from(EvidenceLinkRow)
            .where(EvidenceLinkRow.to_id == UUID(target))
        )
    assert remaining == 0

    graph = envelope(await client.get("/api/v1/evidence-graph", headers=demo.headers))["data"]
    assert all(node["id"] != target for node in graph["nodes"])
    assert all(edge["target"] != target and edge["source"] != target for edge in graph["edges"])


async def test_evidence_is_scoped_to_its_owner(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session, make_user: UserFactory
) -> None:
    document_id = await _upload_and_parse(client, envelope, demo)
    await _analyze(client, envelope, demo, document_id)

    listing = envelope(await client.get("/api/v1/evidence", headers=demo.headers))["data"]
    target = listing["items"][0]["id"]

    other = await make_user(display_name="Other Candidate")
    assert (
        await client.get(f"/api/v1/evidence/{target}", headers=other.headers)
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/evidence/{target}/trace", headers=other.headers)
    ).status_code == 404
    assert (
        await client.delete(f"/api/v1/evidence/{target}", headers=other.headers)
    ).status_code == 404

    theirs = envelope(await client.get("/api/v1/evidence", headers=other.headers))["data"]
    assert theirs["total"] == 0
    graph = envelope(await client.get("/api/v1/evidence-graph", headers=other.headers))["data"]
    assert all(node["type"] != "document" for node in graph["nodes"])


async def test_analyze_refuses_a_document_with_no_stored_text(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, make_user: UserFactory
) -> None:
    """Local Mode keeps no text, so analysis is impossible — and the API says why.

    ``409`` rather than ``400``: the request is well-formed and the document exists; it is
    the document's current state that makes the work impossible.
    """
    account = await make_user(display_name="Local Candidate")
    async with app.state.session_factory() as db:
        user = await db.get(User, UUID(account.id))
        assert user is not None
        user.storage_scope = "local"
        await db.commit()

    document_id = await _upload_and_parse(client, envelope, account)
    response = await client.post(
        f"/api/v1/documents/{document_id}/analyze", headers=account.headers
    )
    assert response.status_code == 409, response.text
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "CONFLICT"
    assert "retention" in payload["error"]["message"]

    # ... and no half-built evidence was left behind.
    listing = envelope(await client.get("/api/v1/evidence", headers=account.headers))["data"]
    assert listing["total"] == 0


async def test_analyze_requires_authentication(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.post("/api/v1/documents/00000000-0000-0000-0000-000000000000/analyze")
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"
