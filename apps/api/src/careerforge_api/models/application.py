"""``applications``, ``application_events`` and ``career_events`` — §2.7.

Four decisions this file makes, none of them obvious from the column list:

* **An application snapshots what it pointed at.** ``company_name``, ``role`` and
  ``location`` are copied from the posting at creation time even when ``job_id`` is
  set. A job posting can be deleted (``job_id`` is ``SET NULL``) or edited, and a
  board that silently changes the company on last month's card is worse than one
  that shows what was true when it was created. ``match_score_snapshot`` is the same
  idea for the score: it is the system's own last computed number for that job,
  copied server-side. A client cannot supply one — the score on a card is evidence,
  not a claim.
* **``salary_expectation`` is text.** The candidate writes "25k×15" or "300-400/天",
  and a numeric column would either reject that or force the client to normalise it
  into something the candidate never said.
* **``archived_at`` is not a delete.** ``DELETE`` removes the row ("I never applied");
  archiving keeps it out of the board while its history stays queryable. §1 lists
  soft deletion for this table specifically, and this is what it is for.
* **Events are append-only and carry ``from_status``.** The audit trail is the funnel's
  data source (PHASE 9), so an event must never be rewritten: a correction is another
  event. ``from_status`` is nullable because the creation event has no previous status.

``career_events`` is the human timeline (``docs/DATABASE.md`` §2.11), and only
milestones reach it — applied, interviewed, offered, rejected. Intermediate board moves
(``oa``, ``final``) stay in ``application_events``: a timeline where "moved to OA" sits
beside "graduated" stops being a timeline. Rejected does belong there: an outcome the
candidate would put on a CV timeline is exactly the kind of thing this table is for.
``wishlist`` is not a milestone either, and ``APPLICATION_MILESTONES`` says why.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType

__all__ = [
    "APPLICATION_MILESTONES",
    "APPLICATION_STATUSES",
    "CAREER_EVENT_KINDS",
    "Application",
    "ApplicationEvent",
    "CareerEvent",
]

#: The seven board columns, in the order the board draws them (``docs/PRD.md`` FR-13.1).
#: Order is part of the contract: the client renders exactly this sequence, so a new
#: status cannot appear in the API and be missing from the board.
APPLICATION_STATUSES: tuple[str, ...] = (
    "wishlist",
    "applied",
    "oa",
    "interview",
    "final",
    "offer",
    "rejected",
)

#: Statuses that are closed: nothing further is expected to happen, so a stored
#: ``next_action_at`` would be a reminder for something that cannot occur.
CLOSED_STATUSES: frozenset[str] = frozenset({"offer", "rejected"})

#: Transitions worth putting on a career timeline.
#:
#: ``wishlist`` is deliberately absent. Adding a card to the board is a bookmark, not an act: a
#: timeline that records "投递" when the card is created *and* again when it is actually applied
#: to shows one application twice — and the PHASE 9 trend chart counted it twice, which is how
#: this was found. ``oa`` and ``final`` are board positions rather than milestones, likewise.
APPLICATION_MILESTONES: dict[str, str] = {
    "wishlist": "",
    "applied": "application",
    "oa": "",
    "interview": "interview",
    "final": "interview",
    "offer": "offer",
    "rejected": "application",
}

#: ``docs/DATABASE.md`` §2.11.
CAREER_EVENT_KINDS: tuple[str, ...] = (
    "project",
    "internship",
    "application",
    "interview",
    "offer",
    "skill",
    "education",
)


def _check(column: str, values: tuple[str, ...]) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IN ({', '.join(repr(value) for value in values)})", name=f"{column}_valid"
    )


class Application(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One card on the board."""

    __tablename__ = "applications"
    __table_args__ = (
        _check("status", APPLICATION_STATUSES),
        CheckConstraint(
            "match_score_snapshot IS NULL OR match_score_snapshot BETWEEN 0 AND 100",
            name="match_score_snapshot_range",
        ),
        CheckConstraint("position >= 0", name="position_non_negative"),
        Index("ix_applications_user_id_status_position", "user_id", "status", "position"),
        Index("ix_applications_user_id_next_action_at", "user_id", "next_action_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Nullable: an application can be tracked before any posting exists in the system.
    job_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resume_version_id: Mapped[UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("resume_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    #: Snapshot of the posting's identity at creation time; the only company there is
    #: when no posting is linked.
    company_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(Text, nullable=False, default="wishlist")
    #: ``jobs`` score at the moment the card was created. ``None`` means no match had
    #: been computed yet — reported as unknown, never as zero.
    match_score_snapshot: Mapped[Decimal | None] = mapped_column(NumericType(5, 2), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)
    next_action_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)
    salary_expectation: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Sort key within a column. Dense from 0 per ``(user, status)`` after every write.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    archived_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)

    events: Mapped[list[ApplicationEvent]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ApplicationEvent.occurred_at",
    )

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def is_open(self) -> bool:
        """Whether anything is still expected to happen to this application."""
        return self.status not in CLOSED_STATUSES


class ApplicationEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One status change. Append-only — a correction is another row, not an edit."""

    __tablename__ = "application_events"
    __table_args__ = (
        _check("to_status", APPLICATION_STATUSES),
        CheckConstraint(
            "from_status IS NULL OR from_status IN "
            f"({', '.join(repr(value) for value in APPLICATION_STATUSES)})",
            name="from_status_valid",
        ),
        Index(
            "ix_application_events_application_id_occurred_at",
            "application_id",
            "occurred_at",
        ),
    )

    application_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: ``None`` on the creation event: there was no previous status.
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    occurred_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)

    application: Mapped[Application] = relationship(back_populates="events")


class CareerEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A milestone on the candidate's timeline (``docs/DATABASE.md`` §2.11).

    ``ref_type`` / ``ref_id`` point at whatever produced it without a foreign key: the
    timeline outlives the rows it describes, and a cascade that quietly deleted a
    graduation because a job posting was removed would be the wrong behaviour.
    """

    __tablename__ = "career_events"
    __table_args__ = (
        _check("kind", CAREER_EVENT_KINDS),
        Index("ix_career_events_user_id_occurred_at", "user_id", "occurred_at"),
        UniqueConstraint("user_id", "dedupe_key", name="uq_career_events_user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    ref_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_id: Mapped[UUID | None] = mapped_column(UUIDType, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict, name="metadata"
    )
    #: ``<kind>:<ref_id>:<status>`` — one milestone per application per status, so a
    #: card dragged back and forth does not write the same milestone repeatedly.
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
