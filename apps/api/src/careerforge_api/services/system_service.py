"""System probes: ``GET /system/health`` and ``GET /system/info``.

Health is a set of **real** probes, not a hard-coded ``{"status": "ok"}``:

* ``database`` — executes ``SELECT 1`` on the configured engine and reports the
  backend that actually answered;
* ``queue`` — reports the implementation that is really serving tasks, and says so
  when the configured one is not available in this process;
* ``vector`` — reports the configured backend and is explicit that no vector index
  exists yet in PHASE 1 (pretending otherwise would make the health page lie);
* ``llm_provider`` — reports the provider that would serve the next call, whether it
  is degraded, and **why** (``docs/API.md`` §1.8 forbids hiding degradation).

The overall ``status`` is derived from those entries (worst-wins), so a healthy API
over SQLite with the heuristic provider reports ``degraded`` — which is the truth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
import shutil
import subprocess
import sys
import time

from sqlalchemy.ext.asyncio import AsyncEngine

from careerforge_ai.parsing.skill_taxonomy import TAXONOMY_VERSION
from careerforge_ai.providers import LLMProvider
from careerforge_ai.schemas.common import DegradationReason
from careerforge_api import __version__
from careerforge_api.core.config import APISettings
from careerforge_api.core.logging import get_logger
from careerforge_api.db.session import is_sqlite_url, ping
from careerforge_api.schemas.system import (
    HealthStatus,
    ServiceHealthEntry,
    SystemHealthResponse,
    SystemInfoResponse,
    SystemReadinessResponse,
    SystemVersionResponse,
)

__all__ = [
    "collect_health",
    "collect_info",
    "collect_readiness",
    "collect_version",
    "detect_git_sha",
    "detect_node_version",
    "overall_status",
    "probe_api",
    "probe_database",
    "probe_provider",
    "probe_queue",
    "probe_vector",
    "redact_dsn",
]

_logger = get_logger("careerforge_api.services.system")

#: Worst-wins ordering for the aggregate status.
_STATUS_SEVERITY: dict[str, int] = {"ok": 0, "unknown": 1, "degraded": 2, "down": 3}

_NODE_CHECK_TIMEOUT_SECONDS = 2.0


async def probe_database(engine: AsyncEngine, settings: APISettings) -> ServiceHealthEntry:
    """``SELECT 1`` against the configured database."""
    backend = "sqlite" if is_sqlite_url(settings.resolved_database_url) else "postgresql"
    started = time.perf_counter()
    try:
        await ping(engine)
    except Exception as exc:
        _logger.error(
            "database_probe_failed",
            extra={"event": "database_probe_failed", "backend": backend, "detail": str(exc)},
        )
        return ServiceHealthEntry(
            name="database",
            status="down",
            backend=backend,
            detail=f"{type(exc).__name__}: {exc}",
        )
    latency_ms = int((time.perf_counter() - started) * 1000)
    return ServiceHealthEntry(
        name="database",
        status="ok",
        backend=backend,
        latency_ms=latency_ms,
        detail=(
            "SQLite (aiosqlite) · WAL, foreign_keys=ON, busy_timeout=5000"
            if backend == "sqlite"
            else "PostgreSQL (asyncpg)"
        ),
    )


def probe_vector(settings: APISettings) -> ServiceHealthEntry:
    """Report the vector arm as it really is: implemented, in memory, not yet durable.

    This used to say ``not_implemented``, which stopped being true in PHASE 3 — the hybrid
    retriever (BM25 + vectors, RRF-fused, ADR-0006) is what answers retrieval for the claim gate
    and the graph query. What is *still* missing is the durable index: embeddings live in the
    process, so a restart re-embeds and a second worker would keep its own copy. Saying
    "implemented" without that caveat would be the same mistake in the other direction.
    """
    configured = settings.vector_backend or "sqlite"
    return ServiceHealthEntry(
        name="vector",
        status="degraded",
        backend=configured,
        reason="in_memory_index",
        detail=(
            f"vector backend is configured as '{configured}'; semantic retrieval is served by the "
            "in-process hybrid index (BM25 + vectors, RRF-fused, ADR-0006), which is rebuilt per "
            "process — a durable embeddings table (and pgvector on the PostgreSQL path) is not "
            "implemented yet, so a restart re-embeds and a second worker keeps its own copy"
        ),
    )


def probe_queue(
    *,
    settings: APISettings,
    active_backend: str,
    degradation_reason: str | None = None,
) -> ServiceHealthEntry:
    """Report which queue implementation is actually serving tasks."""
    configured = settings.queue_backend or "inprocess"
    status: HealthStatus = "ok" if active_backend == configured else "degraded"
    detail = (
        "in-process asyncio queue; job state is still persisted in background_jobs"
        if active_backend == "inprocess"
        else f"{active_backend} queue"
    )
    if status == "degraded":
        detail = (
            f"configured backend '{configured}' is not available in this process; "
            f"falling back to '{active_backend}' ({degradation_reason or 'not_implemented'}). "
            "Task state remains durable in background_jobs but runs inside the API process"
        )
    return ServiceHealthEntry(
        name="queue",
        status=status,
        backend=active_backend,
        reason=degradation_reason,
        detail=detail,
        extra={"configured": configured},
    )


def probe_provider(settings: APISettings, provider: LLMProvider | None) -> ServiceHealthEntry:
    """Report the provider chain: who serves, whether it is degraded, and why."""
    chain = settings.active_provider_chain()
    active = provider.name if provider is not None else (chain[0] if chain else "unknown")
    degraded = active == "heuristic" or not settings.provider_is_configured(settings.llm_provider)
    reason = DegradationReason.NO_API_KEY.value if degraded else DegradationReason.NONE.value
    capabilities = provider.capabilities if provider is not None else None
    detail = f"serving with '{active}'" + (
        f": the requested provider '{settings.llm_provider}' is not configured, "
        "so answers come from the deterministic heuristic provider"
        if degraded
        else ""
    )
    return ServiceHealthEntry(
        name="llm_provider",
        status="degraded" if degraded else "ok",
        backend=active,
        provider=active,
        degraded=degraded,
        reason=reason,
        detail=detail,
        extra={
            "requested": settings.llm_provider,
            "fallback": settings.llm_fallback_provider,
            "chain": list(chain),
            "deterministic": bool(capabilities.deterministic) if capabilities else None,
            "models": {
                "deepseek": settings.deepseek_model,
                "openai": settings.openai_model,
                "ollama": settings.ollama_model,
            },
        },
    )


def probe_api(settings: APISettings) -> ServiceHealthEntry:
    """The API process itself (reaching this entry at all means it is up)."""
    return ServiceHealthEntry(
        name="api",
        status="ok",
        version=__version__,
        backend="fastapi",
        detail=f"uvicorn · environment={settings.environment} · python={sys.version.split()[0]}",
    )


def overall_status(entries: list[ServiceHealthEntry]) -> HealthStatus:
    """Worst-wins aggregate, so a degraded dependency cannot be hidden by an ``ok`` peer."""
    return max(  # type: ignore[return-value]
        (entry.status for entry in entries),
        key=lambda status: _STATUS_SEVERITY.get(status, 1),
        default="unknown",
    )


async def collect_health(
    *,
    settings: APISettings,
    engine: AsyncEngine,
    provider: LLMProvider | None,
    queue_backend: str,
    queue_degradation_reason: str | None = None,
) -> SystemHealthResponse:
    """Run every probe and assemble the documented health payload."""
    began = time.perf_counter()
    provider_entry = probe_provider(settings, provider)
    services = [
        probe_api(settings),
        await probe_database(engine, settings),
        probe_vector(settings),
        probe_queue(
            settings=settings,
            active_backend=queue_backend,
            degradation_reason=queue_degradation_reason,
        ),
        provider_entry,
    ]
    took_ms = int((time.perf_counter() - began) * 1000)
    return SystemHealthResponse(
        status=overall_status(services),
        services=services,
        checks={entry.name: entry for entry in services},
        version={
            "api": __version__,
            "python": sys.version.split()[0],
            "schemas": "v1",
            "taxonomy": TAXONOMY_VERSION,
        },
        checked_at=datetime.now(UTC),
        meta={
            "provider": provider_entry.provider,
            "degraded": bool(provider_entry.degraded),
            "cacheHit": False,
            "tookMs": took_ms,
        },
    )


# ── /system/ready ────────────────────────────────────────────────────────────

#: The single dependency that decides readiness. Everything else is advisory — see
#: :class:`careerforge_api.schemas.system.SystemReadinessResponse`.
READINESS_GATE = "database"


async def collect_readiness(
    *,
    settings: APISettings,
    engine: AsyncEngine,
    provider: LLMProvider | None,
    queue_backend: str,
    queue_degradation_reason: str | None = None,
) -> SystemReadinessResponse:
    """Run the probes and answer the one question a load balancer asks.

    Only the ``database`` probe does I/O; the other four are pure functions over settings and the
    live process, so running all five costs one ``SELECT 1`` and lets the payload name every
    degraded dependency instead of just the gate.
    """
    began = time.perf_counter()
    provider_entry = probe_provider(settings, provider)
    services = [
        probe_api(settings),
        await probe_database(engine, settings),
        probe_vector(settings),
        probe_queue(
            settings=settings,
            active_backend=queue_backend,
            degradation_reason=queue_degradation_reason,
        ),
        provider_entry,
    ]
    gate = next(entry for entry in services if entry.name == READINESS_GATE)
    ready = gate.status == "ok"
    degraded = sorted(
        entry.name for entry in services if entry.name != READINESS_GATE and entry.status != "ok"
    )
    return SystemReadinessResponse(
        status="ready" if ready else "not_ready",
        ready=ready,
        gate=READINESS_GATE,
        environment=settings.environment,
        checked_at=datetime.now(UTC),
        dependencies=services,
        degraded=degraded,
        version={"api": __version__, "python": sys.version.split()[0], "schemas": "v1"},
        meta={
            "provider": provider_entry.provider,
            "degraded": bool(provider_entry.degraded),
            "cacheHit": False,
            "tookMs": int((time.perf_counter() - began) * 1000),
        },
    )


# ── /system/version ──────────────────────────────────────────────────────────


def collect_version(*, settings: APISettings) -> SystemVersionResponse:
    """Build identity for the public ``/system`` page — four facts, no environment details.

    Every value here is an identifier whose *shape* is fixed (a version, a hash, an ISO-8601
    string, an environment name) or a runtime version read from the interpreter. Nothing is
    derived from a path, a URL or a request, which is what makes it safe to serve anonymously.
    """
    sha = detect_git_sha(settings)
    return SystemVersionResponse(
        app=settings.app_name,
        version=__version__,
        commit=sha or None,
        commit_short=sha[:7] if sha else None,
        build_timestamp=settings.build_time.strip() or None,
        environment=settings.environment,
        python_version=sys.version.split()[0],
        node_version=detect_node_version(),
        schema_version="v1",
        taxonomy_version=TAXONOMY_VERSION,
        checked_at=datetime.now(UTC),
    )


# ── /system/info ─────────────────────────────────────────────────────────────


def detect_git_sha(settings: APISettings) -> str:
    """Resolve the commit hash without shelling out.

    ``GIT_SHA`` (injected by CI or the Docker build) wins; otherwise the value is
    read from ``.git`` directly. A ``git`` subprocess would add a runtime dependency
    on a binary that is not in the production image — and would fail there.
    """
    if settings.git_sha:
        return settings.git_sha.strip()
    git_dir = Path(settings.repo_root) / ".git"
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head.startswith("ref:"):
            ref_path = git_dir / head.split(" ", 1)[1].strip()
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()
            packed = git_dir / "packed-refs"
            if packed.exists():
                reference = head.split(" ", 1)[1].strip()
                for line in packed.read_text(encoding="utf-8").splitlines():
                    if line.endswith(reference) and not line.startswith(("#", "^")):
                        return line.split(" ", 1)[0].strip()
            return ""
        return head
    except OSError:
        return ""


@lru_cache(maxsize=1)
def detect_node_version() -> str | None:
    """``node --version`` when Node is on ``PATH``; ``None`` otherwise.

    Informational only (``docs/API.md`` §2.13) — a missing Node must never make the
    API unhealthy, so every failure mode returns ``None``.
    """
    binary = shutil.which("node")
    if binary is None:
        return None
    try:
        completed = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=_NODE_CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip().lstrip("v") or None


def collect_info(
    *,
    settings: APISettings,
    provider: LLMProvider | None,
    queue_backend: str,
    started_at: float,
    prompt_count: int = 0,
    prompt_names: list[str] | None = None,
) -> SystemInfoResponse:
    """Build ``GET /system/info`` — build metadata plus redacted configuration.

    Constructed with field names; FastAPI serialises the response ``by_alias=True``, so
    the payload is camelCase on the wire.
    """
    sha = detect_git_sha(settings)
    return SystemInfoResponse(
        name=settings.app_name,
        version=__version__,
        environment=settings.environment,
        debug=settings.debug,
        build_time=settings.build_time or None,
        commit_hash=sha or None,
        commit_hash_short=sha[:7] if sha else None,
        python_version=sys.version.split()[0],
        node_version=detect_node_version(),
        api_prefix=settings.api_prefix,
        started_at=datetime.fromtimestamp(started_at, tz=UTC),
        uptime_seconds=round(max(0.0, time.time() - started_at), 3),
        database={
            "backend": "sqlite" if is_sqlite_url(settings.resolved_database_url) else "postgresql",
            # Credentials are stripped: a DSN carries a password.
            "url": redact_dsn(settings.resolved_database_url),
            "vectorBackend": settings.vector_backend,
            "embeddingDim": settings.embedding_dim,
        },
        queue={
            "configured": settings.queue_backend,
            "active": queue_backend,
            "workerConcurrency": settings.worker_concurrency,
        },
        vector={
            "backend": settings.vector_backend,
            "topK": settings.vector_top_k,
            "rrfK": settings.rrf_k,
            "implemented": False,
        },
        providers={
            **settings.redacted_provider_config(),
            "active": provider.name if provider is not None else None,
            "capabilities": (
                {
                    "streaming": provider.capabilities.supports_streaming,
                    "embeddings": provider.capabilities.supports_embeddings,
                    "nativeJsonSchema": provider.capabilities.supports_native_json_schema,
                    "deterministic": provider.capabilities.deterministic,
                }
                if provider is not None
                else None
            ),
        },
        rateLimits={
            "authPerMinutePerIp": settings.rate_limit_auth_per_min,
            "readPerMinutePerUser": settings.rate_limit_read_per_min,
            "writePerMinutePerUser": settings.rate_limit_write_per_min,
            "aiPerMinutePerUser": settings.rate_limit_ai_per_min,
            "uploadPerHourPerUser": settings.rate_limit_upload_per_hour,
            "enabled": settings.rate_limit_enabled,
        },
        prompts={
            "count": prompt_count,
            "names": sorted(prompt_names or []),
            "directory": str(settings.resolved_prompts_dir),
        },
    )


def redact_dsn(url: str) -> str:
    """Remove the password from a DSN before it is ever serialised.

    A user without a password (common for local trust authentication) is left alone, so
    the redaction never invents credentials that are not there.
    """
    if "@" not in url or "://" not in url:
        return url
    scheme, remainder = url.split("://", 1)
    credentials, _, host = remainder.rpartition("@")
    if not credentials or ":" not in credentials:
        return url
    user = credentials.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"
