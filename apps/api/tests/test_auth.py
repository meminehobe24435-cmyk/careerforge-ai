"""``/auth/*`` — the flows and failure modes frozen by ``docs/API.md`` §1.2/§2.1."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from httpx import AsyncClient
import jwt
import pytest
from sqlalchemy import func, select

from careerforge_api.core.config import APISettings
from careerforge_api.models.user import User
from careerforge_api.repositories.user_repository import UserRepository
from careerforge_api.schemas.auth import MIN_PASSWORD_LENGTH
from tests.conftest import TEST_PASSWORD, EnvelopeCheck, Session, UserFactory


async def test_demo_login_returns_the_documented_shape(
    client: AsyncClient, envelope: EnvelopeCheck, app
) -> None:
    """`POST /auth/demo` returns exactly the payload of docs/API.md §2.1."""
    response = await client.post("/api/v1/auth/demo")
    assert response.status_code == 200
    data = envelope(response)["data"]

    assert set(data) == {"accessToken", "refreshToken", "expiresIn", "user"}
    # docs/API.md §1.2: access tokens last 30 minutes.
    assert data["expiresIn"] == 1800
    assert data["accessToken"] and data["refreshToken"]

    assert set(data["user"]) == {"id", "email", "displayName", "isDemo", "storageScope"}
    assert data["user"]["email"] == "demo@careerforge.ai"
    assert data["user"]["displayName"] == "Alex Chen"
    assert data["user"]["isDemo"] is True
    assert data["user"]["storageScope"] == "cloud"
    UUID(data["user"]["id"])

    # The demo account must have a profile (docs/DATABASE.md §8: slug `alex`).
    async with app.state.session_factory() as db:
        profile = await UserRepository(db).get_profile(user_id=UUID(data["user"]["id"]))
    assert profile is not None
    assert profile.slug == "alex"
    assert profile.headline == "Embedded & AI Application Engineer"
    assert profile.target_roles == ["Embedded Engineer", "AI Application Engineer"]


async def test_demo_login_is_idempotent(client: AsyncClient, app) -> None:
    """Two demo logins must not create two accounts."""
    first = (await client.post("/api/v1/auth/demo")).json()["data"]["user"]["id"]
    second = (await client.post("/api/v1/auth/demo")).json()["data"]["user"]["id"]
    assert first == second

    async with app.state.session_factory() as db:
        count = await db.scalar(select(func.count(User.id)).where(User.is_demo.is_(True)))
    assert count == 1


async def test_register_then_login_then_refresh_then_protected_route(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """The full documented session lifecycle, including refresh rotation."""
    session = await make_user()
    assert session.expires_in == 1800

    login = await client.post(
        "/api/v1/auth/login", json={"email": session.email, "password": TEST_PASSWORD}
    )
    assert login.status_code == 200
    login_data = envelope(login)["data"]
    assert login_data["user"]["id"] == session.id
    assert login_data["user"]["isDemo"] is False

    headers = {"Authorization": f"Bearer {login_data['accessToken']}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert envelope(me)["data"]["email"] == session.email

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refreshToken": login_data["refreshToken"]}
    )
    assert refreshed.status_code == 200
    rotated = envelope(refreshed)["data"]
    assert rotated["refreshToken"] != login_data["refreshToken"]

    still_valid = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {rotated['accessToken']}"}
    )
    assert still_valid.status_code == 200

    # The presented token can no longer be exchanged: rotation, docs/API.md §1.2.
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refreshToken": login_data["refreshToken"]}
    )
    assert replay.status_code == 401
    assert envelope(replay, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_login_with_wrong_password_is_unauthorized(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    session = await make_user()
    response = await client.post(
        "/api/v1/auth/login", json={"email": session.email, "password": "wrong-password"}
    )
    assert response.status_code == 401
    error = envelope(response, success=False)["error"]
    assert error["code"] == "UNAUTHORIZED"
    # The message must not reveal whether the account exists.
    assert session.email not in error["message"]


async def test_login_with_unknown_email_is_unauthorized(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_demo_account_has_no_password_and_cannot_log_in(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    """The demo account is reachable through /auth/demo only (password_hash is NULL)."""
    response = await client.post(
        "/api/v1/auth/login", json={"email": "demo@careerforge.ai", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_register_rejects_a_duplicate_email(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    session = await make_user()
    response = await client.post(
        "/api/v1/auth/register", json={"email": session.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 409
    error = envelope(response, success=False)["error"]
    assert error["code"] == "CONFLICT"
    assert error["details"][0]["field"] == "email"


async def test_register_validates_email_and_password_length(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "x" * (MIN_PASSWORD_LENGTH - 1)},
    )
    assert response.status_code == 400
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    fields = {detail["field"] for detail in payload["error"]["details"]}
    assert fields == {"email", "password"}


async def test_login_is_case_insensitive_on_email(
    client: AsyncClient, make_user: UserFactory
) -> None:
    session = await make_user()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": session.email.upper(), "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text


async def test_protected_route_without_token_is_401_with_the_envelope(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "UNAUTHORIZED"
    # docs/API.md §1.1: the request id is echoed on the response header too.
    assert response.headers["x-request-id"] == payload["requestId"]


@pytest.mark.parametrize(
    "header", ["", "Basic YWJjOmRlZg==", "Bearer", "Bearer    ", "Token abc.def.ghi"]
)
async def test_malformed_authorization_headers_are_401(
    client: AsyncClient, envelope: EnvelopeCheck, header: str
) -> None:
    response = await client.get("/api/v1/auth/me", headers={"Authorization": header})
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_expired_access_token_reports_token_expired(
    client: AsyncClient,
    envelope: EnvelopeCheck,
    settings: APISettings,
    make_user: UserFactory,
) -> None:
    """``TOKEN_EXPIRED`` is distinct from ``UNAUTHORIZED`` so the client knows to refresh."""
    session = await make_user()
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": session.id,
            "type": "access",
            "jti": "expired-token-for-test",
            "iss": "careerforge-ai",
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int((now - timedelta(hours=1)).timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "TOKEN_EXPIRED"


async def test_access_token_cannot_be_used_as_a_refresh_token(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    response = await client.post("/api/v1/auth/refresh", json={"refreshToken": demo.access_token})
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_refresh_token_cannot_be_used_as_an_access_token(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {demo.refresh_token}"}
    )
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_token_signed_with_another_secret_is_rejected(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session, settings: APISettings
) -> None:
    now = datetime.now(UTC)
    forged = jwt.encode(
        {
            "sub": demo.id,
            "type": "access",
            "jti": "forged",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        "a-different-secret-entirely-0123456789abcdef",
        algorithm=settings.jwt_algorithm,
    )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_logout_revokes_the_refresh_token(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    logout = await client.post(
        "/api/v1/auth/logout", json={"refreshToken": demo.refresh_token}, headers=demo.headers
    )
    assert logout.status_code == 200
    assert envelope(logout)["data"]["revoked"] is True

    replay = await client.post("/api/v1/auth/refresh", json={"refreshToken": demo.refresh_token})
    assert replay.status_code == 401
    assert envelope(replay, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_logout_requires_authentication(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    response = await client.post("/api/v1/auth/logout", json={"refreshToken": demo.refresh_token})
    assert response.status_code == 401
    assert envelope(response, success=False)["error"]["code"] == "UNAUTHORIZED"


async def test_logout_without_a_body_is_accepted(
    client: AsyncClient, envelope: EnvelopeCheck, demo: Session
) -> None:
    response = await client.post("/api/v1/auth/logout", headers=demo.headers)
    assert response.status_code == 200
    assert envelope(response)["data"]["revoked"] is False


async def test_logout_cannot_revoke_another_accounts_token(
    client: AsyncClient, envelope: EnvelopeCheck, make_user: UserFactory
) -> None:
    """One session must never be able to end another account's session."""
    victim = await make_user()
    attacker = await make_user()

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refreshToken": victim.refresh_token},
        headers=attacker.headers,
    )
    assert response.status_code == 200
    assert envelope(response)["data"]["revoked"] is False

    # The victim's refresh token still works.
    still_valid = await client.post(
        "/api/v1/auth/refresh", json={"refreshToken": victim.refresh_token}
    )
    assert still_valid.status_code == 200


async def test_registration_creates_a_profile(
    client: AsyncClient, app, make_user: UserFactory
) -> None:
    """Registration seeds a profile so later phases have a row to write into."""
    session = await make_user()
    async with app.state.session_factory() as db:
        profile = await UserRepository(db).get_profile(user_id=UUID(session.id))
    assert profile is not None
    # Registered users have no public slug until they publish (PHASE 6).
    assert profile.slug is None
    assert profile.target_roles == ["Embedded Engineer", "AI Application Engineer"]
