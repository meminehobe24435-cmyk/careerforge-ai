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
    "ServiceHealthEntry",
    "SystemHealthResponse",
    "SystemInfoResponse",
]

HealthStatus = Literal["ok", "degraded", "down", "unknown"]


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
    rate_limits: dict[str, Any] = Field(default_factory=dict)
    prompts: dict[str, Any] = Field(default_factory=dict)
