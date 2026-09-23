"""Type compatibility layer: one set of ORM models for two database backends.

``docs/DATABASE.md`` §5 fixes the mapping this module implements:

===============  ==================  ==========================  ==============================
logical type     PostgreSQL          SQLite                      mechanism
===============  ==================  ==========================  ==============================
``UUIDType``     ``uuid``            ``CHAR(36)``                ``TypeDecorator``, both ways
``JSONType``     ``jsonb``           ``TEXT`` (JSON)             ``with_variant`` semantics
``TimestampType`` ``timestamptz``    ``DATETIME``                UTC normalised on read/write
``NumericType``  ``numeric(p,s)``    ``NUMERIC``                 always ``Decimal`` in Python
===============  ==================  ==========================  ==============================

Every decorator below declares ``cache_ok = True`` and picks its dialect-specific
representation in ``load_dialect_impl``. That is the same thing
``JSON().with_variant(JSONB, "postgresql")`` does, expressed as a class so the
models can import one name and stay dialect-agnostic.

The point of the exercise is that ``alembic upgrade head`` and
``Base.metadata.create_all()`` produce the same schema on both backends, which is
what the CI matrix in ``.github/workflows/ci.yml`` asserts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CHAR, DateTime, JSON, Numeric
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import TypeDecorator, TypeEngine

__all__ = ["JSONType", "NumericType", "TimestampType", "UUIDType", "utcnow"]


def utcnow() -> datetime:
    """Timezone-aware UTC ``now`` — the only clock the API uses."""
    return datetime.now(UTC)


class UUIDType(TypeDecorator):
    """``uuid`` on PostgreSQL, ``CHAR(36)`` with explicit conversion on SQLite."""

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, UUID):
            value = UUID(str(value))
        # asyncpg handles UUID objects natively; SQLite needs the canonical text form.
        return value if dialect.name == "postgresql" else str(value)

    def process_result_value(self, value: Any, dialect: Any) -> UUID | None:
        if value is None:
            return None
        return value if isinstance(value, UUID) else UUID(str(value))


class JSONType(TypeDecorator):
    """``jsonb`` on PostgreSQL, ``JSON`` (TEXT) on SQLite.

    No bind/result processing is needed: SQLAlchemy's ``JSON`` already serialises on
    the way in and deserialises on the way out for both dialects, and ``JSONB``
    keeps the same Python ``dict``/``list`` shapes.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(JSON())


class TimestampType(TypeDecorator):
    """``timestamptz`` on PostgreSQL, naive-UTC ``DATETIME`` on SQLite.

    SQLite has no timezone type, so values are converted to UTC on the way in and
    re-tagged as UTC on the way out. Nothing in the API ever sees a naive datetime
    (``docs/DATABASE.md`` §1.1, rule 4).
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[Any]:
        return dialect.type_descriptor(DateTime(timezone=dialect.name == "postgresql"))

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError(f"expected datetime, got {type(value).__name__}")
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        aware = value.astimezone(UTC)
        return aware if dialect.name == "postgresql" else aware.replace(tzinfo=None)

    def process_result_value(self, value: Any, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class NumericType(TypeDecorator):
    """``numeric(p, s)`` on both backends, always surfaced as :class:`Decimal`.

    SQLite stores ``NUMERIC`` with dynamic typing (``docs/DATABASE.md`` §5), so the
    Python side normalises to ``Decimal`` to keep the API's arithmetic exact.
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int = 10, scale: int = 3) -> None:
        self.precision = precision
        self.scale = scale
        super().__init__(precision=precision, scale=scale, asdecimal=True)

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[Any]:
        return dialect.type_descriptor(
            Numeric(precision=self.precision, scale=self.scale, asdecimal=True)
        )

    def process_bind_param(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        # ``str`` avoids the binary-float surprise of ``Decimal(0.1)``.
        return Decimal(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return value if isinstance(value, Decimal) else Decimal(str(value))
