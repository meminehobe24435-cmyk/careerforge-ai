"""The application tracker's CRUD surface (``docs/API.md`` §2.9, ``docs/PRD.md`` FR-13).

What these tests protect, beyond the endpoints existing:

* **The board is a snapshot, not a view over live postings.** A card keeps the company,
  role and match score it was created with, so deleting a posting cannot silently change
  or empty a card. One test deletes the posting and re-reads the card.
* **A client cannot supply a score.** ``matchScore`` is refused on input; the number on the
  card is the system's own last computed match.
* **Someone else's card is 404**, including through ``POST /jobs/{id}/applications``.

The state and history semantics — what a move records, what a reorder re-derives, what the
timeline keeps — are in ``test_application_moves.py``.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from careerforge_api.models.application import Application, ApplicationEvent, CareerEvent
from tests.application_support import analyze, list_events, move, track
from tests.conftest import EnvelopeCheck, UserFactory

# ── creating ─────────────────────────────────────────────────────────────────


async def test_a_manual_card_is_tracked_with_its_creation_event(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory, app: FastAPI
) -> None:
    account = await make_user()
    created = await track(client, account, company="甲科技有限公司")

    assert created["status"] == "wishlist"
    assert created["position"] == 0
    assert created["appliedAt"] is None, "nothing has been applied to yet"
    assert created["matchScore"] is None, "no posting, so no score — not zero"

    events = await list_events(client, account, str(created["id"]))
    assert [event["toStatus"] for event in events] == ["wishlist"]
    assert events[0]["fromStatus"] is None, "the creation event has no previous status"

    async with app.state.session_factory() as db:
        milestones = await db.scalar(
            select(func.count())
            .select_from(CareerEvent)
            .where(
                CareerEvent.user_id == account.id,
                CareerEvent.kind == "application",
            )
        )
    # A wishlist card is a bookmark, not an act: no timeline milestone until it is applied to.
    # It used to write one, and PHASE 9's trend chart counted each application twice because of
    # it — the audit trail still records the creation, which is where that belongs.
    assert milestones == 0


async def test_a_card_from_a_posting_snapshots_the_posting(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory, app: FastAPI
) -> None:
    """FR-13.5 — the card copies the posting's identity and the stored match score."""
    account = await make_user()
    job_id = await analyze(client, account)
    matched = await client.post(f"/api/v1/jobs/{job_id}/match", headers=account.headers)
    assert matched.status_code == 200, matched.text
    score = matched.json()["data"]["score"]

    response = await client.post(
        f"/api/v1/jobs/{job_id}/applications",
        headers=account.headers,
    )
    assert response.status_code == 201, response.text
    card = response.json()["data"]

    assert card["jobId"] == job_id
    assert card["company"] == "某某科技有限公司", "company comes from the posting"
    assert card["role"] == "嵌入式软件工程师"
    assert card["location"] == "上海"
    assert card["matchScore"] == score, "the score is the system's own last match"

    # The snapshot survives the posting being deleted: a board that empties itself when a
    # posting is removed would be deleting the user's history on a housekeeping action.
    assert (
        await client.delete(f"/api/v1/jobs/{job_id}", headers=account.headers)
    ).status_code == 204
    detail = await client.get(f"/api/v1/applications/{card['id']}", headers=account.headers)
    assert detail.status_code == 200, detail.text
    after = detail.json()["data"]
    assert after["jobId"] is None
    assert after["company"] == "某某科技有限公司"
    assert after["matchScore"] == score


async def test_a_card_must_be_identifiable(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """A card with no company and no role cannot be identified on a board.

    FastAPI's own request-validation refusal, enveloped as ``400 VALIDATION_ERROR``
    (``docs/API.md`` §1.5) rather than a bare 422.
    """
    account = await make_user()
    response = await client.post("/api/v1/applications", json={}, headers=account.headers)
    assert response.status_code == 400, response.text
    assert envelope(response, success=False)["error"]["code"] == "VALIDATION_ERROR"


async def test_a_client_cannot_supply_its_own_match_score(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """``extra="forbid"``: a card claiming 99% for a job nobody scored is refused."""
    account = await make_user()
    response = await client.post(
        "/api/v1/applications",
        json={"company": "乙公司", "role": "工程师", "matchScore": 99},
        headers=account.headers,
    )
    assert response.status_code == 400, response.text


async def test_an_unknown_status_is_refused(
    client: AsyncClient, make_user: UserFactory, envelope: EnvelopeCheck
) -> None:
    account = await make_user()
    created = await client.post(
        "/api/v1/applications",
        json={"company": "丙公司", "role": "工程师", "status": "ghosted"},
        headers=account.headers,
    )
    assert created.status_code == 400, created.text

    listed = await client.get("/api/v1/applications?status=ghosted", headers=account.headers)
    assert listed.status_code == 400, listed.text
    assert envelope(listed, success=False)["error"]["code"] == "VALIDATION_ERROR"


# ── the board ────────────────────────────────────────────────────────────────


async def test_the_board_always_has_seven_columns_in_order(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Empty columns are included: a missing key forces the client to guess."""
    account = await make_user()
    response = await client.get("/api/v1/applications/board", headers=account.headers)
    assert response.status_code == 200, response.text
    board = response.json()["data"]

    assert [column["status"] for column in board["columns"]] == [
        "wishlist",
        "applied",
        "oa",
        "interview",
        "final",
        "offer",
        "rejected",
    ]
    assert board["counts"] == dict.fromkeys(
        ["wishlist", "applied", "oa", "interview", "final", "offer", "rejected"], 0
    )
    assert board["total"] == 0


async def test_cards_land_in_their_column_in_stored_order(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    first = await track(client, account, company="第一家")
    second = await track(client, account, company="第二家")
    await move(client, account, str(second["id"]), "applied")

    board = (await client.get("/api/v1/applications/board", headers=account.headers)).json()["data"]
    columns = {column["status"]: column["items"] for column in board["columns"]}

    assert [card["company"] for card in columns["wishlist"]] == ["第一家"]
    assert [card["company"] for card in columns["applied"]] == ["第二家"]
    assert board["counts"]["wishlist"] == 1
    assert board["counts"]["applied"] == 1
    assert board["total"] == 2
    assert columns["wishlist"][0]["position"] == 0
    assert columns["applied"][0]["position"] == 0, "a new column starts at zero"
    assert first["id"] != second["id"]


async def test_archiving_keeps_the_card_out_of_the_board_but_not_out_of_the_api(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    card = await track(client, account, company="要归档的")

    archived = await client.patch(
        f"/api/v1/applications/{card['id']}", json={"archived": True}, headers=account.headers
    )
    assert archived.status_code == 200, archived.text
    assert archived.json()["data"]["archivedAt"] is not None

    board = (await client.get("/api/v1/applications/board", headers=account.headers)).json()["data"]
    assert board["total"] == 0
    with_archived = (
        await client.get("/api/v1/applications/board?includeArchived=true", headers=account.headers)
    ).json()["data"]
    assert with_archived["total"] == 1
    assert with_archived["archived"] == 1
    assert with_archived["columns"][0]["items"][0]["id"] == card["id"]


# ── deleting ─────────────────────────────────────────────────────────────────


async def test_deleting_a_card_removes_its_history(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    account = await make_user()
    card = await track(client, account)
    await move(client, account, str(card["id"]), "applied")

    deleted = await client.delete(f"/api/v1/applications/{card['id']}", headers=account.headers)
    assert deleted.status_code == 204, deleted.text
    assert not deleted.content, "204 carries no body (docs/API.md §1.1)"

    gone = await client.get(f"/api/v1/applications/{card['id']}", headers=account.headers)
    assert gone.status_code == 404

    async with app.state.session_factory() as db:
        app_rows = await db.scalar(
            select(func.count()).select_from(Application).where(Application.user_id == account.id)
        )
        event_rows = await db.scalar(
            select(func.count())
            .select_from(ApplicationEvent)
            .where(ApplicationEvent.user_id == account.id)
        )
    assert app_rows == 0
    assert event_rows == 0, "events cascade with the card"

    # The timeline deliberately keeps the milestone: a career fact does not un-happen
    # because a board card was tidied away. One milestone here — the move to ``applied`` —
    # because creating the card in ``wishlist`` is not a milestone.
    async with app.state.session_factory() as db:
        milestones = await db.scalar(
            select(func.count()).select_from(CareerEvent).where(CareerEvent.ref_id == card["id"])
        )
    assert milestones == 1


# ── tenancy ──────────────────────────────────────────────────────────────────


async def test_another_accounts_card_is_404_everywhere(
    client: AsyncClient, make_user: UserFactory, envelope: EnvelopeCheck
) -> None:
    owner = await make_user(display_name="Owner")
    stranger = await make_user(display_name="Stranger")
    card = await track(client, owner, company="别人的公司")
    path = f"/api/v1/applications/{card['id']}"

    for method, url, body in (
        ("get", path, None),
        ("get", f"{path}/events", None),
        ("patch", path, {"status": "applied"}),
        ("delete", path, None),
    ):
        response = await getattr(client, method)(
            url, headers=stranger.headers, **({"json": body} if body else {})
        )
        assert response.status_code == 404, f"{method} {url} → {response.status_code}"
        assert envelope(response, success=False)["error"]["code"] == "NOT_FOUND"

    # And the owner's card is untouched by the attempts.
    still_there = await client.get(path, headers=owner.headers)
    assert still_there.status_code == 200
    assert still_there.json()["data"]["status"] == "wishlist"


async def test_tracking_someone_elses_posting_is_404(
    client: AsyncClient, make_user: UserFactory
) -> None:
    owner = await make_user(display_name="Posting Owner")
    stranger = await make_user(display_name="Posting Stranger")
    job_id = await analyze(client, owner)

    response = await client.post(f"/api/v1/jobs/{job_id}/applications", headers=stranger.headers)
    assert response.status_code == 404, response.text

    mine = await client.post(f"/api/v1/jobs/{job_id}/applications", headers=owner.headers)
    assert mine.status_code == 201, mine.text


async def test_the_job_address_builds_the_card_from_the_posting(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """No body needed: the common case is one click from the analysis page."""
    account = await make_user()
    job_id = await analyze(client, account)

    response = await client.post(
        f"/api/v1/jobs/{job_id}/applications?",
        headers=account.headers,
        content=b"",
    )
    assert response.status_code == 201, response.text
    card = response.json()["data"]
    assert card["role"] == "嵌入式软件工程师"
    assert card["status"] == "wishlist"


async def test_listing_filters_by_status(client: AsyncClient, make_user: UserFactory) -> None:
    account = await make_user()
    kept = await track(client, account, company="留下的")
    moved = await track(client, account, company="移动的")
    await move(client, account, str(moved["id"]), "offer")

    listed = await client.get("/api/v1/applications?status=wishlist", headers=account.headers)
    assert listed.status_code == 200, listed.text
    assert [card["id"] for card in listed.json()["data"]] == [kept["id"]]
