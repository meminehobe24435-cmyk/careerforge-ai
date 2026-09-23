"""Authentication: register, login, demo login, refresh rotation and logout.

Behaviours frozen by ``docs/API.md`` §1.2/§2.1 that this service implements:

* access tokens live 30 minutes, refresh tokens 7 days, and ``POST /auth/refresh``
  **rotates** them (the presented refresh token is revoked as it is exchanged);
* ``POST /auth/demo`` needs no credentials and always resolves to the demo account;
* a failed login is ``401 UNAUTHORIZED`` — the message never says whether the email
  exists, and the bcrypt work is done either way so timing cannot either.

**Known limitation (PHASE 2):** revocation is held in
:class:`TokenRevocationRegistry`, an in-process map, because PHASE 1 has no token
table and no Redis. It is correct for a single API process and is reset by a
restart; a distributed deployment needs the same registry backed by the database or
Redis (see the PHASE 2 notes in the API README). Nothing else about the flow is
provisional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.core.config import APISettings
from careerforge_api.core.errors import ConflictError, UnauthorizedError, ValidationError
from careerforge_api.core.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    dummy_password_hash,
    hash_password,
    verify_password,
)
from careerforge_api.models.user import User
from careerforge_api.repositories.user_repository import UserRepository, normalise_email
from careerforge_api.schemas.auth import AuthResponse, LogoutResponse, UserPublic
from careerforge_api.services.seed_service import DEMO_TARGET_ROLES

__all__ = ["AuthService", "TokenRevocationRegistry"]


@dataclass(slots=True)
class TokenRevocationRegistry:
    """Process-local set of revoked token ids (``jti``), pruned as they expire."""

    _revoked: dict[str, datetime] = field(default_factory=dict)

    def revoke(self, jti: str, *, expires_at: datetime | None = None) -> None:
        self._revoked[jti] = expires_at or datetime.now(UTC)
        self.prune()

    def is_revoked(self, jti: str) -> bool:
        self.prune()
        return jti in self._revoked

    def prune(self) -> None:
        now = datetime.now(UTC)
        for key in [key for key, expiry in self._revoked.items() if expiry <= now]:
            del self._revoked[key]

    @property
    def size(self) -> int:
        return len(self._revoked)


class AuthService:
    """Account lifecycle for ``/auth/*``."""

    def __init__(
        self,
        session: AsyncSession,
        settings: APISettings,
        *,
        revocations: TokenRevocationRegistry | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._users = UserRepository(session)
        self.revocations = revocations or TokenRevocationRegistry()

    # ── registration & login ─────────────────────────────────────────────────

    async def register(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
    ) -> User:
        """Create an account. A duplicate email is ``409 CONFLICT``."""
        normalised = normalise_email(email)
        if await self._users.get_by_email(normalised) is not None:
            raise ConflictError(
                "An account with this email already exists",
                details=[{"field": "email", "issue": "already_registered"}],
            )
        if not password:
            raise ValidationError(
                "password must not be empty",
                details=[{"field": "password", "issue": "required"}],
            )

        user = await self._users.create(
            email=normalised,
            display_name=(display_name or normalised.split("@", 1)[0]).strip() or "Candidate",
            password_hash=hash_password(password),
        )
        # A profile is created up front so the caller has somewhere to write to and
        # the strength score has a row to live in from the first request.
        await self._users.ensure_profile(user_id=user.id, target_roles=list(DEMO_TARGET_ROLES))
        await self._session.commit()
        return user

    async def login(self, *, email: str, password: str) -> User:
        """Verify credentials or fail with ``401 UNAUTHORIZED``."""
        user = await self._users.get_by_email(email)
        if user is None or not user.password_hash:
            # Spend the same bcrypt time as a real account would, so the response
            # latency does not reveal whether the email exists.
            verify_password(password, dummy_password_hash())
            raise UnauthorizedError("Email or password is incorrect")
        if not verify_password(password, user.password_hash):
            raise UnauthorizedError("Email or password is incorrect")
        await self._users.touch_last_login(user)
        await self._session.commit()
        return user

    async def demo_login(self) -> User:
        """Resolve (creating if needed) the seeded demo account."""
        from careerforge_api.services.seed_service import ensure_demo_user

        user = await ensure_demo_user(self._session, self._settings)
        await self._users.touch_last_login(user)
        await self._session.commit()
        return user

    # ── tokens ───────────────────────────────────────────────────────────────

    def issue_tokens(self, user: User) -> AuthResponse:
        """Mint a session. Field names are used here; the wire format is camelCase."""
        access_token, expires_in = create_access_token(user.id, self._settings)
        refresh_token, _ = create_refresh_token(user.id, self._settings)
        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            user=UserPublic.model_validate(user),
        )

    async def refresh(self, refresh_token: str) -> AuthResponse:
        """Rotate a refresh token: revoke the presented one, mint a new pair."""
        claims = decode_token(refresh_token, self._settings, expected_type=TOKEN_TYPE_REFRESH)
        if self.revocations.is_revoked(claims.jti):
            raise UnauthorizedError("This refresh token has already been used or revoked")
        user = await self._users.get_by_id(claims.subject)
        if user is None:
            raise UnauthorizedError("The account for this token no longer exists")
        self.revocations.revoke(claims.jti, expires_at=claims.expires_at)
        await self._session.commit()
        return self.issue_tokens(user)

    async def logout(
        self, refresh_token: str | None, *, user_id: UUID | None = None
    ) -> LogoutResponse:
        """Revoke the supplied refresh token. Idempotent by design.

        When ``user_id`` is supplied (the authenticated caller), a token that belongs to
        somebody else is not revoked: possessing it would already mean a compromise, but
        one session should never be able to end another account's session.
        """
        if not refresh_token:
            return LogoutResponse(revoked=False, detail="no refresh token supplied")
        try:
            claims = decode_token(refresh_token, self._settings, expected_type=TOKEN_TYPE_REFRESH)
        except UnauthorizedError:
            # An expired or already-invalid token means the client is logged out anyway.
            return LogoutResponse(revoked=False, detail="refresh token is not valid")
        if user_id is not None and claims.subject != user_id:
            return LogoutResponse(revoked=False, detail="refresh token belongs to another account")
        self.revocations.revoke(claims.jti, expires_at=claims.expires_at)
        await self._session.commit()
        return LogoutResponse(revoked=True)

    async def authenticate(self, access_token: str) -> User:
        """Resolve a bearer access token to its account (used by ``get_current_user``)."""
        claims = decode_token(access_token, self._settings, expected_type=TOKEN_TYPE_ACCESS)
        if self.revocations.is_revoked(claims.jti):
            raise UnauthorizedError("This token has been revoked")
        user = await self._users.get_by_id(claims.subject)
        if user is None:
            raise UnauthorizedError("The account for this token no longer exists")
        return user

    async def user_public(self, user_id: UUID) -> UserPublic | None:
        user = await self._users.get_by_id(user_id)
        return UserPublic.model_validate(user) if user is not None else None
