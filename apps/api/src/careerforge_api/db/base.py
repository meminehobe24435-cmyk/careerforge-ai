"""Declarative base, naming convention and shared column mixins.

``docs/DATABASE.md`` §1.2 fixes the naming scheme (``ix_<table>_<cols>``,
``uq_<table>_<cols>``, ``ck_<table>_<rule>``), and §1.1 fixes the columns every
business table carries (``id``, ``user_id``, ``created_at``, ``updated_at``).

The naming convention is declared here — once — so autogenerate, ``create_all`` and
the Alembic baseline all agree on constraint names. That agreement is what makes
the migration-vs-models equivalence test possible: a mismatch is a hard failure
rather than a silent schema drift.

Because the convention includes ``%(constraint_name)s``, every ``CheckConstraint``
in the models **must** be given an explicit short name; SQLAlchemy raises otherwise,
which is a useful guardrail against anonymous constraints sneaking in.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from careerforge_api.db.compat import TimestampType, UUIDType, utcnow

__all__ = [
    "NAMING_CONVENTION",
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
]

#: See ``docs/DATABASE.md`` §1.2.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(referred_table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every PHASE 1 table."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        identifier = getattr(self, "id", None)
        return f"<{type(self).__name__} id={identifier}>"


class UUIDPrimaryKeyMixin:
    """``id uuid primary key`` — ``docs/DATABASE.md`` §1.1.

    ``gen_random_uuid()`` in PostgreSQL is replaced by a client-side default so the
    same insert path works on SQLite without a database extension.
    """

    id: Mapped[UUID] = mapped_column(UUIDType, primary_key=True, default=uuid4)


class TimestampMixin:
    """``created_at`` / ``updated_at`` in UTC, maintained by the ORM.

    ``docs/DATABASE.md`` §1.1 allows either a trigger or ORM events; ORM events are
    used here so the behaviour is identical on both backends.
    """

    created_at: Mapped[datetime] = mapped_column(TimestampType, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TimestampType, nullable=False, default=utcnow, onupdate=utcnow
    )
