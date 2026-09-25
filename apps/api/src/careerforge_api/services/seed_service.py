"""Idempotent seeding — the demo account and the vocabulary the app needs to boot.

``docs/DATABASE.md`` §6 puts a hard requirement on seeds: *"必须是自洽的 … 种子脚本
内置自洽性断言，跑不通即失败"*. The seed owns the demo identity (``users`` + ``profiles`` +
``public_profiles``), the demo candidate's career entities (educations, experiences, projects,
declared skills — see :mod:`careerforge_api.services.demo_candidate`), the skill taxonomy and the
prompt registry.

Every function is safe to call on every boot: it looks up first and only writes what
is missing, so ``create_app()`` never fails twice and ``scripts/seed.py`` can be
re-run after a partial failure. The career entities follow the same rule, and for a stronger
reason: they are written through the import writer, which *replaces* what it is given. Seeding them
over a profile a candidate has already built would silently delete their work, so the seed only
fills in an account that has no career rows at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.prompting.registry import PromptRegistry, load_prompt_registry
from careerforge_api.core.config import APISettings
from careerforge_api.core.logging import get_logger
from careerforge_api.models.profile_entity import (
    Experience as ExperienceRow,
    ProfileSkillRow,
    Project as ProjectRow,
)
from careerforge_api.models.user import User
from careerforge_api.repositories.prompt_repository import PromptRepository
from careerforge_api.repositories.user_repository import UserRepository
from careerforge_api.services.demo_candidate import (
    DEMO_GITHUB_USERNAME,
    DEMO_HEADLINE,
    DEMO_LOCATION,
    DEMO_SUMMARY,
    DEMO_TARGET_ROLES,
    demo_candidate_profile,
)
from careerforge_api.services.profile_service import ProfileService
from careerforge_api.services.skill_taxonomy_service import (
    SkillSyncReport,
    sync_skill_taxonomy,
)

__all__ = [
    "DEMO_GITHUB_USERNAME",
    "DEMO_HEADLINE",
    "DEMO_LOCATION",
    "DEMO_SUMMARY",
    "DEMO_TARGET_ROLES",
    "SeedReport",
    "ensure_demo_candidate",
    "ensure_demo_user",
    "seed_all",
]

_logger = get_logger("careerforge_api.services.seed")


async def ensure_demo_user(
    session: AsyncSession,
    settings: APISettings,
    *,
    report: SeedReport | None = None,
) -> User:
    """Return the demo account, creating it (with its profile) when absent.

    The account has no password by design — it is reachable only through
    ``POST /auth/demo``, and the ``is_demo`` flag plus the schema's
    ``password_hash IS NOT NULL OR is_demo = true`` constraint keep it that way.

    ``report`` is an optional sink for *whether this call created the account*. It is a keyword
    argument with a default rather than a second return value because two other callers (the
    lifespan and ``AuthService.demo_login``) want the user and nothing else. Before this, the field
    was declared on :class:`SeedReport` and never written, so a seed report said `created: false`
    for a database it had just built from nothing — a false statement in the one artefact a reader
    uses to check what the seed did.
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
    if report is not None:
        report.demo_user_created = created

    profile, profile_created = await users.ensure_profile(
        user_id=user.id,
        slug=settings.demo_user_slug,
        headline=DEMO_HEADLINE,
        summary=DEMO_SUMMARY,
        location=DEMO_LOCATION,
        github_username=DEMO_GITHUB_USERNAME,
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
    demo_candidate_seeded: bool = False
    demo_candidate_counts: dict[str, int] = field(default_factory=dict)
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
            "demoCandidate": {
                "seeded": self.demo_candidate_seeded,
                "counts": self.demo_candidate_counts,
            },
            "skills": self.skills.as_dict() if self.skills else None,
            "prompts": {
                "inserted": self.prompts_inserted,
                "bumped": self.prompts_bumped,
                "unchanged": self.prompts_unchanged,
            },
            "warnings": self.warnings,
        }


async def _career_row_count(session: AsyncSession, user: User) -> int:
    """Career rows the account already has, across the three entity tables the fixture fills."""
    total = 0
    for model in (ExperienceRow, ProjectRow, ProfileSkillRow):
        statement = select(func.count()).select_from(model).where(model.user_id == user.id)
        total += int(await session.scalar(statement) or 0)
    return total


async def ensure_demo_candidate(
    session: AsyncSession, user: User, settings: APISettings
) -> dict[str, int]:
    """Fill in the demo candidate's career entities — **only** if the account has none.

    The guard is the point. ``ProfileService.persist_profile`` is the import writer, which replaces
    the entities it is handed, so a boot-time seed that ran unconditionally would delete the work of
    anyone who had imported their own résumé into the demo account. "Seed what is missing" is the
    rule everywhere else in this module and it stays the rule here: an account with any experience,
    project or declared skill is left exactly as it is.

    Returns the counts the writer wrote, or `{}` when it was skipped.
    """
    if await _career_row_count(session, user) > 0:
        return {}

    profile_row = await UserRepository(session).get_profile(user_id=user.id)
    slug = (
        profile_row.slug
        if profile_row is not None and profile_row.slug
        else settings.demo_user_slug
    )
    fixture = demo_candidate_profile(slug=slug, github_username="alexchen")
    counts = await ProfileService(session).persist_profile(user=user, profile=fixture)
    _logger.info(
        "demo_candidate_seeded",
        extra={"event": "demo_candidate_seeded", "detail": f"projects={counts.get('projects', 0)}"},
    )
    return counts


async def seed_all(
    session: AsyncSession,
    settings: APISettings,
    *,
    registry: PromptRegistry | None = None,
) -> SeedReport:
    """Seed everything the app needs to boot, idempotently."""
    report = SeedReport()

    user = await ensure_demo_user(session, settings, report=report)
    profile = await UserRepository(session).get_profile(user_id=user.id)
    report.demo_user_id = str(user.id)
    report.demo_profile_slug = profile.slug if profile is not None else None

    # The taxonomy first: the candidate's declared skills are resolved against it, and a skill the
    # dictionary does not know is dropped by the writer rather than stored as free text.
    report.skills = await sync_skill_taxonomy(session)

    counts = await ensure_demo_candidate(session, user, settings)
    report.demo_candidate_seeded = bool(counts)
    report.demo_candidate_counts = counts

    prompts = registry or load_prompt_registry(settings.resolved_prompts_dir)
    prompt_sync = await PromptRepository(session).sync_registry(prompts)
    report.prompts_inserted = prompt_sync.inserted
    report.prompts_bumped = prompt_sync.bumped
    report.prompts_unchanged = prompt_sync.unchanged
    report.warnings.extend(prompts.warnings)

    await session.commit()
    return report
