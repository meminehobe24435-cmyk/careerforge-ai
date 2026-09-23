"""What the tracker records: moves, reorders, and the career timeline.

These are the assertions the funnel in PHASE 9 depends on, so they are separated from the
CRUD surface, where a missing event would just look like a missing field:

* **Every status change writes an event**, and a move to the *same* status writes none —
  otherwise the funnel counts one application several times.
* **A drag re-derives the column's order server-side.** The client is a hostile source of
  ordering data: an interrupted gesture produces duplicate and gapped positions.
* **``applied_at`` is stamped once and not erased by a rewind**, and a closed card drops
  its next action.
* **A milestone reaches the timeline once**, however often the card is dragged.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select

from careerforge_api.models.application import ApplicationEvent, CareerEvent
from tests.application_support import list_events, move, track
from tests.conftest import UserFactory

# ── moving ───────────────────────────────────────────────────────────────────


async def test_moving_a_card_records_the_transition_once(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    account = await make_user()
    card = await track(client, account)
    await move(client, account, str(card["id"]), "applied", note="官网投递")
    await move(client, account, str(card["id"]), "interview")

    events = await list_events(client, account, str(card["id"]))
    transitions = [(event["fromStatus"], event["toStatus"]) for event in events]
    assert transitions == [
        ("applied", "interview"),
        ("wishlist", "applied"),
        (None, "wishlist"),
    ], "newest first, and one row per move"
    assert events[-1]["note"] == "加入投递看板", "the creation event's note explains itself"
    assert events[1]["note"] == "官网投递", "the note travels with the move that carried it"

    async with app.state.session_factory() as db:
        stored = await db.scalar(
            select(func.count())
            .select_from(ApplicationEvent)
            .where(
                ApplicationEvent.user_id == account.id,
                ApplicationEvent.to_status == "applied",
            )
        )
    assert stored == 1, "the shared test database holds other accounts' events too"


async def test_moving_a_card_to_its_own_column_writes_nothing(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """A reorder is not a move. Otherwise the funnel counts one application repeatedly."""
    account = await make_user()
    card = await track(client, account)
    before = await list_events(client, account, str(card["id"]))

    await move(client, account, str(card["id"]), "wishlist", notes="重新排序而已")
    after = await list_events(client, account, str(card["id"]))

    assert len(after) == len(before) == 1
    detail = await client.get(f"/api/v1/applications/{card['id']}", headers=account.headers)
    assert detail.json()["data"]["notes"] == "重新排序而已", "the field change still applied"


async def test_applying_stamps_the_date_and_rewinding_does_not_erase_it(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    card = await track(client, account)
    assert card["appliedAt"] is None

    moved = await move(client, account, str(card["id"]), "applied")
    stamped = moved["appliedAt"]
    assert stamped is not None

    rewound = await move(client, account, str(card["id"]), "wishlist")
    assert rewound["appliedAt"] == stamped, (
        "rewinding corrects the board; it is not a denial that the application happened"
    )


async def test_a_closed_card_drops_its_next_action(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """Nothing further is expected after an offer or a rejection."""
    account = await make_user()
    card = await track(client, account)
    await move(client, account, str(card["id"]), "applied")
    with_action = await client.patch(
        f"/api/v1/applications/{card['id']}",
        json={"nextActionAt": "2026-03-01T09:00:00+00:00"},
        headers=account.headers,
    )
    assert with_action.status_code == 200, with_action.text
    assert with_action.json()["data"]["nextActionAt"] is not None

    offered = await move(client, account, str(card["id"]), "offer")
    assert offered["nextActionAt"] is None, "an offer needs no reminder to chase the offer"


# ── reordering ───────────────────────────────────────────────────────────────


async def test_reorder_is_its_own_route_not_an_id(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """``/applications/reorder`` is declared before ``/{application_id}``.

    Registered the other way round, "reorder" would be parsed as an id and the endpoint
    would answer "Application not found" for its own documented path.
    """
    account = await make_user()
    card = await track(client, account)
    response = await client.patch(
        "/api/v1/applications/reorder",
        json={"items": [{"id": card["id"], "status": "oa", "position": 0}]},
        headers=account.headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"][0]["status"] == "oa"


async def test_reorder_rederives_dense_positions(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """The client is a hostile source of ordering data; the server re-derives the order."""
    account = await make_user()
    cards = [await track(client, account, company=f"公司{index}") for index in range(3)]

    # Reverse the column with positions that overlap, as an interrupted gesture would.
    response = await client.patch(
        "/api/v1/applications/reorder",
        json={
            "items": [
                {"id": cards[0]["id"], "status": "wishlist", "position": 2},
                {"id": cards[1]["id"], "status": "wishlist", "position": 1},
                {"id": cards[2]["id"], "status": "wishlist", "position": 0},
            ]
        },
        headers=account.headers,
    )
    assert response.status_code == 200, response.text

    board = (await client.get("/api/v1/applications/board", headers=account.headers)).json()["data"]
    column = board["columns"][0]["items"]
    assert [card["company"] for card in column] == ["公司2", "公司1", "公司0"]
    assert [card["position"] for card in column] == [0, 1, 2], "dense from zero"


async def test_a_drag_between_columns_writes_an_event_and_a_within_column_drag_does_not(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    first = await track(client, account, company="甲")
    second = await track(client, account, company="乙")

    reorder = await client.patch(
        "/api/v1/applications/reorder",
        json={
            "items": [
                {"id": second["id"], "status": "interview", "position": 0},
            ]
        },
        headers=account.headers,
    )
    assert reorder.status_code == 200, reorder.text
    assert [
        event["toStatus"] for event in await list_events(client, account, str(second["id"]))
    ] == [
        "interview",
        "wishlist",
    ]

    # Now drag within the wishlist column only.
    within = await client.patch(
        "/api/v1/applications/reorder",
        json={"items": [{"id": first["id"], "status": "wishlist", "position": 0}]},
        headers=account.headers,
    )
    assert within.status_code == 200, within.text
    assert len(await list_events(client, account, str(first["id"]))) == 1


async def test_a_milestone_is_recorded_once_however_often_the_card_moves(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """A timeline that inflates itself when a card is dragged back and forth is not one."""
    account = await make_user()
    card = await track(client, account)
    for status in ("applied", "interview", "applied", "interview", "offer"):
        await move(client, account, str(card["id"]), status)

    async with app.state.session_factory() as db:
        rows = (await db.scalars(select(CareerEvent).where(CareerEvent.ref_id == card["id"]))).all()
        kinds = sorted(row.kind for row in rows)

    assert kinds == ["application", "application", "interview", "offer"], (
        "wishlist, applied, one interview (not two), offer — deduped by status"
    )
