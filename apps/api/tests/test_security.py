"""Unit tests for the pieces that are easier to test directly than through HTTP:
password hashing, JWT claims, id generation, log redaction and the production gate.

These are the paths that a live request cannot easily exercise — an expired token, a
>72-byte password, an unredacted email in a log line — but that carry the most risk if
they regress.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from careerforge_ai.errors import ConfigurationError
from careerforge_api.core.config import (
    DEV_JWT_SECRET,
    APISettings,
    assert_runtime_configuration,
)
from careerforge_api.core.errors import TokenExpiredError, UnauthorizedError
from careerforge_api.core.ids import (
    is_valid_request_id,
    new_request_id,
    new_ulid,
    parse_task_id,
    task_public_id,
)
from careerforge_api.core.logging import redact, safe_path
from careerforge_api.core.security import (
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

# ── passwords ────────────────────────────────────────────────────────────────


def test_password_hash_round_trip() -> None:
    digest = hash_password("correct horse battery staple")
    assert digest.startswith("$2b$")
    assert digest != "correct horse battery staple"
    assert verify_password("correct horse battery staple", digest) is True
    assert verify_password("wrong", digest) is False


def test_password_hash_is_salted_per_call() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_passwords_longer_than_seventy_two_bytes_are_handled_consistently() -> None:
    """bcrypt truncates at 72 bytes; hashing and verification must agree on it."""
    long_password = "p" * 200
    digest = hash_password(long_password)
    assert verify_password(long_password, digest) is True
    # Anything sharing the first 72 bytes behaves identically — documented behaviour.
    assert verify_password("p" * 72, digest) is True
    assert verify_password("p" * 71 + "q", digest) is False


@pytest.mark.parametrize("stored", [None, "", "not-a-bcrypt-hash"])
def test_verify_password_never_raises_on_a_bad_stored_hash(stored: str | None) -> None:
    """A corrupted hash is an authentication failure, not a 500."""
    assert verify_password("anything", stored) is False


# ── tokens ───────────────────────────────────────────────────────────────────


def _settings(**overrides) -> APISettings:
    return APISettings(environment="test", **overrides)


def test_access_token_carries_the_documented_claims() -> None:
    settings = _settings()
    user_id = uuid4()
    token, expires_in = create_access_token(user_id, settings)
    assert expires_in == settings.access_token_expire_minutes * 60 == 1800

    claims = decode_token(token, settings, expected_type=TOKEN_TYPE_ACCESS)
    assert claims.subject == user_id
    assert claims.token_type == "access"
    assert claims.jti
    assert claims.expires_at > claims.issued_at

    raw = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert raw["sub"] == str(user_id)
    assert raw["type"] == "access"


def test_refresh_token_lives_seven_days() -> None:
    settings = _settings()
    token, _ = create_refresh_token(uuid4(), settings)
    claims = decode_token(token, settings, expected_type=TOKEN_TYPE_REFRESH)
    assert claims.token_type == "refresh"
    lifetime = claims.expires_at - claims.issued_at
    assert lifetime == timedelta(days=settings.refresh_token_expire_days) == timedelta(days=7)


def test_decode_token_refuses_the_wrong_type() -> None:
    settings = _settings()
    refresh, _ = create_refresh_token(uuid4(), settings)
    with pytest.raises(UnauthorizedError):
        decode_token(refresh, settings, expected_type=TOKEN_TYPE_ACCESS)


def test_decode_token_reports_expiry_separately() -> None:
    settings = _settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "access",
            "jti": "j",
            "iat": int((now - timedelta(minutes=10)).timestamp()),
            "exp": int((now - timedelta(minutes=5)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenExpiredError):
        decode_token(token, settings)


def test_decode_token_requires_the_type_claim() -> None:
    settings = _settings()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "jti": "j",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(UnauthorizedError):
        decode_token(token, settings)


def test_decode_token_rejects_an_alg_none_token() -> None:
    """Algorithm confusion: the token must never choose its own verification method."""
    settings = _settings()
    forged = jwt.encode(
        {"sub": str(uuid4()), "type": "access", "jti": "j", "iat": 0, "exp": 9999999999},
        key="",
        algorithm="none",
    )
    with pytest.raises(UnauthorizedError):
        decode_token(forged, settings)


# ── identifiers ──────────────────────────────────────────────────────────────


def test_request_ids_are_ulid_shaped() -> None:
    request_id = new_request_id()
    assert request_id.startswith("req_")
    assert is_valid_request_id(request_id)
    assert len(new_ulid()) == 26
    assert new_ulid() != new_ulid()


@pytest.mark.parametrize(
    "value", ["", None, "with space", "with\nnewline", "a" * 200, "semi;colon"]
)
def test_invalid_request_ids_are_rejected(value: str | None) -> None:
    assert is_valid_request_id(value) is False


def test_task_ids_round_trip() -> None:
    from uuid import UUID

    identifier = uuid4()
    public = task_public_id(identifier)
    assert public == f"tsk_{identifier.hex}"
    assert parse_task_id(public) == identifier
    assert parse_task_id(str(identifier)) == identifier
    assert parse_task_id(f"tsk-{identifier}") == identifier
    assert parse_task_id("nonsense") is None
    assert parse_task_id("tsk_zzzz") is None
    assert isinstance(parse_task_id(public), UUID)


# ── logging ──────────────────────────────────────────────────────────────────


def test_redact_masks_emails_tokens_and_secrets() -> None:
    assert redact("user alex@careerforge.ai failed") == "user [redacted] failed"
    assert redact("Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abc") == "Bearer=[redacted]"

    token = (
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJjNDdmMzI0YSJ9.kJJOAt5oL7pEVULnA-hAhE4uRIwzrnq8TywMJJECOsA"
    )
    assert redact(f"jwt is {token}") == "jwt is [redacted]"
    assert redact("id " + "a" * 60) == "id [redacted]"
    assert redact("nothing sensitive here") == "nothing sensitive here"


def test_safe_path_drops_the_query_string() -> None:
    """Query strings can carry credentials and are never logged."""
    assert safe_path("/api/v1/auth/refresh?token=secret") == "/api/v1/auth/refresh"
    assert safe_path("/api/v1/tasks/tsk_ab") == "/api/v1/tasks/tsk_ab"


# ── production configuration gate ────────────────────────────────────────────


def test_production_refuses_the_development_jwt_secret() -> None:
    """docs/ARCHITECTURE.md §10: the process must not start insecurely."""
    settings = APISettings(environment="production", jwt_secret=DEV_JWT_SECRET)
    with pytest.raises(ConfigurationError) as error:
        assert_runtime_configuration(settings)
    assert "JWT_SECRET" in str(error.value)


def test_production_accepts_a_generated_secret() -> None:
    settings = APISettings(
        environment="production",
        jwt_secret="0f8a1c2d3e4f5061728394a5b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e8f",
        debug=False,
    )
    assert assert_runtime_configuration(settings) == []


def test_production_warns_about_a_short_secret_and_debug_mode() -> None:
    settings = APISettings(environment="production", jwt_secret="short-but-custom", debug=True)
    warnings = assert_runtime_configuration(settings)
    assert len(warnings) == 2


def test_development_tolerates_the_development_secret() -> None:
    assert assert_runtime_configuration(APISettings(environment="development")) == []


def test_create_app_refuses_to_start_in_production_with_the_dev_secret() -> None:
    from careerforge_api.main import create_app

    with pytest.raises(ConfigurationError):
        create_app(APISettings(environment="production", jwt_secret=DEV_JWT_SECRET))
