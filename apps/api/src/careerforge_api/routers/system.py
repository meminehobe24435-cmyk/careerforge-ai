"""``/system`` — health, readiness, version and build information (``docs/API.md`` §2.13).

Every endpoint here is **public**: ``docker-compose.yml`` and every uptime monitor probe
``/api/v1/system/*`` without a token, and ``docs/API.md`` §2.13 marks none of them as
authenticated. The four answer four different questions, and keeping them separate is what stops
one of them from being asked the wrong one:

* ``/health`` — *how is this deployment doing?* Real probes, worst-wins ``status``; a zero-key
  install is honestly ``degraded``;
* ``/ready`` — *may traffic be sent here?* One gate (the database). A degraded optional
  dependency is **named**, not fatal, so an orchestrator does not kill a working instance;
* ``/version`` — *which build answered me?* Four identifiers, safe to publish;
* ``/info`` — the full configuration dump, with API keys reduced to booleans.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from careerforge_api.core.errors import DependencyUnavailableError
from careerforge_api.deps import SettingsDep
from careerforge_api.schemas.system import (
    SystemHealthResponse,
    SystemInfoResponse,
    SystemReadinessResponse,
    SystemVersionResponse,
)
from careerforge_api.services.system_service import (
    collect_health,
    collect_info,
    collect_readiness,
    collect_version,
)

__all__ = ["router"]

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", summary="Live dependency and provider status")
async def health(request: Request, settings: SettingsDep) -> SystemHealthResponse:
    """Probes the database, the vector backend, the queue backend and the provider chain.

    Always HTTP 200 when the process can answer at all: the *body* reports
    ``ok``/``degraded``/``down`` per dependency, which is what a monitor needs to
    distinguish "API is dead" from "the API is up but degraded".
    """
    state = request.app.state
    return await collect_health(
        settings=settings,
        engine=state.engine,
        provider=getattr(state, "provider", None),
        queue_backend=getattr(state, "queue_backend", "inprocess"),
        queue_degradation_reason=getattr(state, "queue_degradation_reason", None),
    )


@router.get(
    "/ready",
    summary="Readiness: may this instance be sent traffic?",
    responses={503: {"description": "The readiness gate (the database) is not reachable"}},
)
async def ready(request: Request, settings: SettingsDep) -> SystemReadinessResponse:
    """Ready **iff** the database answers.

    ``503 DEPENDENCY_UNAVAILABLE`` when it does not, because that is the status an orchestrator
    acts on and a readiness probe whose HTTP status never changes is not a readiness probe. The
    explanation is not lost on the way out: the error envelope's ``details`` carries every probe,
    so a caller that sees the 503 can still read *which* dependency failed and why.

    Everything that is merely degraded — the queue falling back to in-process, the in-memory
    vector index, the deterministic provider on a zero-key install — is listed in ``degraded`` and
    described in ``dependencies`` while the answer stays ``ready``.
    """
    state = request.app.state
    payload = await collect_readiness(
        settings=settings,
        engine=state.engine,
        provider=getattr(state, "provider", None),
        queue_backend=getattr(state, "queue_backend", "inprocess"),
        queue_degradation_reason=getattr(state, "queue_degradation_reason", None),
    )
    if not payload.ready:
        raise DependencyUnavailableError(
            f"readiness gate '{payload.gate}' is not reachable; "
            f"degraded without gating readiness: {', '.join(payload.degraded) or 'none'}",
            details=[
                {
                    "field": entry.name,
                    "issue": entry.status,
                    "message": entry.detail or "",
                }
                for entry in payload.dependencies
            ],
        )
    return payload


@router.get("/version", summary="App version, git commit, build timestamp and environment")
async def version(settings: SettingsDep) -> SystemVersionResponse:
    """The four facts the public ``/system`` page prints, and nothing else.

    No DSN, no directory, no host name — see
    :class:`careerforge_api.schemas.system.SystemVersionResponse` for why this is a separate
    response model rather than a slice of ``/system/info``.
    """
    return collect_version(settings=settings)


@router.get("/info", summary="Version, commit, runtimes and redacted configuration")
async def info(request: Request, settings: SettingsDep) -> SystemInfoResponse:
    state = request.app.state
    registry = getattr(state, "prompt_registry", None)
    return collect_info(
        settings=settings,
        provider=getattr(state, "provider", None),
        queue_backend=getattr(state, "queue_backend", "inprocess"),
        started_at=getattr(state, "started_at", 0.0),
        prompt_count=len(registry) if registry is not None else 0,
        prompt_names=list(registry.names()) if registry is not None else [],
    )
