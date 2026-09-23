"""Shared test fixtures.

The suite runs against **SQLite with no external services** by default
(``docs/ARCHITECTURE.md`` §1.3, the zero-dependency path), and against PostgreSQL
when ``USE_SQLITE=false`` plus a ``DATABASE_URL`` are configured — which is exactly
what the CI matrix in ``.github/workflows/ci.yml`` does. Nothing here starts a
server, a container or a Redis instance.

Design notes:

* one temporary database per session, one app per test. The app's lifespan is
  idempotent (schema creation, prompt sync, taxonomy sync, demo seed), so re-running
  it is cheap and never double-writes;
* every test creates its own rows with unique emails, so a shared database cannot
  make two tests interfere and the suite is re-runnable;
* the app is built with an explicit :class:`APISettings` object rather than
  environment mutation, which is what makes the rate-limit and production-gate tests
  possible in the same process.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
import itertools
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from careerforge_api.core.config import APISettings
from careerforge_api.db.session import is_sqlite_url
from careerforge_api.main import create_app

#: Test credentials. Long enough for the documented minimum, never a real secret.
TEST_PASSWORD = "sup3r-secret-pw"

#: Budgets high enough that no ordinary test can trip the limiter; the rate-limit
#: test builds its own app with a deliberately small one.
QUIET_LIMITS: dict[str, int] = {
    "rate_limit_auth_per_min": 10_000,
    "rate_limit_read_per_min": 10_000,
    "rate_limit_write_per_min": 10_000,
    "rate_limit_ai_per_min": 10_000,
}


def _database_overrides(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """SQLite gets a throwaway file; a configured PostgreSQL URL is used as-is."""
    probe = APISettings()
    if not is_sqlite_url(probe.resolved_database_url):
        return {}
    directory = tmp_path_factory.mktemp("careerforge-db")
    return {"use_sqlite": True, "sqlite_path": str(directory / "careerforge-test.db")}


@pytest.fixture(scope="session")
def settings_factory(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[..., APISettings]:
    """Build settings with test defaults; per-call overrides win."""
    base: dict[str, Any] = {
        **_database_overrides(tmp_path_factory),
        **QUIET_LIMITS,
        "environment": "test",
        # Keep pytest's output readable: the JSON access log is exercised by
        # test_logging, not by every request in the suite.
        "log_level": "WARNING",
    }

    def factory(**overrides: Any) -> APISettings:
        return APISettings(**{**base, **overrides})

    return factory


@pytest.fixture
def settings(settings_factory: Callable[..., APISettings]) -> APISettings:
    return settings_factory()


@pytest_asyncio.fixture
async def app(settings: APISettings) -> AsyncIterator[FastAPI]:
    """A fully started application (lifespan run) bound to the test database."""
    application = create_app(settings)
    # httpx's ASGITransport does not run lifespan events, so they are run explicitly.
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http


@dataclass(slots=True)
class Session:
    """An authenticated caller, with the raw payloads for contract assertions."""

    email: str
    password: str
    user: dict[str, Any]
    access_token: str
    refresh_token: str
    expires_in: int

    @property
    def id(self) -> str:
        return str(self.user["id"])

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def _session_from_payload(email: str, password: str, data: dict[str, Any]) -> Session:
    return Session(
        email=email,
        password=password,
        user=data["user"],
        access_token=data["accessToken"],
        refresh_token=data["refreshToken"],
        expires_in=data["expiresIn"],
    )


@pytest_asyncio.fixture
async def demo(client: AsyncClient) -> Session:
    """The seeded demo account, obtained exactly the way the UI does it."""
    response = await client.post("/api/v1/auth/demo")
    assert response.status_code == 200, response.text
    return _session_from_payload("demo@careerforge.ai", "", response.json()["data"])


@pytest_asyncio.fixture
async def make_user(client: AsyncClient) -> Callable[..., Awaitable[Session]]:
    """Register a fresh account (unique email per call) and return its session."""
    counter = itertools.count()

    async def factory(
        *,
        password: str = TEST_PASSWORD,
        display_name: str = "Test Candidate",
        email: str | None = None,
    ) -> Session:
        address = email or f"user{next(counter)}-{uuid4().hex[:8]}@example.com"
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": address, "password": password, "displayName": display_name},
        )
        assert response.status_code == 201, response.text
        return _session_from_payload(address, password, response.json()["data"])

    return factory


#: Types for fixtures handed to tests as callables (kept explicit for readability).
UserFactory = Callable[..., Awaitable[Session]]
EnvelopeCheck = Callable[..., dict[str, Any]]


@pytest.fixture
def envelope() -> Callable[[Any], dict[str, Any]]:
    """Assert an httpx response carries the documented envelope and return its data."""

    def check(response: Any, *, success: bool = True) -> dict[str, Any]:
        payload = response.json()
        assert set(payload) == {"success", "data", "error", "requestId"}, payload
        assert payload["success"] is success, payload
        assert payload["requestId"], payload
        assert payload["requestId"] == response.headers["x-request-id"]
        if success:
            assert payload["error"] is None
        else:
            assert payload["data"] is None
            assert payload["error"]["code"]
            assert isinstance(payload["error"]["details"], list)
        return payload

    return check
