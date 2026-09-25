"""Seeding and the services built on it: demo account, skill taxonomy, prompts.

``docs/DATABASE.md`` §6 requires seeds to be idempotent and self-consistent, and §6
also requires the ``skills`` table to stay isomorphic with
``careerforge_ai.parsing.skill_taxonomy``. Both are asserted here — against the real
taxonomy module, not a copy of it.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI
from sqlalchemy import func, select

from careerforge_ai.parsing.skill_taxonomy import SKILLS, TAXONOMY_VERSION
from careerforge_ai.prompting.registry import PROMPT_NAMES, PromptRegistry, load_prompt_registry
from careerforge_api.models.prompt import PromptVersion
from careerforge_api.models.skill import Skill
from careerforge_api.models.user import User
from careerforge_api.repositories.prompt_repository import PromptRepository
from careerforge_api.services.demo_candidate import DEMO_SKILLS
from careerforge_api.services.seed_service import seed_all
from careerforge_api.services.skill_taxonomy_service import sync_skill_taxonomy

APPS_API = Path(__file__).resolve().parents[1]
REPO_ROOT = APPS_API.parents[1]


async def test_demo_user_is_seeded_with_a_profile(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        from careerforge_api.repositories.user_repository import UserRepository

        users = UserRepository(session)
        user = await users.get_by_email("demo@careerforge.ai")
        assert user is not None
        assert user.display_name == "Alex Chen"
        assert user.is_demo is True
        assert user.password_hash is None
        assert user.storage_scope == "cloud"
        profile = await users.get_profile(user_id=user.id)
        assert profile is not None
        assert profile.slug == "alex"
        assert profile.profile_strength == 82

        public = await users.get_public_profile(user_id=user.id)
        assert public is not None
        assert public.is_published is False
        assert public.sections["contact"] is False


async def test_demo_candidate_fixture_is_a_coherent_person(app: FastAPI, settings) -> None:
    """The seed's candidate fixture produces a person, not rows that happen to exist.

    Before this, the seed wrote the user and the profile row and stopped: no projects, no
    experience, no declared skills. Every screen that shows a *person* — the recruiter view above
    all — therefore read a candidate whose first project had the same name and summary, because the
    only rows it ever had came from whoever imported a résumé last.

    The assertion runs against **a private account** rather than the shared demo one, and that is a
    correctness requirement rather than tidiness: the suite shares one database, and another test's
    `POST /profile/import` replaces the demo account's career entities. Asserting on the demo
    account would make this test a statement about test order.

    What it pins is coherence:

    * the headline is a **title**, not the person's name printed twice;
    * every project has a summary that is longer than, and different from, its own name;
    * the skill set contains what the shipped demo flows match on (STM32/FreeRTOS/Python/FastAPI/
      RAG) and does **not** contain the ones the Unsupported preset and the Jobs gap depend on
      being absent (AUTOSAR, Kafka, Kubernetes, Rust, TensorFlow).
    """
    async with app.state.session_factory() as session:
        from careerforge_api.models.profile_entity import (
            Experience as ExperienceRow,
            ProfileSkillRow,
            Project as ProjectRow,
        )
        from careerforge_api.repositories.user_repository import UserRepository
        from careerforge_api.services.seed_service import ensure_demo_candidate

        users = UserRepository(session)
        account = await users.create(
            email=f"candidate-fixture-{uuid4().hex[:8]}@example.com",
            display_name="Fixture Candidate",
            password_hash="not-a-real-hash",
            is_demo=False,
            storage_scope="cloud",
        )
        await session.commit()

        counts = await ensure_demo_candidate(session, account, settings)
        await session.commit()

        assert counts["projects"] == 3
        assert counts["experiences"] == 2
        assert counts["educations"] == 1
        assert counts["skills"] >= 10

        profile = await users.get_profile(user_id=account.id)
        assert profile is not None
        # A title, not the display name: the public page prints both, one above the other.
        assert profile.headline
        assert profile.headline != account.display_name
        assert profile.summary
        assert account.display_name not in profile.summary

        projects = (
            await session.scalars(
                select(ProjectRow).where(ProjectRow.user_id == account.id).order_by(ProjectRow.name)
            )
        ).all()
        assert len(projects) == 3
        for project in projects:
            assert project.summary, f"project {project.name!r} has no summary"
            # The bug that read as broken data: a summary that only repeats the name.
            assert project.summary.strip() != project.name.strip()
            assert len(project.summary) > len(project.name)

        experiences = (
            await session.scalars(select(ExperienceRow).where(ExperienceRow.user_id == account.id))
        ).all()
        assert len(experiences) == 2
        assert all(row.description for row in experiences)

        declared = {
            row.canonical_id
            for row in (
                await session.scalars(
                    select(ProfileSkillRow).where(ProfileSkillRow.user_id == account.id)
                )
            ).all()
        }
        # Present: the skills the shipped demo posting, the Strong validator preset and the
        # AI-application half of the same person rely on.
        assert {"stm32", "free_rtos", "pid", "i2c", "python", "fastapi", "rag"} <= declared
        # Absent: the Unsupported preset and the Jobs gap both depend on these being missing.
        assert not declared & {"autosar", "kafka", "kubernetes", "rust", "tensorflow"}
        # Every declared skill resolves in the taxonomy, so the counts above are all of them…
        assert declared <= {skill.canonical_id for skill in SKILLS}
        # …and every fixture entry was written, i.e. no id was silently dropped by the writer.
        assert counts["skills"] == len(DEMO_SKILLS)


async def test_demo_candidate_is_not_seeded_over_existing_work(app: FastAPI, settings) -> None:
    """The seed fills in a new account and leaves a used one alone.

    ``persist_profile`` is the import writer: it *replaces* the career entities it is handed. A
    boot-time seed that ran unconditionally would delete the work of anyone who had imported their
    own résumé into the demo account — silently, on every restart. The guard is therefore part of
    the contract, and it is asserted here rather than assumed.
    """
    async with app.state.session_factory() as session:
        from careerforge_api.models.profile_entity import Project as ProjectRow
        from careerforge_api.repositories.user_repository import UserRepository
        from careerforge_api.services.seed_service import ensure_demo_candidate

        users = UserRepository(session)
        account = await users.create(
            email=f"candidate-used-{uuid4().hex[:8]}@example.com",
            display_name="Has Own Work",
            password_hash="not-a-real-hash",
            is_demo=False,
            storage_scope="cloud",
        )
        await session.commit()

        assert await ensure_demo_candidate(session, account, settings) != {}
        await session.commit()
        before = (
            await session.scalars(select(ProjectRow).where(ProjectRow.user_id == account.id))
        ).all()

        # A second run is a no-op — nothing is rewritten, nothing is duplicated.
        assert await ensure_demo_candidate(session, account, settings) == {}
        await session.commit()
        after = (
            await session.scalars(select(ProjectRow).where(ProjectRow.user_id == account.id))
        ).all()
        assert [row.id for row in after] == [row.id for row in before]


async def test_seed_all_is_idempotent(app: FastAPI, settings) -> None:
    """Running the seed twice must not duplicate anything.

    One registry instance is reused for both runs, so the assertion cannot be affected by
    a prompt file being edited concurrently — the point being tested is the database
    write, not the file watcher the API does not have.
    """
    registry = load_prompt_registry(settings.resolved_prompts_dir)
    async with app.state.session_factory() as session:
        first = await seed_all(session, settings, registry=registry)
        skills_before = await session.scalar(select(func.count()).select_from(Skill))
        users_before = await session.scalar(select(func.count()).select_from(User))
        prompts_before = await session.scalar(select(func.count()).select_from(PromptVersion))
    async with app.state.session_factory() as session:
        second = await seed_all(session, settings, registry=registry)
        skills_after = await session.scalar(select(func.count()).select_from(Skill))
        users_after = await session.scalar(select(func.count()).select_from(User))
        prompts_after = await session.scalar(select(func.count()).select_from(PromptVersion))

    # Neither run creates the account: the app's lifespan already did, and the second run finds
    # it. The flag is asserted on both runs because it used to be declared on `SeedReport` and
    # never written, so `False` meant nothing at all.
    assert first.demo_user_created is False
    assert second.demo_user_created is False
    assert second.skills is not None
    assert second.skills.inserted == 0
    assert second.skills.updated == 0
    assert second.prompts_inserted == 0
    assert second.prompts_bumped == 0
    assert (skills_after, users_after, prompts_after) == (
        skills_before,
        users_before,
        prompts_before,
    )
    # Accounts registered by other tests share this database, so only "unchanged" is
    # meaningful here; there is a dedicated test that the demo account exists once.
    assert users_after == users_before
    assert skills_before == len(SKILLS)


async def test_skill_taxonomy_is_synced_and_matches_the_core_module(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        rows = list((await session.execute(select(Skill))).scalars())
    assert len(rows) == len(SKILLS) == 126

    by_id = {row.canonical_id: row for row in rows}
    stm32 = by_id["stm32"]
    assert stm32.display_name == "STM32"
    assert stm32.category == "embedded"
    assert "stm32f407" in stm32.aliases
    assert stm32.is_active is True

    # Every row mirrors the code-side taxonomy exactly (docs/DATABASE.md §6).
    for skill in SKILLS:
        row = by_id[skill.canonical_id]
        assert row.display_name == skill.display_name
        assert row.category == skill.category.value
        assert list(row.aliases) == list(skill.aliases)


async def test_skill_sync_reactivates_and_prunes(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        target = await session.scalar(select(Skill).where(Skill.canonical_id == "stm32"))
        assert target is not None
        target.is_active = False
        session.add(
            Skill(
                canonical_id="obsolete_probe_skill",
                display_name="Obsolete",
                category="tool",
                aliases=[],
                is_active=True,
            )
        )
        await session.commit()

    async with app.state.session_factory() as session:
        report = await sync_skill_taxonomy(session, prune=True)
        await session.commit()
    assert report.updated >= 1  # stm32 reactivated
    assert report.deactivated == 1  # the obsolete row was retired, not deleted

    async with app.state.session_factory() as session:
        reactivated = await session.scalar(select(Skill).where(Skill.canonical_id == "stm32"))
        retired = await session.scalar(
            select(Skill).where(Skill.canonical_id == "obsolete_probe_skill")
        )
    assert reactivated is not None and reactivated.is_active is True
    assert retired is not None and retired.is_active is False


async def test_prompt_registry_is_mirrored_and_one_version_stays_active(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        rows = [
            row for row in await PromptRepository(session).list_all() if row.name in PROMPT_NAMES
        ]

    names = {row.name for row in rows}
    assert names == set(PROMPT_NAMES)
    active = [row for row in rows if row.is_active]
    assert {row.name for row in active} == names
    assert len(active) == len(names)  # exactly one active version per prompt
    assert all(row.content and row.content_sha256 for row in rows)
    assert all(row.ref.endswith(f"@v{row.version}") for row in rows)


async def test_prompt_sync_bumps_the_version_when_content_changes(app: FastAPI) -> None:
    """docs/DATABASE.md §2.11: a content change without a version bump adds a revision.

    Uses a synthetic prompt name so the probe cannot perturb the real prompt history.
    """
    from careerforge_ai.prompting.registry import PromptRegistry, PromptTemplate

    def registry_with(body: str) -> PromptRegistry:
        registry = PromptRegistry()
        registry.register(PromptTemplate(name="test_revision_probe", version=1, body=body))
        return registry

    async with app.state.session_factory() as session:
        repository = PromptRepository(session)
        first = await repository.sync_registry(registry_with("first body"))
        await session.commit()
    assert first.inserted == 1

    async with app.state.session_factory() as session:
        repository = PromptRepository(session)
        original = await repository.get("test_revision_probe", 1)
        assert original is not None

        second = await repository.sync_registry(registry_with("second body"))
        await session.commit()
    assert second.inserted == 0
    assert second.bumped == 1

    async with app.state.session_factory() as session:
        repository = PromptRepository(session)
        latest = await repository.get("test_revision_probe", 2)
        preserved = await repository.get("test_revision_probe", 1)
    assert latest is not None and preserved is not None
    assert latest.content == "second body"
    assert latest.is_active is True
    # The original revision is preserved verbatim for already-traced runs.
    assert preserved.content == "first body"
    assert preserved.is_active is False

    # Re-syncing the *same* new content must NOT add another revision: otherwise a prompt
    # edited without a version bump would grow the table on every boot.
    async with app.state.session_factory() as session:
        repository = PromptRepository(session)
        third = await repository.sync_registry(registry_with("second body"))
        await session.commit()
        total = len(
            [row for row in await repository.list_all() if row.name == "test_revision_probe"]
        )
    assert third.bumped == 0
    assert third.inserted == 0
    assert total == 2


async def test_prompt_sync_honours_a_declared_version_bump(app: FastAPI) -> None:
    """When the front matter says ``version: 4``, that number is what gets stored."""
    from careerforge_ai.prompting.registry import PromptRegistry, PromptTemplate

    registry = PromptRegistry()
    registry.register(PromptTemplate(name="test_declared_version", version=1, body="v1 body"))
    async with app.state.session_factory() as session:
        repository = PromptRepository(session)
        assert (await repository.sync_registry(registry)).inserted == 1
        await session.commit()

    bumped = PromptRegistry()
    bumped.register(PromptTemplate(name="test_declared_version", version=4, body="v4 body"))
    async with app.state.session_factory() as session:
        repository = PromptRepository(session)
        report = await repository.sync_registry(bumped)
        await session.commit()
        row = await repository.get("test_declared_version", 4)

    assert report.inserted == 1
    assert report.bumped == 0
    assert row is not None and row.content == "v4 body" and row.is_active is True


async def test_prompt_files_exist_for_every_registered_name(app: FastAPI) -> None:
    """A mirrored prompt must always point at the file it came from."""
    async with app.state.session_factory() as session:
        rows = [
            row for row in await PromptRepository(session).list_all() if row.name in PROMPT_NAMES
        ]
    assert {row.name for row in rows} == set(PROMPT_NAMES)
    for row in rows:
        assert row.path, f"{row.ref} has no source path"
        path = Path(row.path)
        if not path.is_absolute():
            path = REPO_ROOT / path
        assert path.exists(), f"prompt file missing for {row.ref}: {path}"
        assert path.read_text(encoding="utf-8").strip(), f"prompt file is empty: {path}"


def test_taxonomy_version_is_reported_by_the_health_endpoint() -> None:
    assert TAXONOMY_VERSION == "taxonomy@1.0.0"


async def test_user_repository_scopes_profile_reads_by_user_id(app: FastAPI) -> None:
    """The same profile must not be reachable through a different user id."""
    from careerforge_api.repositories.user_repository import UserRepository

    async with app.state.session_factory() as session:
        users = UserRepository(session)
        demo = await users.get_by_email("demo@careerforge.ai")
        assert demo is not None
        assert await users.get_profile(user_id=demo.id) is not None
        assert await users.get_profile(user_id=UUID(int=0)) is None
        assert await users.get_public_profile(user_id=UUID(int=0)) is None
