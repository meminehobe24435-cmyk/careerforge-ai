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

#: ``docs/DATABASE.md`` §2.3 — the tables that turn an upload into citable material.
PHASE_2_TABLES = {
    "documents",
    "document_chunks",
}

#: ``docs/DATABASE.md`` §2.5 — evidence and the edges over it.
PHASE_3_TABLES = {
    "evidence",
    "evidence_links",
}


def test_metadata_contains_exactly_the_migrated_tables() -> None:
    """Exact, not a superset assertion: a table added without its phase being finished
    should fail here rather than pass unnoticed."""
    assert set(Base.metadata.tables) == PHASE_1_TABLES | PHASE_2_TABLES | PHASE_3_TABLES


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
        "documents": {"ck_documents_kind_valid", "ck_documents_parse_status_valid"},
        "document_chunks": {
            "ck_document_chunks_chunk_index_non_negative",
            "ck_document_chunks_char_range_valid",
        },
        "evidence": {
            # The formula constraint is the point of this table: a stored confidence that
            # its own five factors do not produce must be impossible.
            "ck_evidence_confidence_formula",
            "ck_evidence_kind_valid",
            "ck_evidence_confidence_unit_range",
        },
        "evidence_links": {
            "ck_evidence_links_relation_valid",
            "ck_evidence_links_no_self_loops",
        },
    }
    for table, names in expected.items():
        found = {c.name for c in Base.metadata.tables[table].constraints if c.name}
        assert names <= found, f"{table} is missing {names - found}"


async def test_evidence_confidence_formula_is_enforced_by_the_database(app: FastAPI) -> None:
    """``docs/DATABASE.md`` §3: the stored confidence must be the formula applied to the
    stored factors.

    This is the guarantee the product rests on — "0.72 confidence" only means something if
    it can be recomputed from the row. Writing a number its own inputs do not produce must
    be impossible, not merely discouraged.
    """
    await _assert_confidence_probe(app, confidence=0.72, accepted=True)
    await _assert_confidence_probe(app, confidence=0.50, accepted=False)
    # ... and within the rounding tolerance the engine actually uses.
    await _assert_confidence_probe(app, confidence=0.721, accepted=True)


async def _assert_confidence_probe(app: FastAPI, *, confidence: float, accepted: bool) -> None:
    """Probe one row: factors fixed at a=0.7 r=1.0 s=0.6 n=1 e=0.8 → 0.72 exactly."""
    from careerforge_api.models.evidence import Evidence

    async with app.state.session_factory() as session:
        owner = await UserRepository(session).create(
            email=f"formula-{uuid4().hex[:8]}@example.com",
            display_name="Formula Probe",
            password_hash="$2b$12$probe",
        )
        await session.commit()
        owner_id = owner.id

    row = {
        "id": uuid4(),
        "user_id": owner_id,
        "kind": "manual",
        "title": "probe",
        "snippet": "",
        "locator": {},
        "source_authority": 0.7,
        "specificity": 0.6,
        "extraction_quality": 0.8,
        "recency_score": 1.0,
        "corroboration_count": 1,
        "confidence": confidence,
        "content_hash": uuid4().hex,
        # ``metadata_``, not ``metadata``: the ORM attribute is renamed because
        # ``Table.metadata`` is SQLAlchemy's own and would shadow it. The column itself is
        # named ``metadata`` (``docs/DATABASE.md`` §2.5).
        "metadata_": {},
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    async with app.state.session_factory() as session:
        if accepted:
            await session.execute(insert(Evidence).values(row))
            await session.commit()
            return
        with pytest.raises(IntegrityError):
            await session.execute(insert(Evidence).values(row))
            await session.flush()
        await session.rollback()


def test_a_stored_confidence_matches_its_factors() -> None:
    """The Python mirror of the SQL formula agrees with the arithmetic the docs state."""
    from careerforge_api.models.evidence import Evidence

    row = Evidence(
        user_id=uuid4(),
        kind="manual",
        title="probe",
        snippet="",
        locator={},
        source_authority=0.7,
        specificity=0.6,
        extraction_quality=0.8,
        recency_score=1.0,
        corroboration_count=1,
        confidence=0.72,
        content_hash="x",
        metadata_={},
    )
    assert row.recomputed_confidence == 0.72
    row.corroboration_count = 5  # 0.4 + 1.0 capped at 1.0
    assert row.recomputed_confidence == round(
        0.30 * 0.7 + 0.15 * 1.0 + 0.20 * 0.6 + 0.20 * 1.0 + 0.15 * 0.8, 3
    )


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
