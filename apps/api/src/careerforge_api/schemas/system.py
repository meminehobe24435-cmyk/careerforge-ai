"""System models: ``GET /system/health`` and ``GET /system/info``.

``docs/API.md`` §2.13 describes health as "API / DB / Redis / Vector / LLM provider
status" but does not freeze the body, so the shape here is chosen to satisfy the one
consumer that already exists: ``apps/web``'s health grid normalises
``{ status, services: [{ name, status, detail, latencyMs, version }] }``
(``packages/shared/src/api/types.ts`` → ``SystemHealthResponse``).

``checks`` mirrors the same entries keyed by name, which is what a log-scraper,
``curl | jq .data.checks.database.status`` or an uptime monitor wants. The two
views are generated from one list, so they cannot disagree.

``status`` is **not** forced to ``ok``: a healthy API over SQLite with no API key
really is ``degraded`` — the heuristic provider is serving the AI features and the
documented rule is to say so rather than pretend (``docs/API.md`` §1.8).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from careerforge_api.schemas.envelope import ApiMeta

__all__ = [
    "HealthStatus",
    "ReadinessStatus",
    "ServiceHealthEntry",
    "SystemHealthResponse",
    "SystemInfoResponse",
    "SystemReadinessResponse",
    "SystemVersionResponse",
]

HealthStatus = Literal["ok", "degraded", "down", "unknown"]

#: ``ready`` is a promise the instance can serve traffic; ``not_ready`` is not. There is no
#: ``degraded`` readiness: a deployment with no API key is *ready* and says which dependency is
#: degraded, because a readiness probe that fails on a degraded optional dependency makes an
#: orchestrator kill a working instance (PHASE 14).
ReadinessStatus = Literal["ready", "not_ready"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ServiceHealthEntry(_CamelModel):
    """One probe result."""

    #: Stable key, e.g. ``api`` · ``database`` · ``vector`` · ``queue`` · ``llm_provider``.
    name: str
    status: HealthStatus
    #: Human explanation, already redacted server-side.
    detail: str | None = None
    latency_ms: int | None = Field(default=None, alias="latencyMs")
    version: str | None = None
    #: Which implementation is actually serving: ``sqlite`` / ``inprocess`` / ``heuristic``.
    backend: str | None = None
    #: Present on ``llm_provider`` — the provider that would serve the next call.
    provider: str | None = None
    #: Present on ``llm_provider`` — must never be hidden from the UI.
    degraded: bool | None = None
    #: Why it is degraded (``no_api_key``, ``provider_error``, ``not_implemented`` …).
    reason: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SystemHealthResponse(_CamelModel):
    """``data`` of ``GET /system/health``."""

    status: HealthStatus
    services: list[ServiceHealthEntry] = Field(default_factory=list)
    #: The same entries keyed by name, for tools that prefer a map.
    checks: dict[str, ServiceHealthEntry] = Field(default_factory=dict)
    version: dict[str, str] = Field(default_factory=dict)
    checked_at: datetime = Field(alias="checkedAt")
    meta: ApiMeta = Field(default_factory=ApiMeta)


class SystemInfoResponse(_CamelModel):
    """``data`` of ``GET /system/info`` — build metadata and redacted configuration."""

    name: str
    version: str
    environment: str
    debug: bool
    build_time: str | None = Field(default=None, alias="buildTime")
    commit_hash: str | None = Field(default=None, alias="commitHash")
    commit_hash_short: str | None = Field(default=None, alias="commitHashShort")
    python_version: str = Field(alias="pythonVersion")
    node_version: str | None = Field(default=None, alias="nodeVersion")
    api_prefix: str = Field(alias="apiPrefix")
    started_at: datetime = Field(alias="startedAt")
    uptime_seconds: float = Field(alias="uptimeSeconds")
    database: dict[str, Any] = Field(default_factory=dict)
    queue: dict[str, Any] = Field(default_factory=dict)
    vector: dict[str, Any] = Field(default_factory=dict)
    providers: dict[str, Any] = Field(default_factory=dict)
    rate_limits: dict[str, Any] = Field(default_factory=dict, alias="rateLimits")
    prompts: dict[str, Any] = Field(default_factory=dict)


class SystemReadinessResponse(_CamelModel):
    """``data`` of ``GET /system/ready`` — the probe an orchestrator may act on.

    Readiness is **one gate**: the database. A request that reaches the API is answered by a
    running process, so the process itself cannot be the thing that is not ready; what can be
    missing is the store the process reads. Redis (the queue), the vector index and the LLM
    provider are *optional in this deployment* — a zero-key install serves the whole product on
    the deterministic provider — so a degraded one is **named in ``degraded``** and reported in
    ``dependencies``, and the status stays ``ready``.

    That distinction is the whole point of the endpoint. ``GET /system/health`` answers "how is
    this deployment doing" and reports ``degraded`` for the normal zero-key install, which is
    correct; a readiness probe that copied that answer would mark every public demo instance
    unhealthy.
    """

    status: ReadinessStatus
    ready: bool
    #: Which dependency decides readiness. Named in the payload so a reader does not have to
    #: guess from the code which of the five entries is load-bearing.
    gate: str = "database"
    environment: str
    checked_at: datetime = Field(alias="checkedAt")
    #: Every probe, including the ones that do not gate readiness.
    dependencies: list[ServiceHealthEntry] = Field(default_factory=list)
    #: Names of dependencies that are degraded or down but do not make the instance unready.
    degraded: list[str] = Field(default_factory=list)
    version: dict[str, str] = Field(default_factory=dict)
    meta: ApiMeta = Field(default_factory=ApiMeta)


class SystemVersionResponse(_CamelModel):
    """``data`` of ``GET /system/version`` — build identity, and nothing else.

    Deliberately narrow, and narrower than ``/system/info`` on purpose. ``/system/info`` is the
    configuration dump, and it legitimately reports things such as the database URL — which for
    the SQLite path *is* an absolute file path, and for PostgreSQL is an absolute host name. The
    `/system` page needs four facts (version, commit, build timestamp, environment) and must
    publish them on a public endpoint, so they get their own response model in which every field
    is a constant-shape identifier: no DSN, no directory, no host, no credential material, and
    nothing that reflects user input.
    """

    app: str
    version: str
    #: Full commit hash, or ``None`` when the deployment did not record one.
    commit: str | None = None
    commit_short: str | None = Field(default=None, alias="commitShort")
    #: ISO-8601, injected at image build time; ``None`` when no build recorded one. A missing
    #: value is reported as missing rather than filled in with "now", which would be a lie that
    #: changes on every request.
    build_timestamp: str | None = Field(default=None, alias="buildTimestamp")
    environment: str
    python_version: str = Field(alias="pythonVersion")
    node_version: str | None = Field(default=None, alias="nodeVersion")
    schema_version: str = Field(alias="schemaVersion")
    taxonomy_version: str = Field(alias="taxonomyVersion")
    checked_at: datetime = Field(alias="checkedAt")
