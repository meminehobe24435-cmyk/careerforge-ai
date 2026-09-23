"""``/applications`` — the tracker board (``docs/API.md`` §2.9, ``docs/PRD.md`` FR-13).

Two things about this surface are deliberate:

* **Route order matters.** ``/applications/board`` and ``/applications/reorder`` are
  declared before ``/applications/{application_id}``: a literal path registered after a
  parameterised one is unreachable, and the failure mode is a confusing "Application not
  found" for the word "board".
* **No endpoint accepts a score.** ``matchScore`` is snapshotted from the stored match at
  creation (``services/application_service.py``). A client that could post a score could
  put "92% match" on a card for a job the system never scored.

``POST /jobs/{job_id}/applications`` (FR-13.5, "add to applications" from the analysis
page) is mounted from here rather than in ``routers/jobs.py``: it is the tracker's write
path that happens to be addressed by job, and splitting the implementation across two
modules is how the two addresses drift apart.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from careerforge_api.core.errors import NotFoundError
from careerforge_api.deps import CurrentUser, DbSession
from careerforge_api.schemas.applications import (
    APPLICATION_STATUS_VALUES,
    ApplicationBoardResponse,
    ApplicationColumn,
    ApplicationCreateRequest,
    ApplicationDetailResponse,
    ApplicationEventResponse,
    ApplicationResponse,
    ApplicationUpdateRequest,
    ReorderRequest,
)
from careerforge_api.services.application_service import ApplicationService

__all__ = ["job_router", "router"]

router = APIRouter(prefix="/applications", tags=["applications"])
#: ``POST /jobs/{id}/applications`` — mounted under the jobs prefix, implemented here.
job_router = APIRouter(tags=["applications"])


def _parse_uuid(raw: str, *, what: str) -> UUID:
    """A malformed id is a 404, not a 422: the API never confirms which ids exist."""
    try:
        return UUID(raw)
    except ValueError as exc:
        raise NotFoundError(f"{what} not found") from exc


def _card(row: object) -> ApplicationResponse:
    return ApplicationResponse.from_row(row)


@router.get("", summary="The tracked applications")
async def list_applications(
    session: DbSession,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False, alias="includeArchived"),
) -> list[ApplicationResponse]:
    rows = await ApplicationService(session).list_for_user(
        user=user, status=status_filter, include_archived=include_archived
    )
    return [_card(row) for row in rows]


@router.get("/board", summary="The board: seven columns in the documented order")
async def get_board(
    session: DbSession,
    user: CurrentUser,
    include_archived: bool = Query(default=False, alias="includeArchived"),
) -> ApplicationBoardResponse:
    """Every column is present, even when empty.

    An empty column is information — it says nothing has reached that stage — whereas a
    missing key forces the client to guess, and a client that guesses draws a board with
    the wrong columns the day a stage is added.
    """
    board = await ApplicationService(session).board(user=user, include_archived=include_archived)
    return ApplicationBoardResponse(
        columns=[
            ApplicationColumn(status=name, items=[_card(row) for row in board.columns[name]])
            for name in APPLICATION_STATUS_VALUES
        ],
        counts=board.counts,
        total=board.total,
        archived=board.archived,
    )


@router.patch("/reorder", summary="Apply drag-and-drop placements")
async def reorder_applications(
    payload: ReorderRequest, session: DbSession, user: CurrentUser
) -> list[ApplicationResponse]:
    """Declared before ``/{application_id}`` so "reorder" is not read as an id."""
    service = ApplicationService(session)
    rows = await service.reorder(
        user=user,
        items=[
            {"id": item.id, "status": item.status, "position": item.position}
            for item in payload.items
        ],
    )
    return [_card(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED, summary="Track an application")
async def create_application(
    payload: ApplicationCreateRequest, session: DbSession, user: CurrentUser
) -> ApplicationResponse:
    row = await ApplicationService(session).create(
        user=user,
        job_id=_uuid_or_none(payload.job_id, what="Job"),
        company=payload.company,
        role=payload.role,
        location=payload.location,
        status=payload.status,
        salary_expectation=payload.salary_expectation,
        notes=payload.notes,
        next_action_at=payload.next_action_at,
        resume_version_id=_uuid_or_none(payload.resume_version_id, what="Resume version"),
    )
    return _card(row)


@router.get("/{application_id}", summary="One card with its status history")
async def get_application(
    application_id: str, session: DbSession, user: CurrentUser
) -> ApplicationDetailResponse:
    service = ApplicationService(session)
    row = await service.require(_parse_uuid(application_id, what="Application"), user=user)
    events = await service.events_of(application=row)
    return ApplicationDetailResponse.from_row(
        row, events=[ApplicationEventResponse.from_row(event) for event in events]
    )


@router.patch("/{application_id}", summary="Update fields, move the card, or archive it")
async def update_application(
    application_id: str,
    payload: ApplicationUpdateRequest,
    session: DbSession,
    user: CurrentUser,
) -> ApplicationDetailResponse:
    """A status change writes an event; a change to the same status writes nothing."""
    service = ApplicationService(session)
    row = await service.require(_parse_uuid(application_id, what="Application"), user=user)
    fields = payload.model_dump(exclude_unset=True, exclude={"note"})
    await service.update(user=user, application=row, fields=fields, note=payload.note)
    events = await service.events_of(application=row)
    return ApplicationDetailResponse.from_row(
        row, events=[ApplicationEventResponse.from_row(event) for event in events]
    )


@router.get("/{application_id}/events", summary="Status history, newest first")
async def list_events(
    application_id: str, session: DbSession, user: CurrentUser
) -> list[ApplicationEventResponse]:
    service = ApplicationService(session)
    row = await service.require(_parse_uuid(application_id, what="Application"), user=user)
    events = await service.events_of(application=row)
    return [ApplicationEventResponse.from_row(event) for event in events]


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a card and its history",
)
async def delete_application(application_id: str, session: DbSession, user: CurrentUser) -> None:
    service = ApplicationService(session)
    row = await service.require(_parse_uuid(application_id, what="Application"), user=user)
    await service.delete(application=row)


@job_router.post(
    "/jobs/{job_id}/applications",
    status_code=status.HTTP_201_CREATED,
    summary="Add a job from the analysis page to the board",
)
async def track_job(
    job_id: str,
    session: DbSession,
    user: CurrentUser,
    payload: ApplicationCreateRequest | None = None,
) -> ApplicationResponse:
    """FR-13.5 — one click from "I analysed this posting" to "I am tracking it".

    The body is optional: the common case is a card built entirely from the stored
    posting, and requiring the client to echo the company back would give the board's
    company a chance to differ from the analysis page's for no reason. **The URL owns the
    job id** — a body naming a different one cannot point the card somewhere else than the
    path says.
    """
    body = payload or ApplicationCreateRequest(job_id=job_id, role="")
    row = await ApplicationService(session).create(
        user=user,
        job_id=_parse_uuid(job_id, what="Job"),
        company=body.company,
        role=body.role,
        location=body.location,
        status=body.status,
        salary_expectation=body.salary_expectation,
        notes=body.notes,
        next_action_at=body.next_action_at,
        resume_version_id=_uuid_or_none(body.resume_version_id, what="Resume version"),
    )
    return _card(row)


def _uuid_or_none(raw: str | None, *, what: str) -> UUID | None:
    if raw is None or not raw.strip():
        return None
    return _parse_uuid(raw, what=what)
