"""FastAPI dependencies: settings, database session, current user, task lookup.

``docs/ARCHITECTURE.md`` §8.2 lists authentication as a step in the middleware chain;
it is implemented here instead, as a dependency, because only some routes need an
identity — a middleware would have to guess, and "no token required" would become an
exception list rather than the default.

The ownership rule from ``docs/API.md`` §1.2 lives in :func:`get_owned_or_404`:
a resource that exists but belongs to someone else is **404, not 403**, so the API
never confirms that another user's data exists.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from careerforge_api.core.config import APISettings, get_api_settings
from careerforge_api.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from careerforge_api.models.user import User
from careerforge_api.services.auth_service import AuthService, TokenRevocationRegistry

__all__ = [
    "AuthServiceDep",
    "CurrentUser",
    "DbSession",
    "OptionalUser",
    "SettingsDep",
    "get_admin_or_403",
    "get_auth_service",
    "get_current_user",
    "get_db",
    "get_optional_user",
    "get_owned_or_404",
    "get_request_id",
    "get_settings",
    "get_token_revocations",
]


# ── settings ─────────────────────────────────────────────────────────────────


def get_settings(request: Request) -> APISettings:
    """The settings this app instance was built with.

    ``create_app(settings=...)`` stores its object on ``app.state`` so a test can run
    against an explicit configuration (a temporary SQLite file, a tighter rate limit)
    without mutating the process environment.
    """
    settings = getattr(request.app.state, "settings", None)
    return settings if settings is not None else get_api_settings()


SettingsDep = Annotated[APISettings, Depends(get_settings)]


# ── database ─────────────────────────────────────────────────────────────────


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One session (and one transaction) per request.

    The transaction is committed when the handler returns successfully and rolled
    back when it raises, so an ``ApiError`` halfway through a write leaves no partial
    state behind. Services that must be durable *before* the response is serialised
    (auth) commit explicitly; a second commit is a no-op.
    """
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()


DbSession = Annotated[AsyncSession, Depends(get_db)]


# ── request context ──────────────────────────────────────────────────────────


def get_request_id(request: Request) -> str:
    """The correlation id set by :class:`~careerforge_api.middleware.request_id.RequestIDMiddleware`."""
    return str(getattr(request.state, "request_id", "") or "")


def get_token_revocations(request: Request) -> TokenRevocationRegistry:
    """The app-wide revoked-token registry (see the PHASE 2 note in ``AuthService``)."""
    registry = getattr(request.app.state, "token_revocations", None)
    if registry is None:  # pragma: no cover - only if create_app was bypassed
        registry = TokenRevocationRegistry()
        request.app.state.token_revocations = registry
    return registry


def get_auth_service(
    session: DbSession,
    settings: SettingsDep,
    revocations: Annotated[TokenRevocationRegistry, Depends(get_token_revocations)],
) -> AuthService:
    """Auth service bound to the app-wide revocation registry.

    Routes must depend on this rather than constructing ``AuthService`` themselves:
    a per-request registry would forget every revoked token the moment the response
    was sent, silently disabling refresh rotation.
    """
    return AuthService(session, settings, revocations=revocations)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


# ── authentication ───────────────────────────────────────────────────────────


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise UnauthorizedError("Authorization header is missing")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise UnauthorizedError("Authorization header must use the Bearer scheme")
    return value.strip()


async def get_current_user(
    session: DbSession,
    settings: SettingsDep,
    revocations: Annotated[TokenRevocationRegistry, Depends(get_token_revocations)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """Require a valid access token; ``401 UNAUTHORIZED``/``TOKEN_EXPIRED`` otherwise."""
    token = _bearer_token(authorization)
    service = AuthService(session, settings, revocations=revocations)
    return await service.authenticate(token)


async def get_optional_user(
    session: DbSession,
    settings: SettingsDep,
    revocations: Annotated[TokenRevocationRegistry, Depends(get_token_revocations)],
    authorization: Annotated[str | None, Header()] = None,
) -> User | None:
    """For endpoints that behave differently when authenticated but never require it."""
    if not authorization:
        return None
    try:
        return await get_current_user(session, settings, revocations, authorization)
    except UnauthorizedError:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]

OptionalUser = Annotated[User | None, Depends(get_optional_user)]


# ── ownership ────────────────────────────────────────────────────────────────


def get_owned_or_404[ResourceT](
    resource: ResourceT | None,
    *,
    user_id: UUID,
    owner_field: str = "user_id",
) -> ResourceT:
    """Return the resource when the caller owns it, otherwise raise ``404 NOT_FOUND``.

    Used for every lookup that takes an id from the URL. ``403 FORBIDDEN`` would tell
    an attacker that the id exists, which ``docs/API.md`` §1.2 explicitly rules out.
    """
    if resource is None:
        raise NotFoundError()
    owner = getattr(resource, owner_field, None)
    if owner is not None and owner != user_id:
        raise NotFoundError()
    return resource


def get_admin_or_403(user: User) -> User:
    """``403 FORBIDDEN`` is correct when the caller already knows the resource exists."""
    if user.role != "admin":
        raise ForbiddenError("This operation requires the admin role")
    return user
