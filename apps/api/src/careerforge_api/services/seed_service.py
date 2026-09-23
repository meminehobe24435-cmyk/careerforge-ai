"""Idempotent seeding — the demo account and the vocabulary the app needs to boot.

``docs/DATABASE.md`` §6 puts a hard requirement on seeds: *"必须是自洽的 … 种子脚本
内置自洽性断言，跑不通即失败"*. PHASE 1 seeds what PHASE 1 has: the demo identity
(``users`` + ``profiles`` + ``public_profiles``), the skill taxonomy and the prompt
registry. The career entities (educations, projects, evidence, jobs, …) arrive with
their own phases, and this module is where they will be added.

Every function is safe to call on every boot: it looks up first and only writes what
is missing, so ``create_app()`` never fails twice and ``scripts/seed.py`` can be
re-run after a partial failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.prompting.registry import PromptRegistry, load_prompt_registry
from careerforge_api.core.config import APISettings
from careerforge_api.core.logging import get_logger
from careerforge_api.models.user import User
from careerforge_api.repositories.prompt_repository import PromptRepository
from careerforge_api.repositories.user_repository import UserRepository
from careerforge_api.services.skill_taxonomy_service import (
    SkillSyncReport,
    sync_skill_taxonomy,
)

__all__ = [
    "DEMO_HEADLINE",
    "DEMO_TARGET_ROLES",
    "SeedReport",
    "ensure_demo_user",
    "seed_all",
]

#: Headline from ``docs/DATABASE.md`` §8.
DEMO_HEADLINE = "Embedded & AI Application Engineer"

#: Example target roles from ``docs/DATABASE.md`` §2.1.
DEMO_TARGET_ROLES: tuple[str, ...] = ("Embedded Engineer", "AI Application Engineer")

_logger = get_logger("careerforge_api.services.seed")


async def ensure_demo_user(session: AsyncSession, settings: APISettings) -> User:
    """Return the demo account, creating it (with its profile) when absent.

    The account has no password by design — it is reachable only through
    ``POST /auth/demo``, and the ``is_demo`` flag plus the schema's
    ``password_hash IS NOT NULL OR is_demo = true`` constraint keep it that way.
    """
    users = UserRepository(session)
    user = await users.get_by_email(settings.demo_user_email)
    created = False
    if user is None:
        user = await users.create(
            email=settings.demo_user_email,
            display_name=settings.demo_user_name,
            password_hash=None,
            is_demo=True,
            storage_scope="cloud",
        )
        created = True

    profile, profile_created = await users.ensure_profile(
        user_id=user.id,
        slug=settings.demo_user_slug,
        headline=DEMO_HEADLINE,
        summary="Embedded firmware engineer moving into AI application engineering.",
        location="Shanghai, China",
        github_username="alexchen",
        target_roles=list(DEMO_TARGET_ROLES),
        profile_strength=82,
    )
    await users.ensure_public_profile(user_id=user.id, slug=settings.demo_user_slug)
    await session.flush()
    if created or profile_created:
        _logger.info(
            "demo_user_seeded",
            extra={"event": "demo_user_seeded", "detail": f"profile={profile.slug}"},
        )
    return user


@dataclass(slots=True)
class SeedReport:
    """What a :func:`seed_all` run did."""

    demo_user_id: str | None = None
    demo_user_created: bool = False
    demo_profile_slug: str | None = None
    skills: SkillSyncReport | None = None
    prompts_inserted: int = 0
    prompts_bumped: int = 0
    prompts_unchanged: int = 0
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "demoUser": {
                "id": self.demo_user_id,
                "created": self.demo_user_created,
                "slug": self.demo_profile_slug,
            },
            "skills": self.skills.as_dict() if self.skills else None,
            "prompts": {
                "inserted": self.prompts_inserted,
                "bumped": self.prompts_bumped,
                "unchanged": self.prompts_unchanged,
            },
            "warnings": self.warnings,
        }


async def seed_all(
    session: AsyncSession,
    settings: APISettings,
    *,
    registry: PromptRegistry | None = None,
) -> SeedReport:
    """Seed everything PHASE 1 owns, idempotently."""
    report = SeedReport()

    user = await ensure_demo_user(session, settings)
    profile = await UserRepository(session).get_profile(user_id=user.id)
    report.demo_user_id = str(user.id)
    report.demo_profile_slug = profile.slug if profile is not None else None

    report.skills = await sync_skill_taxonomy(session)

    prompts = registry or load_prompt_registry(settings.resolved_prompts_dir)
    prompt_sync = await PromptRepository(session).sync_registry(prompts)
    report.prompts_inserted = prompt_sync.inserted
    report.prompts_bumped = prompt_sync.bumped
    report.prompts_unchanged = prompt_sync.unchanged
    report.warnings.extend(prompts.warnings)

    await session.commit()
    return report
