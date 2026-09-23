"""``/documents/*`` — upload, parse, chunk, read, delete.

These tests drive the whole documented path rather than the service: multipart upload →
``202`` with a task id → the queued ``document.ingest`` job → the stored document and its
chunks. That matters because the parts that broke in earlier phases were exactly the ones
unit tests could not see: a handler that was never registered, a transaction that rolled
back the failure it was supposed to record.

Fixture documents are text and Markdown, which need no optional parser; the PDF and DOCX
paths are covered against real bytes in ``packages/ai/tests/test_document_parsing.py``.
One corrupt PDF is uploaded here, because *failing* to parse is an HTTP behaviour.

The database is shared for the whole session and ``documents`` de-duplicates on
``(user_id, sha256)``, so the fixture bytes differ on every call. Identical bytes in two
tests would make the second upload a no-op — correct behaviour, and exactly what
``test_reuploading_identical_bytes_is_idempotent`` exercises deliberately.
"""

from __future__ import annotations

import asyncio
import itertools
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import func, select

from careerforge_api.models.document import DocumentChunk
from careerforge_api.models.user import User
from tests.conftest import EnvelopeCheck, Session, UserFactory

_RESUME_BODY = """教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 2023.07-2023.12
使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。

项目经历
Balance Robot 基于 STM32 的两轮自平衡小车，使用 FreeRTOS 划分任务，PID 控制电机。

专业技能
C/C++、Python、STM32、FreeRTOS、Git
"""

_uniqueness = itertools.count()


def _resume() -> bytes:
    """Résumé bytes that differ on every call, so the tests stay independent."""
    return f"{_RESUME_BODY}\n<!-- fixture {next(_uniqueness)} -->\n".encode()


def _note() -> bytes:
    return f"# 面试记录\n\n被问到 FreeRTOS 优先级反转。\n<!-- {next(_uniqueness)} -->\n".encode()


async def _upload(
    client: AsyncClient,
    session: Session,
    *,
    name: str,
    data: bytes,
    kind: str = "resume",
    mime: str = "text/plain",
) -> Response:
    return await client.post(
        "/api/v1/documents",
        files={"file": (name, data, mime)},
        data={"kind": kind},
        headers=session.headers,
    )


async def _accepted(
    client: AsyncClient,
    envelope: EnvelopeCheck,
    session: Session,
    *,
    name: str,
    data: bytes,
    kind: str = "resume",
    mime: str = "text/plain",
) -> dict:
    response = await _upload(client, session, name=name, data=data, kind=kind, mime=mime)
    assert response.status_code == 202, response.text
    return envelope(response)["data"]


async def _await_task(
    client: AsyncClient,
    envelope: EnvelopeCheck,
    session: Session,
    task_id: str | None,
    *,
    attempts: int = 200,
) -> dict:
    """Poll ``GET /tasks/{id}`` until it reaches a terminal state."""
    assert task_id is not None, "a queued upload must return a task id"
    payload: dict = {}
    for _ in range(attempts):
        payload = envelope(await client.get(f"/api/v1/tasks/{task_id}", headers=session.headers))[
            "data"
        ]
        if payload["status"] in {"succeeded", "failed", "cancelled"}:
            return payload
        await asyncio.sleep(0.02)
    raise AssertionError(f"task {task_id} never settled: {payload}")


async def _detail(
    client: AsyncClient, envelope: EnvelopeCheck, session: Session, doc_id: str
) -> dict:
    response = await client.get(f"/api/v1/documents/{doc_id}", headers=session.headers)
    return envelope(response)["data"]


async def _chunks(
    client: AsyncClient, envelope: EnvelopeCheck, session: Session, doc_id: str
) -> list[dict]:
    response = await client.get(f"/api/v1/documents/{doc_id}/chunks", headers=session.headers)
    return envelope(response)["data"]


async def _text(
    client: AsyncClient, envelope: EnvelopeCheck, session: Session, doc_id: str
) -> dict:
    response = await client.get(f"/api/v1/documents/{doc_id}/text", headers=session.headers)
    return envelope(response)["data"]


async def test_upload_parses_chunks_and_stores_a_text_resume(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    accepted = await _accepted(client, envelope, demo, name="resume.txt", data=_resume())
    assert accepted["taskId"].startswith("tsk_")
    assert accepted["documentId"]
    assert accepted["deduplicated"] is False

    task = await _await_task(client, envelope, demo, accepted["taskId"])
    assert task["status"] == "succeeded", task
    assert task["result"]["parseStatus"] == "parsed"
    assert task["result"]["chunkCount"] >= 1
    assert task["result"]["textRetained"] is True

    detail = await _detail(client, envelope, demo, accepted["documentId"])
    assert detail["parseStatus"] == "parsed"
    assert detail["kind"] == "resume"
    assert detail["format"] == "text"
    assert detail["encoding"] == "utf-8"
    assert detail["textRetained"] is True
    assert detail["charCount"] > 0
    assert detail["chunkCount"] >= 1
    assert detail["warnings"] == []
    # The preview is deliberately short: the full text has its own endpoint.
    assert detail["textPreview"]
    assert len(detail["textPreview"]) <= 400

    chunks = await _chunks(client, envelope, demo, accepted["documentId"])
    assert chunks
    assert [chunk["index"] for chunk in chunks] == sorted(chunk["index"] for chunk in chunks)
    assert any("FreeRTOS" in chunk["content"] for chunk in chunks)
    assert all(chunk["tokenCount"] > 0 for chunk in chunks)

    text = await _text(client, envelope, demo, accepted["documentId"])
    assert "FreeRTOS" in text["text"]
    assert text["unavailableReason"] is None


async def test_reuploading_identical_bytes_is_idempotent(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """Re-uploading a résumé must not fork the evidence graph."""
    payload = _resume()
    first = await _accepted(client, envelope, demo, name="resume.txt", data=payload)
    await _await_task(client, envelope, demo, first["taskId"])

    second = await _accepted(client, envelope, demo, name="resume.txt", data=payload)
    assert second["deduplicated"] is True
    assert second["documentId"] == first["documentId"]
    # No new work is promised, so no task id is returned.
    assert second["taskId"] is None
    assert second["status"] == "parsed"

    listing = envelope(await client.get("/api/v1/documents", headers=demo.headers))["data"]
    matching = [item for item in listing["items"] if item["id"] == first["documentId"]]
    assert len(matching) == 1


async def test_a_corrupt_pdf_fails_the_task_and_records_why(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """The stored failure row is the point: the candidate has to be told, and a server log
    is not where a candidate looks."""
    accepted = await _accepted(
        client,
        envelope,
        demo,
        name="broken.pdf",
        data=b"%PDF-1.4\nthis is not a pdf at all",
        mime="application/pdf",
    )

    task = await _await_task(client, envelope, demo, accepted["taskId"])
    assert task["status"] == "failed"
    assert task["error"]

    detail = await _detail(client, envelope, demo, accepted["documentId"])
    assert detail["parseStatus"] == "failed"
    assert detail["parseError"]
    assert detail["chunkCount"] == 0

    text = await _text(client, envelope, demo, accepted["documentId"])
    assert text["text"] is None
    assert text["unavailableReason"] == "parse_failed"


async def test_unsupported_type_is_refused_before_it_is_accepted(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    """A file this build cannot read is a 400 at upload time, not a 202 followed by a
    failed task: accepting work you cannot do is the least useful answer."""
    response = await _upload(
        client, demo, name="photo.png", data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, mime="image/png"
    )
    assert response.status_code == 400, response.text
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    assert "photo.png" in payload["error"]["message"]

    listing = envelope(await client.get("/api/v1/documents", headers=demo.headers))["data"]
    assert all(item["filename"] != "photo.png" for item in listing["items"])


async def test_upload_requires_authentication(client: AsyncClient, envelope: EnvelopeCheck) -> None:
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("resume.txt", _resume(), "text/plain")},
        data={"kind": "resume"},
    )
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_local_mode_reports_that_no_text_was_stored(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, make_user: UserFactory
) -> None:
    """Local Mode is a promise: the text is not on the server, and the API says so rather
    than showing an empty box.

    A fresh account is used rather than the demo one, because this test changes a column
    other tests depend on.
    """
    account = await make_user(display_name="Local Mode Candidate")
    async with app.state.session_factory() as db:
        user = await db.get(User, UUID(account.id))
        assert user is not None
        user.storage_scope = "local"
        await db.commit()

    accepted = await _accepted(client, envelope, account, name="resume.txt", data=_resume())
    task = await _await_task(client, envelope, account, accepted["taskId"])
    assert task["status"] == "succeeded", task
    assert task["result"]["textRetained"] is False
    assert task["result"]["chunkCount"] == 0

    detail = await _detail(client, envelope, account, accepted["documentId"])
    # Parsing still happened: the candidate learns what was in the file even though the
    # server did not keep it.
    assert detail["parseStatus"] == "parsed"
    assert detail["textRetained"] is False
    assert detail["textPreview"] is None
    assert detail["chunkCount"] == 0

    assert await _chunks(client, envelope, account, accepted["documentId"]) == []

    text = await _text(client, envelope, account, accepted["documentId"])
    assert text["text"] is None
    assert text["unavailableReason"] == "local_mode"


async def test_sensitive_identifiers_are_counted_not_stored(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    accepted = await _accepted(
        client,
        envelope,
        demo,
        name="contact.txt",
        data="联系方式\nalex@example.com\n手机 13800138000\n".encode(),
    )
    await _await_task(client, envelope, demo, accepted["taskId"])

    detail = await _detail(client, envelope, demo, accepted["documentId"])
    assert detail["piiFindingCount"] >= 2
    assert set(detail["piiKinds"]) >= {"email", "phone_cn"}


async def test_list_filters_by_kind_and_status(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    for name, data, kind in (
        ("resume.txt", _resume(), "resume"),
        ("notes.md", _note(), "notes"),
    ):
        accepted = await _accepted(client, envelope, demo, name=name, data=data, kind=kind)
        await _await_task(client, envelope, demo, accepted["taskId"])

    listing = envelope(await client.get("/api/v1/documents", headers=demo.headers))["data"]
    assert listing["total"] >= 2
    assert listing["byKind"].get("resume", 0) >= 1
    assert listing["byKind"].get("notes", 0) >= 1

    only_notes = envelope(await client.get("/api/v1/documents?kind=notes", headers=demo.headers))[
        "data"
    ]
    assert only_notes["items"]
    assert all(item["kind"] == "notes" for item in only_notes["items"])
    assert only_notes["total"] == len(only_notes["items"])

    # The status filter has to be applied in SQL: filtering after a LIMIT would return
    # short pages whose count disagrees with their items.
    parsed = envelope(await client.get("/api/v1/documents?status=parsed", headers=demo.headers))[
        "data"
    ]
    assert all(item["parseStatus"] == "parsed" for item in parsed["items"])
    assert parsed["total"] >= len(parsed["items"])


async def test_another_users_document_is_a_404_not_a_403(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session, make_user: UserFactory
) -> None:
    accepted = await _accepted(client, envelope, demo, name="resume.txt", data=_resume())
    document_id = accepted["documentId"]

    other = await make_user(display_name="Other Candidate")
    for path in (
        f"/api/v1/documents/{document_id}",
        f"/api/v1/documents/{document_id}/chunks",
        f"/api/v1/documents/{document_id}/text",
    ):
        response = await client.get(path, headers=other.headers)
        assert response.status_code == 404, path
        assert envelope(response, success=False)["error"]["code"] == "NOT_FOUND"

    deleted = await client.delete(f"/api/v1/documents/{document_id}", headers=other.headers)
    assert deleted.status_code == 404

    # ... and the other user's own list does not mention it.
    listing = envelope(await client.get("/api/v1/documents", headers=other.headers))["data"]
    assert all(item["id"] != document_id for item in listing["items"])


async def test_malformed_document_id_is_a_404(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    response = await client.get("/api/v1/documents/not-a-uuid", headers=demo.headers)
    assert response.status_code == 404
    assert envelope(response, success=False)["error"]["code"] == "NOT_FOUND"


async def test_deleting_a_document_removes_its_chunks(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    accepted = await _accepted(client, envelope, demo, name="resume.txt", data=_resume())
    await _await_task(client, envelope, demo, accepted["taskId"])
    document_id = accepted["documentId"]
    assert await _chunks(client, envelope, demo, document_id)

    deleted = await client.delete(f"/api/v1/documents/{document_id}", headers=demo.headers)
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""
    response = await client.get(f"/api/v1/documents/{document_id}", headers=demo.headers)
    assert response.status_code == 404

    async with app.state.session_factory() as db:
        remaining = await db.scalar(
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == UUID(document_id))
        )
    assert remaining == 0, "the FK cascade must remove chunks with their document"


async def test_unknown_kind_is_rejected_before_any_work(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    response = await _upload(client, demo, name="resume.txt", data=_resume(), kind="manifesto")
    assert response.status_code == 400
    assert envelope(response, success=False)["error"]["code"] == "VALIDATION_ERROR"
