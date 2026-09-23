"""``/tasks/*`` — the long-task contract of ``docs/API.md`` §1.4.

The queue is driven directly (``app.state.queue.enqueue``) because no PHASE 1 endpoint
returns ``202`` yet; the endpoints that will (profile import, GitHub analysis, resume
optimisation) reuse exactly this queue and these responses.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient

from careerforge_api.core.ids import parse_task_id, task_public_id
from tests.conftest import EnvelopeCheck, Session, UserFactory


async def _enqueue(app: FastAPI, *, kind: str, user_id: str | None, payload: dict | None = None):
    return await app.state.queue.enqueue(
        kind=kind, payload=payload or {}, user_id=UUID(user_id) if user_id else None
    )


async def test_task_lifecycle_is_queued_then_succeeded_with_stages(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    job = await _enqueue(app, kind="system.ping", user_id=demo.id, payload={"hello": "world"})
    task_id = task_public_id(job.id)

    # The documented id shape (`tsk_…`) round-trips to the UUID primary key.
    assert task_id.startswith("tsk_")
    assert parse_task_id(task_id) == job.id

    # queued (or already running), with the documented keys present
    first = envelope(await client.get(f"/api/v1/tasks/{task_id}", headers=demo.headers))["data"]
    assert set(first) >= {"taskId", "status", "progress", "stage", "result", "error"}
    assert first["taskId"] == task_id
    assert first["status"] in {"queued", "running", "succeeded"}

    for _ in range(100):
        payload = envelope(await client.get(f"/api/v1/tasks/{task_id}", headers=demo.headers))[
            "data"
        ]
        if payload["status"] == "succeeded":
            break
        await asyncio.sleep(0.02)

    assert payload["status"] == "succeeded"
    assert payload["progress"] == 100
    assert payload["result"] == {"pong": True, "payload": {"hello": "world"}}
    assert payload["error"] is None
    assert payload["attempts"] == 1
    assert payload["queuedAt"] and payload["startedAt"] and payload["finishedAt"]


async def test_task_accepts_a_bare_uuid_too(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    job = await _enqueue(app, kind="system.noop", user_id=demo.id)
    response = await client.get(f"/api/v1/tasks/{job.id}", headers=demo.headers)
    assert response.status_code == 200
    assert envelope(response)["data"]["taskId"] == task_public_id(job.id)


async def test_malformed_task_id_is_a_404(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    for bad in ("not-a-uuid", "tsk_zzzz", "123"):
        response = await client.get(f"/api/v1/tasks/{bad}", headers=demo.headers)
        assert response.status_code == 404
        assert envelope(response, success=False)["error"]["code"] == "NOT_FOUND"


async def test_another_users_task_is_404_not_403(
    client: AsyncClient,
    envelope: EnvelopeCheck,
    app: FastAPI,
    make_user: UserFactory,
) -> None:
    """docs/API.md §1.2: cross-user resources must not reveal that they exist."""
    owner = await make_user()
    intruder = await make_user()
    job = await _enqueue(app, kind="system.ping", user_id=owner.id)
    task_id = task_public_id(job.id)

    read = await client.get(f"/api/v1/tasks/{task_id}", headers=intruder.headers)
    assert read.status_code == 404
    assert envelope(read, success=False)["error"]["code"] == "NOT_FOUND"

    cancel = await client.post(f"/api/v1/tasks/{task_id}/cancel", headers=intruder.headers)
    assert cancel.status_code == 404
    assert envelope(cancel, success=False)["error"]["code"] == "NOT_FOUND"


async def test_tasks_require_authentication(
    client: AsyncClient, app: FastAPI, demo: Session
) -> None:
    job = await _enqueue(app, kind="system.noop", user_id=demo.id)
    assert (await client.get(f"/api/v1/tasks/{task_public_id(job.id)}")).status_code == 401
    assert (await client.post(f"/api/v1/tasks/{task_public_id(job.id)}/cancel")).status_code == 401


async def test_system_tasks_are_readable_by_any_authenticated_user(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, make_user: UserFactory
) -> None:
    """``background_jobs.user_id`` is nullable for system work (docs/DATABASE.md §2.11)."""
    user = await make_user()
    job = await _enqueue(app, kind="system.noop", user_id=None)
    response = await client.get(f"/api/v1/tasks/{task_public_id(job.id)}", headers=user.headers)
    assert response.status_code == 200
    assert envelope(response)["data"]["kind"] == "system.noop"


async def test_cancelling_a_running_task_marks_it_cancelled(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    progress_calls: list[int] = []

    async def slow(context) -> dict[str, object]:  # type: ignore[no-untyped-def]
        """A handler that keeps working until it is cancelled."""
        for index in range(200):
            progress_calls.append(index)
            await context.report("working", min(99, index))
            await asyncio.sleep(0.02)
        return {"finished": True}

    app.state.queue.register_handler("test.slow", slow)
    job = await _enqueue(app, kind="test.slow", user_id=demo.id)
    task_id = task_public_id(job.id)
    await asyncio.sleep(0.1)

    response = await client.post(f"/api/v1/tasks/{task_id}/cancel", headers=demo.headers)
    assert response.status_code == 200
    data = envelope(response)["data"]
    assert data["cancelled"] is True
    assert data["status"] == "cancelled"

    await asyncio.sleep(0.05)
    after = envelope(await client.get(f"/api/v1/tasks/{task_id}", headers=demo.headers))["data"]
    assert after["status"] == "cancelled"
    assert progress_calls  # the handler really did run before it was stopped


async def test_cancelling_a_finished_task_is_idempotent(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    job = await _enqueue(app, kind="system.noop", user_id=demo.id)
    task_id = task_public_id(job.id)
    for _ in range(50):
        await asyncio.sleep(0.02)
        status = (await client.get(f"/api/v1/tasks/{task_id}", headers=demo.headers)).json()["data"]
        if status["status"] == "succeeded":
            break

    response = await client.post(f"/api/v1/tasks/{task_id}/cancel", headers=demo.headers)
    assert response.status_code == 200
    data = envelope(response)["data"]
    assert data["cancelled"] is False
    assert data["status"] == "succeeded"
    assert "already" in data["detail"]


async def test_unknown_job_kind_fails_with_a_clear_error(
    client: AsyncClient, envelope: EnvelopeCheck, app: FastAPI, demo: Session
) -> None:
    """A handler that does not exist must fail the row, never hang the queue."""
    job = await _enqueue(app, kind="nope.not.registered", user_id=demo.id)
    task_id = task_public_id(job.id)
    for _ in range(50):
        await asyncio.sleep(0.02)
        data = (await client.get(f"/api/v1/tasks/{task_id}", headers=demo.headers)).json()["data"]
        if data["status"] == "failed":
            break

    assert data["status"] == "failed"
    assert data["error"] and "no handler" in data["error"]
