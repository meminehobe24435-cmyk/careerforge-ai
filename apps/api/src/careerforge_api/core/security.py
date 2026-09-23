"""Password hashing and JWT issuing/decoding.

``docs/API.md`` §1.2: HS256 access tokens valid for 30 minutes, refresh tokens for
7 days with rotation on ``POST /auth/refresh``. Tokens carry a ``type`` claim so a
refresh token can never be replayed as an access token, and the subject is the
user id.

Two details are deliberate rather than incidental:

* **bcrypt truncates at 72 bytes.** ``bcrypt`` 5.x raises on longer input instead
  of truncating silently, so passwords are truncated here — once, consistently, on
  both hash and verify.
* **Password comparison for unknown accounts.** :func:`dummy_password_hash` lets
  the login path spend the same bcrypt time for a non-existent email as for a real
  one, so response timing does not enumerate accounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from uuid import UUID

import bcrypt
import jwt
from careerforge_ai.errors import ConfigurationError

from careerforge_api.core.config import APISettings
from careerforge_api.core.errors import TokenExpiredError, UnauthorizedError
from careerforge_api.core.ids import new_ulid

__all__ = [
    "TOKEN_TYPE_ACCESS",
    "TOKEN_TYPE_REFRESH",
    "TokenClaims",
    "create_access_token",
    "create_refresh_token",
    "create_token",
    "decode_token",
    "dummy_password_hash",
    "hash_password",
    "verify_password",
]

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

#: bcrypt's hard input limit (bytes), see the module docstring.
_BCRYPT_MAX_BYTES = 72

_ISSUER = "careerforge-ai"


def _password_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """bcrypt hash (cost 12) of ``password``."""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-time verification; ``False`` for demo accounts (``None``) or bad hashes."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        # A malformed stored hash is an authentication failure, never a 500.
        return False


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """A real bcrypt hash of a value nobody knows, for timing-equal login failures."""
    return hash_password(new_ulid())


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Decoded, already-validated token payload."""

    subject: UUID
    token_type: str
    jti: str
    issued_at: datetime
    expires_at: datetime


def _encode(payload: dict[str, object], settings: APISettings) -> str:
    if len(settings.jwt_secret) < 16:
        # A weak key silently produces forgeable tokens; make it an explicit error.
        raise ConfigurationError(
            "JWT_SECRET must be at least 16 characters",
            details={"length": len(settings.jwt_secret)},
        )
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_token(
    user_id: UUID,
    settings: APISettings,
    *,
    token_type: str,
) -> tuple[str, int]:
    """Mint one token; returns ``(token, expires_in_seconds)``."""
    now = datetime.now(UTC)
    if token_type == TOKEN_TYPE_REFRESH:
        expires_delta = timedelta(days=settings.refresh_token_expire_days)
    else:
        expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    expires_at = now + expires_delta
    payload: dict[str, object] = {
        "sub": str(user_id),
        "type": token_type,
        "jti": new_ulid(),
        "iss": _ISSUER,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return _encode(payload, settings), int(expires_delta.total_seconds())


def create_access_token(user_id: UUID, settings: APISettings) -> tuple[str, int]:
    return create_token(user_id, settings, token_type=TOKEN_TYPE_ACCESS)


def create_refresh_token(user_id: UUID, settings: APISettings) -> tuple[str, int]:
    return create_token(user_id, settings, token_type=TOKEN_TYPE_REFRESH)


def decode_token(
    token: str,
    settings: APISettings,
    *,
    expected_type: str | None = TOKEN_TYPE_ACCESS,
) -> TokenClaims:
    """Validate signature, expiry and ``type``; raise the documented 401 codes.

    ``TOKEN_EXPIRED`` is reported separately from ``UNAUTHORIZED`` because
    ``docs/API.md`` §1.6 tells the client to refresh on the former and to
    re-authenticate on the latter.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or malformed token") from exc

    token_type = str(payload.get("type", ""))
    if expected_type is not None and token_type != expected_type:
        raise UnauthorizedError(
            f"Expected a {expected_type} token but received a {token_type or 'unknown'} token"
        )
    try:
        subject = UUID(str(payload["sub"]))
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Token subject is not a valid user id") from exc

    jti = str(payload.get("jti") or "")
    if not jti:
        raise UnauthorizedError("Token is missing its identifier")
    return TokenClaims(
        subject=subject,
        token_type=token_type,
        jti=jti,
        issued_at=datetime.fromtimestamp(int(payload["iat"]), tz=UTC),
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
    )
