"""Application tracker models: ``/applications`` (``docs/API.md`` §2.9).

The board is returned as **columns in the documented order**, not as a flat list the
client has to group. ``docs/PRD.md`` FR-13.1 fixes seven columns and their sequence, and
a client that has to know the sequence to draw the board will eventually disagree with
the server about it — so the server states it.

``ApplicationResponse.match_score`` is a *snapshot*, copied from the system's own last
computed match when the card was created. It is not accepted on input and it does not
follow later matches: it answers "how well did this look when I decided to apply", which
is the question a board is for.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "APPLICATION_STATUS_VALUES",
    "ApplicationBoardResponse",
    "ApplicationColumn",
    "ApplicationCreateRequest",
    "ApplicationDetailResponse",
    "ApplicationEventResponse",
    "ApplicationResponse",
    "ApplicationUpdateRequest",
    "ReorderItem",
    "ReorderRequest",
]

#: Mirrors ``models.application.APPLICATION_STATUSES``. Declared as a literal so the
#: OpenAPI schema carries an enum; ``test_applications.py`` asserts the two agree, so
#: this cannot drift into being merely decorative.
APPLICATION_STATUS_VALUES = (
    "wishlist",
    "applied",
    "oa",
    "interview",
    "final",
    "offer",
    "rejected",
)

ApplicationStatus = Literal["wishlist", "applied", "oa", "interview", "final", "offer", "rejected"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ApplicationCreateRequest(_CamelModel):
    """``POST /applications``. Either a ``jobId`` or the manual fields.

    Unknown fields are refused: ``matchScore`` is deliberately not accepted — the score
    on a card comes from the stored match, not from the client.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    job_id: str | None = Field(default=None, alias="jobId")
    company: str = Field(default="", max_length=200)
    role: str = Field(default="", max_length=200)
    location: str | None = Field(default=None, max_length=200)
    status: ApplicationStatus = "wishlist"
    salary_expectation: str | None = Field(default=None, alias="salaryExpectation", max_length=120)
    notes: str = Field(default="", max_length=4000)
    next_action_at: datetime | None = Field(default=None, alias="nextActionAt")
    resume_version_id: str | None = Field(default=None, alias="resumeVersionId")

    @model_validator(mode="after")
    def _needs_an_identity(self) -> ApplicationCreateRequest:
        """A card with no company and no role is unidentifiable on a board."""
        if not self.job_id and not (self.company.strip() or self.role.strip()):
            raise ValueError("provide either jobId or at least one of company/role")
        return self


class ApplicationUpdateRequest(_CamelModel):
    """``PATCH /applications/{id}``. Every field optional; unset means "leave alone".

    ``archived`` is a boolean rather than a timestamp because the caller decides, not the
    clock: ``true`` archives, ``false`` restores.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    status: ApplicationStatus | None = None
    company: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    salary_expectation: str | None = Field(default=None, alias="salaryExpectation", max_length=120)
    notes: str | None = Field(default=None, max_length=4000)
    next_action_at: datetime | None = Field(default=None, alias="nextActionAt")
    resume_version_id: str | None = Field(default=None, alias="resumeVersionId")
    applied_at: datetime | None = Field(default=None, alias="appliedAt")
    archived: bool | None = None
    note: str = Field(default="", max_length=500)


class ReorderItem(_CamelModel):
    """One card's new place: which column, and where in it."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str
    status: ApplicationStatus
    position: int = Field(default=0, ge=0, le=10_000)


class ReorderRequest(_CamelModel):
    """``PATCH /applications/reorder`` — a drag, or a whole board saved at once."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    items: list[ReorderItem] = Field(min_length=1, max_length=200)


class ApplicationEventResponse(_CamelModel):
    id: str
    from_status: str | None = Field(default=None, alias="fromStatus")
    to_status: str = Field(alias="toStatus")
    note: str = ""
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")

    @classmethod
    def from_row(cls, event: Any) -> ApplicationEventResponse:
        return cls(
            id=str(event.id),
            from_status=event.from_status,
            to_status=event.to_status,
            note=event.note,
            occurred_at=event.occurred_at,
        )


class ApplicationResponse(_CamelModel):
    """One card. ``company`` and ``role`` are the snapshot, not a live join."""

    id: str
    job_id: str | None = Field(default=None, alias="jobId")
    resume_version_id: str | None = Field(default=None, alias="resumeVersionId")
    company: str = ""
    role: str = ""
    location: str | None = None
    status: str = "wishlist"
    match_score: float | None = Field(default=None, alias="matchScore")
    salary_expectation: str | None = Field(default=None, alias="salaryExpectation")
    notes: str = ""
    position: int = 0
    applied_at: datetime | None = Field(default=None, alias="appliedAt")
    next_action_at: datetime | None = Field(default=None, alias="nextActionAt")
    archived_at: datetime | None = Field(default=None, alias="archivedAt")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")

    @classmethod
    def from_row(cls, row: Any) -> ApplicationResponse:
        return cls(
            id=str(row.id),
            job_id=str(row.job_id) if row.job_id else None,
            resume_version_id=str(row.resume_version_id) if row.resume_version_id else None,
            company=row.company_name,
            role=row.role,
            location=row.location,
            status=row.status,
            match_score=(
                float(row.match_score_snapshot) if row.match_score_snapshot is not None else None
            ),
            salary_expectation=row.salary_expectation,
            notes=row.notes,
            position=row.position,
            applied_at=row.applied_at,
            next_action_at=row.next_action_at,
            archived_at=row.archived_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class ApplicationDetailResponse(ApplicationResponse):
    """``GET /applications/{id}`` — the card plus its status history."""

    events: list[ApplicationEventResponse] = Field(default_factory=list)

    @classmethod
    def from_row(cls, row: Any, *, events: list[ApplicationEventResponse] | None = None) -> Any:
        base = ApplicationResponse.from_row(row)
        return cls(**base.model_dump(), events=events or [])


class ApplicationColumn(_CamelModel):
    """One board column. ``items`` is already in stored order."""

    status: str
    items: list[ApplicationResponse] = Field(default_factory=list)


class ApplicationBoardResponse(_CamelModel):
    """The whole board, plus the counts the dashboard and the column headers show."""

    columns: list[ApplicationColumn] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    total: int = 0
    archived: int = 0
