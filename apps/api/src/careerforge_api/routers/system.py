"""``/system`` — health and build information (``docs/API.md`` §2.13).

Both endpoints are **public**: ``docker-compose.yml`` and every uptime monitor probe
``/api/v1/system/health`` without a token, and ``docs/API.md`` §2.13 marks neither
endpoint as authenticated. They expose no user data and no secrets — ``/system/info``
publishes provider *configuration* with the API keys reduced to booleans.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from careerforge_api.deps import SettingsDep
from careerforge_api.schemas.system import SystemHealthResponse, SystemInfoResponse
from careerforge_api.services.system_service import collect_health, collect_info

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
