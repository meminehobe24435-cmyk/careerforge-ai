"""Seed the database with everything PHASE 1 needs, safely re-runnable.

``docs/DATABASE.md`` §6 asks for ``scripts/seed.py``: idempotent, ``--reset`` to
rebuild, and usable in CI. This entrypoint is a thin wrapper around the same
:func:`careerforge_api.services.seed_service.seed_all` the API calls during startup, so
the seeded state can never differ between a fresh boot and a scripted seed.

Usage (from the repository root)::

    $env:USE_SQLITE="true"
    .\\.venv\\Scripts\\python.exe scripts\\seed.py
    .\\.venv\\Scripts\\python.exe scripts\\seed.py --reset --yes

On PostgreSQL the schema is expected to exist already (``alembic upgrade head``,
``docs/DATABASE.md`` §6); on SQLite the tables are created if missing so the
zero-dependency path needs no migration step.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))

from careerforge_api.core.config import APISettings, get_api_settings  # noqa: E402
from careerforge_api.core.logging import configure_logging  # noqa: E402
from careerforge_api.db.base import Base  # noqa: E402
from careerforge_api.db.session import (  # noqa: E402
    create_all,
    create_engine,
    create_session_factory,
    session_scope,
)
from careerforge_api.services.seed_service import seed_all  # noqa: E402

__all__ = ["main", "reset_database", "run"]


async def reset_database(settings: APISettings) -> list[str]:
    """Drop and recreate every table. Returns the table names affected.

    Only meaningful for the SQLite path (and for CI, which wants a clean slate); a
    shared PostgreSQL database is never dropped by a seed script, so ``--reset``
    refuses there unless ``--force-postgres`` is given explicitly.
    """
    engine = create_engine(settings)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
        await create_all(engine)
    finally:
        await engine.dispose()
    return sorted(Base.metadata.tables)


async def run(*, reset: bool = False, force_postgres: bool = False) -> dict[str, object]:
    settings = get_api_settings()
    if settings.use_sqlite:
        engine = create_engine(settings)
        try:
            if reset:
                await reset_database(settings)
            else:
                await create_all(engine)
        finally:
            await engine.dispose()
    elif reset and not force_postgres:
        raise SystemExit(
            "--reset would drop tables in a PostgreSQL database; re-run with "
            "--force-postgres if that is really what you want"
        )

    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with session_scope(factory) as session:
            report = await seed_all(session, settings)
        return {
            "database": settings.resolved_database_url,
            "useSqlite": settings.use_sqlite,
            **report.as_dict(),
        }
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the CareerForge AI database.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate tables first")
    parser.add_argument(
        "--force-postgres",
        action="store_true",
        help="allow --reset against PostgreSQL (drops every table)",
    )
    parser.add_argument("--yes", action="store_true", help="skip the reset confirmation")
    args = parser.parse_args(argv)

    if args.reset and not args.yes and not args.force_postgres:
        answer = input("--reset drops every table. Type 'reset' to continue: ").strip()
        if answer != "reset":
            print("aborted")
            return 1

    settings = get_api_settings()
    configure_logging(settings)
    report = asyncio.run(run(reset=args.reset, force_postgres=args.force_postgres))

    print("seed complete")
    for key, value in report.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
