"""User and profile data access.

**Every query that reads user-owned data filters by ``user_id``.** That is the
enforcement point for ``docs/ARCHITECTURE.md`` §10 ("资源级 ``user_id`` 强制过滤,
Repo 层统一注入"): routers never build their own ``select()`` for tenant data, so
there is a single place to audit and a single place a mistake could live.

Cross-tenant reads return ``None`` rather than raising, because
``docs/API.md`` §1.2 requires ``404 NOT_FOUND`` — the router must not be able to
tell "does not exist" from "belongs to someone else" (see
:func:`careerforge_api.deps.get_owned_or_404`).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.db.compat import utcnow
from careerforge_api.models.user import Profile, PublicProfile, User

__all__ = ["DEFAULT_LOCALE", "UserRepository", "normalise_email"]

DEFAULT_LOCALE = "zh-CN"

#: Five-dimension breakdown starts empty; ``docs/API.md`` §2.2 fills it in PHASE 2.
_EMPTY_BREAKDOWN: dict[str, Any] = {"breakdown": [], "suggestions": []}
_EMPTY_STATS: dict[str, Any] = {
    "evidenceCount": 0,
    "skillCount": 0,
    "projectCount": 0,
    "documentCount": 0,
}


def normalise_email(email: str) -> str:
    """Emails are stored and compared in one canonical form.

    Uniqueness is a global constraint on ``users.email``; without normalisation
    ``Alex@example.com`` and ``alex@example.com`` would be two accounts whose
    password reset flows disagree about which one owns the address.
    """
    return email.strip().lower()


class UserRepository:
    """Tenant-scoped reads and writes for ``users`` / ``profiles`` / ``public_profiles``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── users ────────────────────────────────────────────────────────────────

    async def get_by_id(self, user_id: UUID) -> User | None:
        """Load an account by its primary key (the subject of a token)."""
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == normalise_email(email))
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        display_name: str,
        password_hash: str | None,
        is_demo: bool = False,
        storage_scope: str = "cloud",
        locale: str = DEFAULT_LOCALE,
        privacy_settings: dict[str, Any] | None = None,
    ) -> User:
        user = User(
            email=normalise_email(email),
            display_name=display_name,
            password_hash=password_hash,
            is_demo=is_demo,
            storage_scope=storage_scope,
            locale=locale,
            privacy_settings=dict(privacy_settings or {}),
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def touch_last_login(self, user: User, *, when: Any | None = None) -> None:
        user.last_login_at = when or utcnow()
        await self._session.flush()

    async def update_storage_scope(self, user: User, *, storage_scope: str) -> User:
        """Local Mode toggle (``docs/API.md`` §2.1 ``PATCH /me/settings``)."""
        user.storage_scope = storage_scope
        await self._session.flush()
        return user

    async def count_users(self) -> int:
        return int((await self._session.execute(select(func.count(User.id)))).scalar() or 0)

    # ── profiles (always filtered by user_id) ────────────────────────────────

    async def get_profile(self, *, user_id: UUID) -> Profile | None:
        statement = select(Profile).where(Profile.user_id == user_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_profile_by_slug(self, slug: str) -> Profile | None:
        """Public-page lookup: the slug **is** the tenant key here (``docs/API.md`` §2.12)."""
        statement = select(Profile).where(Profile.slug == slug)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def profile_slug_exists(self, slug: str) -> bool:
        statement = select(Profile.id).where(Profile.slug == slug).limit(1)
        return (await self._session.execute(statement)).first() is not None

    async def ensure_profile(
        self,
        *,
        user_id: UUID,
        slug: str | None = None,
        headline: str | None = None,
        summary: str | None = None,
        location: str | None = None,
        github_username: str | None = None,
        target_roles: list[str] | None = None,
        years_experience: Decimal | float | None = None,
        profile_strength: int | None = None,
    ) -> tuple[Profile, bool]:
        """Idempotently return the caller's profile — ``(profile, created)``.

        Used by the demo seed and by registration, so both paths converge on one
        shape instead of drifting apart.
        """
        existing = await self.get_profile(user_id=user_id)
        if existing is not None:
            return existing, False

        profile = Profile(
            user_id=user_id,
            slug=slug,
            headline=headline,
            summary=summary,
            location=location,
            github_username=github_username,
            target_roles=list(target_roles or []),
            years_experience=(
                Decimal(str(years_experience)) if years_experience is not None else None
            ),
            profile_strength=profile_strength,
            strength_breakdown=dict(_EMPTY_BREAKDOWN),
            stats=dict(_EMPTY_STATS),
        )
        self._session.add(profile)
        await self._session.flush()
        return profile, True

    async def update_profile_fields(self, *, user_id: UUID, **fields: Any) -> Profile | None:
        """Partial update scoped to the caller's own profile."""
        profile = await self.get_profile(user_id=user_id)
        if profile is None:
            return None
        for name, value in fields.items():
            if value is not None and hasattr(profile, name):
                setattr(profile, name, value)
        await self._session.flush()
        return profile

    # ── public profiles (always filtered by user_id) ─────────────────────────

    async def get_public_profile(self, *, user_id: UUID) -> PublicProfile | None:
        statement = select(PublicProfile).where(PublicProfile.user_id == user_id)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def ensure_public_profile(
        self, *, user_id: UUID, slug: str | None = None
    ) -> tuple[PublicProfile, bool]:
        existing = await self.get_public_profile(user_id=user_id)
        if existing is not None:
            return existing, False
        record = PublicProfile(
            user_id=user_id,
            slug=slug,
            is_published=False,
            sections={"skills": True, "projects": True, "evidence": True, "contact": False},
            highlights=[],
            interview_topics=[],
            view_count=0,
        )
        self._session.add(record)
        await self._session.flush()
        return record, True
