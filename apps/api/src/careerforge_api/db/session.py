"""Async engine and session factory construction.

The URL is never assembled here: :attr:`careerforge_ai.config.Settings.resolved_database_url`
already applies the SQLite fallback (ADR-004), so this module only turns that URL
into an engine and applies the SQLite pragmas ``docs/DATABASE.md`` §5 requires.

``PRAGMA journal_mode=WAL`` (concurrent readers), ``foreign_keys=ON`` (SQLite ships
FK enforcement **off**, which would silently break every ``ON DELETE CASCADE`` in
the schema) and ``busy_timeout=5000`` (bounded wait instead of an immediate
"database is locked") are attached with a ``connect`` event listener, so every
connection in the pool gets them — including connections created after a fork or a
recycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from careerforge_api.core.config import APISettings

__all__ = [
    "create_all",
    "create_engine",
    "create_engine_for_url",
    "create_session_factory",
    "ensure_sqlite_directory",
    "is_sqlite_url",
    "ping",
    "session_scope",
]

#: Pragmas from ``docs/DATABASE.md`` §5, applied to every SQLite connection.
SQLITE_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
    "PRAGMA synchronous=NORMAL",
)


def is_sqlite_url(url: str) -> bool:
    return make_url(url).get_backend_name() == "sqlite"


def ensure_sqlite_directory(url: str) -> Path | None:
    """Create the parent directory of a file-backed SQLite database.

    Without this a fresh checkout fails with "unable to open database file" the
    first time ``data/careerforge.db`` is opened.
    """
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database:
        return None
    if parsed.database == ":memory:":
        return None
    path = Path(parsed.database)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _install_sqlite_pragmas(engine: AsyncEngine) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            for pragma in SQLITE_PRAGMAS:
                cursor.execute(pragma)
        finally:
            cursor.close()


def create_engine_for_url(url: str, *, echo: bool = False) -> AsyncEngine:
    """Build an async engine for an explicit URL, applying the SQLite pragmas.

    Split out from :func:`create_engine` so the Alembic environment can reuse the
    identical connection setup (pragmas, directory creation, pooling) instead of
    duplicating it in ``alembic/env.py``.
    """
    options: dict[str, Any] = {"echo": echo, "future": True}

    if is_sqlite_url(url):
        ensure_sqlite_directory(url)
        # NullPool: a file-backed SQLite database is cheap to open and this keeps
        # no idle handles around (important for tests that delete the file).
        options["poolclass"] = NullPool
        options["connect_args"] = {"timeout": 30}
    else:
        options["pool_pre_ping"] = True

    engine = create_async_engine(url, **options)
    if is_sqlite_url(url):
        _install_sqlite_pragmas(engine)
    return engine


def create_engine(settings: APISettings) -> AsyncEngine:
    """Build the async engine for ``settings.resolved_database_url``."""
    return create_engine_for_url(settings.resolved_database_url, echo=settings.sql_echo)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory.

    ``expire_on_commit=False`` so a serialised response can read attributes after
    the request's transaction committed; that is what keeps the read path free of
    surprise lazy loads (which an async session cannot perform anyway).
    """
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Transactional session for code without a request scope (seeds, workers)."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ping(engine: AsyncEngine) -> None:
    """``SELECT 1`` — the database probe behind ``GET /system/health``."""
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


def _metadata() -> Any:
    # Imported lazily so ``careerforge_api.db.session`` can be imported by models
    # without a cycle, while still seeing every table at ``create_all`` time.
    from careerforge_api.models import Base

    return Base.metadata


async def create_all(engine: AsyncEngine) -> None:
    """Create the PHASE 1 tables if they do not exist.

    Used on the zero-dependency SQLite path so ``USE_SQLITE=true`` needs no
    migration step; PostgreSQL deployments run ``alembic upgrade head`` instead
    (``docs/DATABASE.md`` §6). Both produce the same schema — asserted by
    ``tests/test_migrations.py``.
    """
    metadata = _metadata()
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
