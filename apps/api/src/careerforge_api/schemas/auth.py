"""Auth request/response models — ``docs/API.md`` §2.1.

The response shapes are copied from the document and from the frozen client types in
``packages/shared/src/api/types.ts`` (``DemoLoginResponse``, ``User``,
``AuthTokens``); ``POST /auth/login`` reuses the demo shape because the document
shows only the demo response and the frontend treats the two as the same bundle.

Passwords are never echoed anywhere, and ``password`` is marked
``repr=False`` so it cannot leak through a debug log of a model.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

__all__ = [
    "MIN_PASSWORD_LENGTH",
    "AuthResponse",
    "AuthTokens",
    "LoginRequest",
    "LogoutRequest",
    "LogoutResponse",
    "RefreshRequest",
    "RegisterRequest",
    "UserPublic",
]

#: Not frozen by ``docs/API.md``; 8 is the shortest value that is not a guess quota.
MIN_PASSWORD_LENGTH = 8


class _CamelModel(BaseModel):
    """Accepts snake_case and camelCase input, always emits camelCase."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class RegisterRequest(_CamelModel):
    """``POST /auth/register``."""

    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128, repr=False)
    display_name: str | None = Field(default=None, alias="displayName", max_length=120)


class LoginRequest(_CamelModel):
    """``POST /auth/login``."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128, repr=False)


class RefreshRequest(_CamelModel):
    """``POST /auth/refresh``."""

    refresh_token: str = Field(alias="refreshToken", min_length=8)


class LogoutRequest(_CamelModel):
    """``POST /auth/logout`` — the refresh token to revoke."""

    refresh_token: str | None = Field(default=None, alias="refreshToken")


class UserPublic(_CamelModel):
    """The ``user`` object of the documented demo-login response."""

    id: UUID
    email: str
    display_name: str = Field(alias="displayName")
    is_demo: bool = Field(alias="isDemo")
    storage_scope: str = Field(alias="storageScope")


class AuthTokens(_CamelModel):
    """Access + refresh pair. ``expiresIn`` is the access-token lifetime in seconds."""

    access_token: str = Field(alias="accessToken")
    refresh_token: str = Field(alias="refreshToken")
    expires_in: int = Field(alias="expiresIn")


class AuthResponse(AuthTokens):
    """``data`` of ``POST /auth/demo``, ``/auth/login``, ``/auth/register`` and ``/auth/refresh``."""

    user: UserPublic


class LogoutResponse(_CamelModel):
    """``data`` of ``POST /auth/logout``."""

    revoked: bool
    detail: str | None = None
