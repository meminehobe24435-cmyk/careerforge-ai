"""Alembic environment: async-aware, configured from the AI core's settings.

The database URL is **not** duplicated in ``alembic.ini``: it comes from
``careerforge_ai.config.Settings.resolved_database_url``, the same resolution the API
and the tests use (ADR-004). That is what makes

    USE_SQLITE=true alembic upgrade head

and

    DATABASE_URL=postgresql+asyncpg://... alembic upgrade head

behave identically, with no second source of truth to keep in sync.

``-x db_url=<async url>`` overrides the settings for one invocation, which is how the
CI matrix can migrate a database that is not the process default.

The engine is built through ``careerforge_api.db.session.create_engine_for_url`` so
the SQLite pragmas (WAL, ``foreign_keys=ON``, ``busy_timeout``) are in effect while
migrating too — without them a migration could not create the ``ON DELETE CASCADE``
foreign keys it declares.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context

from careerforge_api.core.config import APISettings, get_api_settings
from careerforge_api.db.session import create_engine_for_url
from careerforge_api.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

#: Autogenerate compares against the ORM metadata, which is why the models are imported.
target_metadata = Base.metadata


def _settings() -> APISettings:
    return get_api_settings()


def _database_url(settings: APISettings) -> str:
    """Resolution order: ``-x db_url=...``, then ``sqlalchemy.url``, then settings.

    The middle step is what lets a test or a CI job drive migrations
    programmatically (``Config.set_main_option("sqlalchemy.url", ...)``) without
    mutating the process environment.
    """
    overrides = context.get_x_argument(as_dictionary=True)
    override = (overrides.get("db_url") or "").strip()
    if override:
        return override
    configured = (config.get_main_option("sqlalchemy.url") or "").strip()
    if configured:
        return configured
    return settings.resolved_database_url


def run_migrations_offline() -> None:
    """``--sql`` mode: emit the DDL without connecting.

    Offline mode needs a synchronous DBAPI for PostgreSQL, so it is only fully usable
    against SQLite (whose driver is in the standard library). Documented in the
    migration guide rather than worked around.
    """
    settings = _settings()
    url = _database_url(settings)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    context.configure(
        connection=connection,  # type: ignore[arg-type]
        target_metadata=target_metadata,
        compare_type=True,
        # SQLite cannot ALTER most things; batch mode rewrites the table instead.
        render_as_batch=connection.dialect.name == "sqlite",  # type: ignore[attr-defined]
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    settings = _settings()
    engine = create_engine_for_url(_database_url(settings))
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
