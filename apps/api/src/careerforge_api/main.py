"""Application factory: lifespan, model setup and the documented middleware chain.

``create_app()`` is the only place that assembles the process:

1. **Configuration** — :class:`~careerforge_api.core.config.APISettings` (an extension
   of the AI core's settings; the database URL, vector/queue backends, provider chain
   and prompt directory all come from ``careerforge_ai.config.Settings``, so there is
   one source of truth for configuration).
2. **Security gate** — a production deployment still carrying the development
   ``JWT_SECRET`` refuses to start (``docs/ARCHITECTURE.md`` §10).
3. **Lifespan** — create the tables when running on SQLite, load the prompt registry
   from ``prompts/``, build the provider chain **once** with
   ``careerforge_ai.providers.build_provider``, mirror prompts and the skill taxonomy
   into the database, seed the demo account, and build the queue.
4. **Middleware** — added innermost-first so the resulting stack matches
   ``docs/ARCHITECTURE.md`` §8.2; see
   :mod:`careerforge_api.middleware` for the ordering rationale.
5. **Routers** — mounted under ``settings.api_prefix``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from careerforge_ai.prompting.registry import PromptRegistry, load_prompt_registry
from careerforge_ai.providers import build_provider
from careerforge_api import __version__
from careerforge_api.core.config import (
    APISettings,
    assert_runtime_configuration,
    get_api_settings,
)
from careerforge_api.core.logging import configure_logging, get_logger
from careerforge_api.db.session import (
    create_all,
    create_engine,
    create_session_factory,
    session_scope,
)
from careerforge_api.middleware.envelope import EnvelopeMiddleware
from careerforge_api.middleware.errors import ErrorHandlingMiddleware, register_exception_handlers
from careerforge_api.middleware.logging import RequestLoggingMiddleware
from careerforge_api.middleware.ratelimit import RateLimitMiddleware, TokenBucketLimiter
from careerforge_api.middleware.request_id import RequestIDMiddleware
from careerforge_api.repositories.prompt_repository import PromptRepository
from careerforge_api.routers import ai, auth, documents, evidence, jobs, system, tasks
from careerforge_api.services.ai_service import InterviewSessionStore
from careerforge_api.services.auth_service import TokenRevocationRegistry
from careerforge_api.services.seed_service import ensure_demo_user
from careerforge_api.services.skill_taxonomy_service import sync_skill_taxonomy
from careerforge_api.workers.handlers import register_default_handlers
from careerforge_api.workers.queue import build_queue_selection

__all__ = ["app", "create_app", "lifespan"]

logger = get_logger("careerforge_api.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Prepare shared state on the way in and release it on the way out."""
    settings: APISettings = app.state.settings
    app.state.started_at = time.time()

    engine = create_engine(settings)
    app.state.engine = engine
    session_factory = create_session_factory(engine)
    app.state.session_factory = session_factory

    if settings.use_sqlite:
        # The zero-dependency path has no migration step: `alembic upgrade head`
        # produces the same schema, and tests assert the equivalence.
        await create_all(engine)
        logger.info(
            "sqlite_schema_ready",
            extra={"event": "sqlite_schema_ready", "backend": "sqlite"},
        )

    registry: PromptRegistry = load_prompt_registry(settings.resolved_prompts_dir)
    app.state.prompt_registry = registry
    for warning in registry.warnings:
        logger.warning(
            "prompt_registry_warning", extra={"event": "prompt_registry", "detail": warning}
        )

    # Built exactly once per process: the chain holds an in-memory cache and its
    # resilience state, and rebuilding it per request would throw both away.
    app.state.provider = build_provider(settings)
    app.state.token_revocations = TokenRevocationRegistry()

    selection = build_queue_selection(settings, session_factory)
    app.state.queue = selection.queue
    app.state.queue_backend = selection.backend
    app.state.queue_degradation_reason = selection.degradation_reason
    # The same registration the standalone worker performs, so a job kind cannot work in
    # the API process and be "no handler registered" in the worker (or the reverse).
    register_default_handlers(selection.queue, session_factory)

    async with session_scope(session_factory) as session:
        await PromptRepository(session).sync_registry(registry)
        await sync_skill_taxonomy(session)
        await ensure_demo_user(session, settings)

    logger.info(
        "app_started",
        extra={
            "event": "app_started",
            "backend": selection.backend,
            "provider": app.state.provider.name,
            "detail": f"prompts={len(registry)} environment={settings.environment}",
        },
    )
    try:
        yield
    finally:
        await selection.queue.shutdown()
        await engine.dispose()
        logger.info("app_stopped", extra={"event": "app_stopped"})


def create_app(settings: APISettings | None = None) -> FastAPI:
    """Build the FastAPI application.

    ``settings`` is injectable so tests can run against a temporary SQLite file with
    tighter rate limits without mutating the process environment.
    """
    resolved = settings or get_api_settings()

    # Non-fatal advisories are logged; anything unsafe raises before a socket opens.
    warnings = assert_runtime_configuration(resolved)
    configure_logging(resolved, force=True)
    for warning in warnings:
        logger.warning("configuration_warning", extra={"event": "configuration", "detail": warning})

    application = FastAPI(
        title=resolved.app_name,
        version=__version__,
        description=(
            "CareerForge AI API. Every response is enveloped as "
            "`{success, data, error, requestId}` (docs/API.md §1.1)."
        ),
        openapi_url=resolved.openapi_url,
        docs_url=resolved.api_docs_url,
        redoc_url=None,
        # Never FastAPI's debug responses: they leak tracebacks into the contract.
        debug=False,
        lifespan=lifespan,
    )
    application.state.settings = resolved
    application.state.rate_limiter = TokenBucketLimiter()
    # Interview sessions span several requests, so the store is app-wide. It is
    # in-process, which ``GET /ai/capabilities`` reports as a limitation.
    application.state.interview_sessions = InterviewSessionStore()

    # ── middleware, innermost first ──────────────────────────────────────────
    # Starlette wraps `add_middleware` calls in reverse: the last one added ends up
    # outermost. This order therefore produces, on the way in:
    #   RequestID → logging → TrustedHost → CORS → rate limit → error handling →
    #   envelope → (FastAPI exception handlers) → router
    application.add_middleware(EnvelopeMiddleware)
    application.add_middleware(ErrorHandlingMiddleware, logger=logger, debug=resolved.debug)
    application.add_middleware(
        RateLimitMiddleware, settings=resolved, limiter=application.state.rate_limiter
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-Id",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
    )
    if resolved.host_check_enabled:
        # Only when a real allow-list is configured; "*" (the default) skips it.
        application.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved.trusted_host_list)
    application.add_middleware(RequestLoggingMiddleware, logger=logger)
    application.add_middleware(RequestIDMiddleware)

    register_exception_handlers(application)

    # ── routes ───────────────────────────────────────────────────────────────
    application.include_router(auth.router, prefix=resolved.api_prefix)
    application.include_router(system.router, prefix=resolved.api_prefix)
    application.include_router(tasks.router, prefix=resolved.api_prefix)
    application.include_router(documents.router, prefix=resolved.api_prefix)
    application.include_router(evidence.router, prefix=resolved.api_prefix)
    application.include_router(jobs.router, prefix=resolved.api_prefix)
    application.include_router(ai.router, prefix=resolved.api_prefix)

    @application.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        """A tiny landing document — the API lives under ``settings.api_prefix``."""
        return JSONResponse(
            {
                "name": resolved.app_name,
                "version": __version__,
                "api": resolved.api_prefix,
                "docs": resolved.api_docs_url,
                "health": f"{resolved.api_prefix}/system/health",
            }
        )

    logger.info(
        "app_created",
        extra={
            "event": "app_created",
            "backend": resolved.environment,
            "detail": f"prefix={resolved.api_prefix}",
        },
    )
    return application


#: ASGI entrypoint used by ``uvicorn careerforge_api.main:app``.
app = create_app()
