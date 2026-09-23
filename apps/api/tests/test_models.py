"""The PHASE 1 schema: documented ``CHECK`` constraints, cascades and indexes.

``docs/DATABASE.md`` §1.1 rule 3 chooses ``text`` + ``CHECK`` over native enums
*"so migrations stay smooth"* — which only holds if the constraints are actually
there. These tests write invalid values through the ORM and require the database to
refuse them, so a constraint cannot be silently dropped by a future edit.

They also prove ``PRAGMA foreign_keys=ON`` is in effect: SQLite ships with foreign key
enforcement **off**, so a cascade test is the only honest way to show the pragma from
``docs/DATABASE.md`` §5 is applied.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError

from careerforge_api.db.base import Base
from careerforge_api.models import BackgroundJob, Profile, PublicProfile, Skill, User
from careerforge_api.models.observability import AgentRun, LlmCall
from careerforge_api.models.prompt import PromptVersion
from careerforge_api.repositories.user_repository import UserRepository

PHASE_1_TABLES = {
    "users",
    "profiles",
    "public_profiles",
    "prompt_versions",
    "agent_runs",
    "llm_calls",
    "background_jobs",
    "ai_caches",
    "skills",
}


def test_metadata_contains_exactly_the_phase_1_tables() -> None:
    assert set(Base.metadata.tables) == PHASE_1_TABLES


def test_every_documented_table_has_its_check_constraints() -> None:
    """A representative constraint per table, by its documented name."""
    expected = {
        "users": {"ck_users_role_valid", "ck_users_storage_scope_valid"},
        "profiles": {"ck_profiles_profile_strength_range", "ck_profiles_years_experience_range"},
        "public_profiles": {"ck_public_profiles_view_count_non_negative"},
        "skills": {"ck_skills_category_valid"},
        "prompt_versions": {"ck_prompt_versions_version_positive"},
        "agent_runs": {"ck_agent_runs_status_valid", "ck_agent_runs_trigger_valid"},
        "llm_calls": {"ck_llm_calls_operation_valid", "ck_llm_calls_status_valid"},
        "background_jobs": {
            "ck_background_jobs_status_valid",
            "ck_background_jobs_progress_range",
        },
        "ai_caches": {"ck_ai_caches_kind_valid"},
    }
    for table, names in expected.items():
        found = {c.name for c in Base.metadata.tables[table].constraints if c.name}
        assert names <= found, f"{table} is missing {names - found}"


def test_evidence_confidence_formula_constraint_is_not_part_of_phase_1() -> None:
    """The formula CHECK from docs/DATABASE.md §3 arrives with the `evidence` table.

    Noted explicitly so its absence is a known boundary rather than an oversight: the
    constraint cannot exist before the table it constrains does.
    """
    assert "evidence" not in Base.metadata.tables


async def _expect_integrity_error(session_factory, statement) -> None:
    async with session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(statement)
            await session.flush()
        await session.rollback()


def _user_row(**overrides) -> dict[str, object]:
    now = datetime.now(UTC)
    row: dict[str, object] = {
        "id": uuid4(),
        "email": f"check-{uuid4().hex[:8]}@example.com",
        "password_hash": "$2b$12$not-a-real-hash-but-not-null",
        "display_name": "Constraint Probe",
        "role": "user",
        "is_demo": False,
        "storage_scope": "cloud",
        "privacy_settings": {},
        "locale": "zh-CN",
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


async def test_users_role_constraint(app: FastAPI) -> None:
    await _expect_integrity_error(
        app.state.session_factory, insert(User).values(_user_row(role="superuser"))
    )


async def test_users_storage_scope_constraint(app: FastAPI) -> None:
    await _expect_integrity_error(
        app.state.session_factory, insert(User).values(_user_row(storage_scope="floppy"))
    )


async def test_demo_accounts_may_omit_a_password_but_only_demo_accounts(app: FastAPI) -> None:
    """``password_hash IS NOT NULL OR is_demo = true`` (docs/DATABASE.md §2.1)."""
    await _expect_integrity_error(
        app.state.session_factory,
        insert(User).values(_user_row(password_hash=None, is_demo=False)),
    )
    async with app.state.session_factory() as session:
        await session.execute(insert(User).values(_user_row(password_hash=None, is_demo=True)))
        await session.commit()


async def test_profiles_profile_strength_is_bounded(app: FastAPI) -> None:
    """The probe uses a real owner so only the CHECK constraint can reject the write."""
    async with app.state.session_factory() as session:
        user = await UserRepository(session).create(
            email=f"strength-{uuid4().hex[:8]}@example.com",
            display_name="Strength Probe",
            password_hash="$2b$12$probe",
        )
        await session.commit()
        user_id = user.id

    await _expect_integrity_error(
        app.state.session_factory,
        insert(Profile).values(
            id=uuid4(),
            user_id=user_id,
            target_roles=[],
            strength_breakdown={},
            stats={},
            profile_strength=101,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )
    # ... and the boundary value is accepted.
    async with app.state.session_factory() as session:
        await session.execute(
            insert(Profile).values(
                id=uuid4(),
                user_id=user_id,
                target_roles=[],
                strength_breakdown={},
                stats={},
                profile_strength=100,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def test_background_jobs_status_and_progress_are_bounded(app: FastAPI) -> None:
    base = {
        "id": uuid4(),
        "kind": "test",
        "payload": {},
        "status": "queued",
        "progress": 0,
        "attempts": 0,
        "max_attempts": 3,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    await _expect_integrity_error(
        app.state.session_factory, insert(BackgroundJob).values({**base, "status": "pending"})
    )
    await _expect_integrity_error(
        app.state.session_factory,
        insert(BackgroundJob).values({**base, "id": uuid4(), "progress": 101}),
    )
    await _expect_integrity_error(
        app.state.session_factory,
        insert(BackgroundJob).values({**base, "id": uuid4(), "max_attempts": 0}),
    )


async def test_skills_category_constraint(app: FastAPI) -> None:
    await _expect_integrity_error(
        app.state.session_factory,
        insert(Skill).values(
            id=uuid4(),
            canonical_id=f"probe-{uuid4().hex[:6]}",
            display_name="Probe",
            category="vibes",
            aliases=[],
            is_active=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )


async def test_llm_calls_operation_and_status_constraints(app: FastAPI) -> None:
    base = {
        "id": uuid4(),
        "agent": "probe",
        "provider": "heuristic",
        "model": "heuristic",
        "operation": "chat",
        "status": "ok",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0,
        "cost_cny": 0,
        "cache_hit": False,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    await _expect_integrity_error(
        app.state.session_factory, insert(LlmCall).values({**base, "operation": "telepathy"})
    )
    await _expect_integrity_error(
        app.state.session_factory,
        insert(LlmCall).values({**base, "id": uuid4(), "status": "maybe"}),
    )


async def test_agent_runs_status_and_trigger_constraints(app: FastAPI) -> None:
    base = {
        "id": uuid4(),
        "workflow": "probe",
        "agent": "probe",
        "status": "running",
        "trigger": "api",
        "steps": [],
        "input_ref": {},
        "output_ref": {},
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0,
        "cost_cny": 0,
        "cache_hit": False,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    await _expect_integrity_error(
        app.state.session_factory, insert(AgentRun).values({**base, "status": "finished"})
    )
    await _expect_integrity_error(
        app.state.session_factory,
        insert(AgentRun).values({**base, "id": uuid4(), "trigger": "cron"}),
    )


async def test_prompt_version_must_be_positive_and_unique(app: FastAPI) -> None:
    base = {
        "id": uuid4(),
        "name": "probe_prompt",
        "content": "body",
        "content_sha256": "sha",
        "variables": [],
        "is_active": True,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    await _expect_integrity_error(
        app.state.session_factory, insert(PromptVersion).values({**base, "version": 0})
    )
    async with app.state.session_factory() as session:
        await session.execute(insert(PromptVersion).values({**base, "version": 1}))
        await session.commit()
    await _expect_integrity_error(
        app.state.session_factory,
        insert(PromptVersion).values({**base, "id": uuid4(), "version": 1}),
    )


async def test_foreign_keys_cascade_on_user_delete(app: FastAPI) -> None:
    """Proves ``PRAGMA foreign_keys=ON``: SQLite would otherwise ignore the cascade."""
    async with app.state.session_factory() as session:
        repository = UserRepository(session)
        user = await repository.create(
            email=f"cascade-{uuid4().hex[:8]}@example.com",
            display_name="Cascade Probe",
            password_hash="$2b$12$probe",
        )
        await repository.ensure_profile(user_id=user.id)
        await repository.ensure_public_profile(user_id=user.id, slug=f"cascade-{uuid4().hex[:6]}")
        session.add(
            BackgroundJob(
                kind="probe", payload={}, user_id=user.id, status="queued", progress=0, attempts=0
            )
        )
        await session.commit()
        user_id: UUID = user.id

    async with app.state.session_factory() as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()

    async with app.state.session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(User).where(User.id == user_id))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(Profile).where(Profile.user_id == user_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(PublicProfile)
                .where(PublicProfile.user_id == user_id)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BackgroundJob)
                .where(BackgroundJob.user_id == user_id)
            )
            == 0
        )


async def test_sqlite_pragmas_are_applied(app: FastAPI) -> None:
    """WAL + foreign_keys + busy_timeout, per ``docs/DATABASE.md`` §5."""
    from sqlalchemy import text

    from careerforge_api.db.session import is_sqlite_url

    if not is_sqlite_url(str(app.state.engine.url)):
        pytest.skip("pragmas are a SQLite concern")
    async with app.state.engine.connect() as connection:
        journal = (await connection.execute(text("PRAGMA journal_mode"))).scalar()
        foreign_keys = (await connection.execute(text("PRAGMA foreign_keys"))).scalar()
        busy_timeout = (await connection.execute(text("PRAGMA busy_timeout"))).scalar()
    assert str(journal).lower() == "wal"
    assert int(foreign_keys) == 1
    assert int(busy_timeout) == 5000


async def test_json_and_timestamp_columns_round_trip_through_the_compat_types(
    app: FastAPI,
) -> None:
    """``docs/DATABASE.md`` §5: JSON is JSON, timestamps come back timezone-aware."""
    async with app.state.session_factory() as session:
        repository = UserRepository(session)
        user = await repository.create(
            email=f"compat-{uuid4().hex[:8]}@example.com",
            display_name="Compat Probe",
            password_hash="$2b$12$probe",
            privacy_settings={"publicPage": False, "retainRawText": True},
        )
        await repository.ensure_profile(
            user_id=user.id, target_roles=["Embedded Engineer"], years_experience=2.5
        )
        await session.commit()
        user_id = user.id

    async with app.state.session_factory() as session:
        stored = await UserRepository(session).get_by_id(user_id)
        assert stored is not None
        assert stored.privacy_settings == {"publicPage": False, "retainRawText": True}
        assert stored.created_at.tzinfo is not None
        profile = await UserRepository(session).get_profile(user_id=user_id)
        assert profile is not None
        assert profile.target_roles == ["Embedded Engineer"]
        assert str(profile.years_experience) == "2.5"
