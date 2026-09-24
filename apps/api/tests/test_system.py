"""``/system/health`` and ``/system/info`` — real probes, honest answers.

``docs/API.md`` §2.13 describes both endpoints without freezing the health body, so
the contract asserted here is the one that has a second consumer: the normalisation
in ``apps/web``'s health grid (``{status, services:[{name,status,...}]}``, mirrored by
``packages/shared``'s ``SystemHealthResponse``).
"""

from __future__ import annotations

import json

from httpx import AsyncClient

from careerforge_api import __version__
from careerforge_api.core.config import APISettings
from tests.conftest import EnvelopeCheck


async def test_health_reports_a_working_database_and_the_active_backends(
    client: AsyncClient, envelope: EnvelopeCheck, settings: APISettings
) -> None:
    response = await client.get("/api/v1/system/health")
    assert response.status_code == 200
    data = envelope(response)["data"]

    # Overall status is worst-wins across the probes; it is derived, not hard-coded.
    assert data["status"] in {"ok", "degraded", "down", "unknown"}
    assert data["checkedAt"]
    assert data["version"]["api"] == __version__

    by_name = data["checks"]
    assert set(by_name) == {"api", "database", "vector", "queue", "llm_provider"}
    # `services` is the same data as an array, for clients that prefer it.
    assert [entry["name"] for entry in data["services"]] == [
        "api",
        "database",
        "vector",
        "queue",
        "llm_provider",
    ]

    database = by_name["database"]
    assert database["status"] == "ok"
    assert database["backend"] == ("sqlite" if settings.use_sqlite else "postgresql")
    assert database["latencyMs"] >= 0
    assert (
        "SELECT 1" in database["detail"]
        or "SQLite" in database["detail"]
        or "PostgreSQL" in database["detail"]
    )


async def test_health_reports_the_queue_backend_that_is_actually_running(
    client: AsyncClient, envelope: EnvelopeCheck, settings: APISettings
) -> None:
    data = envelope(await client.get("/api/v1/system/health"))["data"]
    queue = data["checks"]["queue"]
    # No Redis on this machine: the in-process queue is reported, with a reason.
    assert queue["backend"] == "inprocess"
    assert queue["extra"]["configured"] == settings.queue_backend
    if settings.queue_backend != "inprocess":
        assert queue["status"] == "degraded"


async def test_health_reports_the_provider_chain_and_its_degradation(
    client: AsyncClient, envelope: EnvelopeCheck, settings: APISettings
) -> None:
    """docs/API.md §1.8: degradation must be visible, with the reason."""
    data = envelope(await client.get("/api/v1/system/health"))["data"]
    provider = data["checks"]["llm_provider"]

    assert provider["provider"] == "heuristic"
    assert provider["degraded"] is True
    assert provider["reason"] == "no_api_key"
    assert provider["status"] == "degraded"
    assert provider["extra"]["chain"] == ["heuristic"]
    assert provider["extra"]["requested"] == settings.llm_provider
    # The degradation is echoed in the documented `meta` block.
    assert data["meta"]["provider"] == "heuristic"
    assert data["meta"]["degraded"] is True
    assert data["meta"]["tookMs"] >= 0


async def test_health_reports_the_vector_backend_honestly(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    """Semantic retrieval works, from an index that does not survive a restart — and the health
    page says exactly that.

    It reported ``not_implemented`` until PHASE 11, which stopped being true in PHASE 3: the
    hybrid retriever (BM25 + vectors, RRF-fused, ADR-0006) is what answers retrieval for the claim
    gate and the graph query. The remaining gap is durability, and the assertion names it rather
    than letting the old label keep standing — a health page that under-reports is wrong in the
    same way as one that over-reports.
    """
    data = envelope(await client.get("/api/v1/system/health"))["data"]
    vector = data["checks"]["vector"]
    assert vector["reason"] == "in_memory_index"
    assert vector["status"] == "degraded"
    assert vector["backend"] in {"sqlite", "pgvector"}
    # The detail must name both halves: what serves retrieval, and what is missing.
    assert "in-process" in vector["detail"]
    assert "durable" in vector["detail"]


async def test_health_is_public_and_needs_no_token(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    """The compose healthcheck and uptime monitors call it anonymously."""
    data = envelope(await client.get("/api/v1/system/health"))["data"]
    assert data["checks"]["api"]["status"] == "ok"


async def test_info_reports_version_commit_and_runtimes(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.get("/api/v1/system/info")
    assert response.status_code == 200
    data = envelope(response)["data"]

    assert data["name"] == "CareerForge AI"
    assert data["version"] == __version__
    assert data["apiPrefix"] == "/api/v1"
    assert data["pythonVersion"].startswith("3.12")
    assert data["startedAt"]
    assert data["uptimeSeconds"] >= 0
    # The commit hash is read from .git (or GIT_SHA); None is acceptable outside a checkout.
    if data["commitHash"] is not None:
        assert data["commitHashShort"] == data["commitHash"][:7]


async def test_info_reports_prompts_and_redacted_configuration(
    client: AsyncClient, envelope: EnvelopeCheck, settings: APISettings
) -> None:
    data = envelope(await client.get("/api/v1/system/info"))["data"]

    assert data["prompts"]["count"] == 10
    assert "jd_analysis" in data["prompts"]["names"]
    assert data["database"]["backend"] == ("sqlite" if settings.use_sqlite else "postgresql")
    assert data["queue"]["active"] == "inprocess"
    assert data["vector"]["implemented"] is False
    # Every block has to be populated: an alias typo would silently produce an empty
    # dict, because pydantic ignores unknown construction keywords.
    assert data["rateLimits"] == {
        "authPerMinutePerIp": settings.rate_limit_auth_per_min,
        "readPerMinutePerUser": settings.rate_limit_read_per_min,
        "writePerMinutePerUser": settings.rate_limit_write_per_min,
        "aiPerMinutePerUser": settings.rate_limit_ai_per_min,
        "uploadPerHourPerUser": 20,
        "enabled": settings.rate_limit_enabled,
    }
    for block in ("database", "queue", "vector", "providers", "prompts"):
        assert data[block], f"/system/info reported an empty {block} block"

    providers = data["providers"]
    assert providers["active"] == "heuristic"
    assert providers["chain"] == ["heuristic"]
    assert providers["api_keys_present"] == {
        "deepseek": False,
        "openai": False,
        "github": False,
    }
    # No credential material may appear anywhere in the payload.
    body = json.dumps(data)
    assert settings.jwt_secret not in body
    assert "sk-proj-" not in body
    for key in ("apiKey", "api_key", "secret", "password", "token"):
        assert f'"{key}"' not in body, f"/system/info leaked a field named {key}"


async def test_info_keeps_the_sqlite_url_readable(
    client: AsyncClient, envelope: EnvelopeCheck, settings: APISettings
) -> None:
    """A SQLite URL has no credentials, so it is reported unchanged."""
    data = envelope(await client.get("/api/v1/system/info"))["data"]
    assert data["database"]["url"] == settings.resolved_database_url
    assert "***" not in data["database"]["url"]


def test_redact_dsn_removes_only_the_password() -> None:
    """A DSN carries a password; /system/info must never echo it."""
    from careerforge_api.services.system_service import redact_dsn

    assert (
        redact_dsn("postgresql+asyncpg://careerforge:super-secret-pw@localhost:5432/careerforge")
        == "postgresql+asyncpg://careerforge:***@localhost:5432/careerforge"
    )
    assert redact_dsn("postgresql+asyncpg://careerforge@localhost/db") == (
        "postgresql+asyncpg://careerforge@localhost/db"
    )
    assert redact_dsn("sqlite+aiosqlite:///C:/tmp/careerforge.db") == (
        "sqlite+aiosqlite:///C:/tmp/careerforge.db"
    )
