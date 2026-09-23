"""Shared helpers for the tracker tests.

Split out when ``test_applications.py`` crossed the 500-line guard, and split by
responsibility rather than by size: the API-surface tests (``test_applications.py``) and the
state/history tests (``test_application_moves.py``) ask different questions of the same
endpoints, and both need to create a card. Duplicating four helpers across them would make
the two suites drift into disagreeing about what "tracked" means.

Not named ``test_*`` so pytest does not collect it, the same convention as
``interview_data.py``.
"""

from __future__ import annotations

import itertools

from httpx import AsyncClient

from tests.conftest import Session

JD_TEXT = """某某科技有限公司
岗位：嵌入式软件工程师
工作地点：上海

任职要求：
1. 熟悉 STM32 与 FreeRTOS；
2. 熟悉 CAN 总线通信协议。
"""

_counter = itertools.count()


def jd() -> str:
    """A unique posting per call: ``jobs`` de-duplicates on the description hash."""
    return f"{JD_TEXT}\n<!-- fixture {next(_counter)} -->\n"


async def analyze(client: AsyncClient, session: Session) -> str:
    response = await client.post(
        "/api/v1/jobs/analyze", json={"text": jd()}, headers=session.headers
    )
    assert response.status_code == 200, response.text
    return str(response.json()["data"]["id"])


async def track(
    client: AsyncClient, session: Session, *, company: str = "某某科技", status: str = "wishlist"
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/applications",
        json={"company": company, "role": "嵌入式软件工程师", "status": status},
        headers=session.headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def move(
    client: AsyncClient, session: Session, application_id: str, status: str, **extra: object
) -> dict[str, object]:
    response = await client.patch(
        f"/api/v1/applications/{application_id}",
        json={"status": status, **extra},
        headers=session.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def list_events(
    client: AsyncClient, session: Session, application_id: str
) -> list[dict[str, object]]:
    response = await client.get(
        f"/api/v1/applications/{application_id}/events", headers=session.headers
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def board(client: AsyncClient, session: Session, *, include_archived: bool = False) -> dict:
    suffix = "?includeArchived=true" if include_archived else ""
    response = await client.get(f"/api/v1/applications/board{suffix}", headers=session.headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]
