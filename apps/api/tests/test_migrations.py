"""The Alembic baseline and ``create_all`` must produce the same schema.

This is the guarantee that lets the zero-dependency path skip migrations: SQLite is
created with ``Base.metadata.create_all()`` while Docker and CI run
``alembic upgrade head``, so if the two ever diverged, the local demo and the deployed
system would be different products.

The comparison is structural and dialect-level: table set, column order/type/
nullability, index names, unique constraints, foreign keys (target + ``ON DELETE``)
and ``CHECK`` constraint names, read straight out of ``sqlite_master``/``PRAGMA`` for
both database files.

The test is **synchronous** on purpose — Alembic's ``env.py`` runs its own event loop,
which cannot be nested inside a running one.
"""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from careerforge_api.models import Base

APPS_API = Path(__file__).resolve().parents[1]
ALEMBIC_INI = APPS_API / "alembic.ini"

_CHECK_RE = re.compile(r'CONSTRAINT\s+"?(\w+)"?\s+CHECK', re.IGNORECASE)


def _describe(database: Path) -> dict[str, Any]:
    """Structural description of a SQLite file, ignoring Alembic's bookkeeping table."""
    connection = sqlite3.connect(database)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            if row[0] != "alembic_version" and not row[0].startswith("sqlite_")
        ]
        description: dict[str, Any] = {}
        for table in tables:
            columns = [
                (row[1], row[2].upper(), bool(row[3]), bool(row[5]))
                for row in connection.execute(f"PRAGMA table_info('{table}')")
            ]
            index_rows = list(connection.execute(f"PRAGMA index_list('{table}')"))
            indexes = sorted(
                row[1] for row in index_rows if row[1] and not row[1].startswith("sqlite_autoindex")
            )
            uniques = sorted(
                tuple(
                    sorted(
                        column[2] for column in connection.execute(f"PRAGMA index_info('{row[1]}')")
                    )
                )
                for row in index_rows
                if row[3] == 1 and not row[1].startswith("sqlite_autoindex")
            )
            foreign_keys = sorted(
                (row[3], row[2], row[6])
                for row in connection.execute(f"PRAGMA foreign_key_list('{table}')")
            )
            ddl = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()[0]
            checks = sorted(_CHECK_RE.findall(ddl or ""))
            description[table] = {
                "columns": columns,
                "indexes": indexes,
                "uniques": uniques,
                "foreign_keys": foreign_keys,
                "checks": checks,
            }
        return description
    finally:
        connection.close()


def _migrated_database(tmp_path: Path) -> Path:
    """Run ``alembic upgrade head`` against a throwaway SQLite file."""
    target = tmp_path / "migrated.db"
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{target.as_posix()}")
    command.upgrade(config, "head")
    return target


def _declared_database(tmp_path: Path) -> Path:
    """Create the same schema from the ORM models."""
    target = tmp_path / "declared.db"
    engine = create_engine(f"sqlite:///{target.as_posix()}", poolclass=NullPool)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    return target


def test_alembic_baseline_matches_the_models(tmp_path: Path) -> None:
    migrated = _describe(_migrated_database(tmp_path))
    declared = _describe(_declared_database(tmp_path))

    assert set(migrated) == set(declared), "table sets differ"
    for table in sorted(declared):
        for aspect in ("columns", "indexes", "uniques", "foreign_keys", "checks"):
            assert migrated[table][aspect] == declared[table][aspect], (
                f"{table}.{aspect} differs:\n"
                f"  migration: {migrated[table][aspect]}\n"
                f"  models:    {declared[table][aspect]}"
            )


def test_alembic_downgrade_removes_everything(tmp_path: Path) -> None:
    """docs/DATABASE.md §6: every migration implements a working ``downgrade()``."""
    target = tmp_path / "roundtrip.db"
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{target.as_posix()}")
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    assert _describe(target) == {}


def test_alembic_revision_id_is_the_documented_head() -> None:
    """The head is a deliberate list, not a wildcard: a migration that appears without
    its phase being finished should fail this test, not silently become the head."""
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert script.get_heads() == ["0007"]
    for revision in (
        "0001_initial",
        "0002_documents",
        "0003_evidence",
        "0004_jobs",
        "0005_profile_entities",
        "0006_resume",
        "0007_applications",
    ):
        assert (APPS_API / "alembic" / "versions" / f"{revision}.py").exists()


@pytest.mark.parametrize(
    "table",
    [
        "users",
        "background_jobs",
        "skills",
        "prompt_versions",
        # PHASE 2
        "documents",
        "document_chunks",
        # PHASE 3
        "evidence",
        "evidence_links",
        # PHASE 4
        "jobs",
        "job_skills",
        "job_matches",
        # PHASE 6
        "resume_versions",
        "resume_claims",
        "claim_evidence",
        # PHASE 2b
        "educations",
        "experiences",
        "projects",
        "achievements",
        "profile_skills",
        # PHASE 8
        "applications",
        "application_events",
        "career_events",
    ],
)
def test_tables_exist_after_migration(tmp_path: Path, table: str) -> None:
    assert table in _describe(_migrated_database(tmp_path))
