"""``/auth`` — registration, login, demo login, refresh, logout and the current user.

Every response is the envelope from ``docs/API.md`` §1.1 (applied by middleware), and
the ``data`` payloads match §2.1 exactly: ``{accessToken, refreshToken, expiresIn,
user:{id,email,displayName,isDemo,storageScope}}``.

One deviation worth stating plainly: ``POST /auth/register`` returns **201** with the
same token bundle as ``/auth/login``, because the document lists the endpoint but does
not freeze its status code or body, and ``RegisterRequest`` in ``packages/shared``
expects a session afterwards. ``/auth/login``, ``/auth/demo`` and ``/auth/refresh``
return **200**.

The routes depend on :data:`careerforge_api.deps.AuthServiceDep` rather than building
an ``AuthService`` themselves, so refresh rotation and logout share the application's
one revocation registry.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from careerforge_api.deps import AuthServiceDep, CurrentUser
from careerforge_api.schemas.auth import (
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    UserPublic,
)

__all__ = ["router"]

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and start a session",
)
async def register(payload: RegisterRequest, service: AuthServiceDep) -> AuthResponse:
    """Duplicate email → ``409 CONFLICT`` (``docs/API.md`` §1.6)."""
    user = await service.register(
        email=payload.email,
        password=payload.password,
        display_name=payload.display_name,
    )
    return service.issue_tokens(user)


@router.post("/login", summary="Exchange credentials for a token pair")
async def login(payload: LoginRequest, service: AuthServiceDep) -> AuthResponse:
    """Wrong credentials → ``401 UNAUTHORIZED`` with no hint about which field was wrong."""
    user = await service.login(email=payload.email, password=payload.password)
    return service.issue_tokens(user)


@router.post("/demo", summary="One-click demo login (no credentials)")
async def demo_login(service: AuthServiceDep) -> AuthResponse:
    """``data.user`` always has ``isDemo: true``; the account is seeded if absent."""
    user = await service.demo_login()
    return service.issue_tokens(user)


@router.post("/refresh", summary="Rotate a refresh token")
async def refresh(payload: RefreshRequest, service: AuthServiceDep) -> AuthResponse:
    """The presented refresh token is revoked as it is exchanged (rotation)."""
    return await service.refresh(payload.refresh_token)


@router.post("/logout", summary="Revoke a refresh token")
async def logout(
    service: AuthServiceDep,
    user: CurrentUser,
    payload: LogoutRequest | None = None,
) -> LogoutResponse:
    """Requires a valid access token (``docs/API.md`` §2.1); the body is optional."""
    return await service.logout(payload.refresh_token if payload else None, user_id=user.id)


@router.get("/me", summary="The authenticated user")
async def me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)
