"""API-layer configuration.

A thin extension of :class:`careerforge_ai.config.Settings`, exactly as
``docs/ARCHITECTURE.md`` §1.3 intends: the HTTP layer adds the handful of knobs it
owns (API prefix, trusted hosts, SQL echo, build metadata) and inherits everything
else from the core — database URL resolution, vector/queue backend selection,
provider chain, prompt directory, rate-limit budgets, JWT/security settings and
the demo seed identity.

Re-implementing any of those here would create a second source of truth for
configuration, which is precisely the failure mode ADR-004 avoids.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from careerforge_ai.config import Settings
from careerforge_ai.errors import ConfigurationError
from careerforge_ai.parsing.documents import MAX_DOCUMENT_BYTES

__all__ = [
    "DEV_JWT_SECRET",
    "MIN_PRODUCTION_SECRET_LENGTH",
    "APISettings",
    "assert_runtime_configuration",
    "get_api_settings",
    "reset_api_settings_cache",
]

#: The placeholder shipped in ``.env.example``. Never valid outside development.
DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-32bytes-min"

#: HS256 keys shorter than this are brute-forcible; production must not use one.
MIN_PRODUCTION_SECRET_LENGTH = 32


class APISettings(Settings):
    """AI core settings plus the HTTP-only options.

    Read from the environment (and the repository ``.env``) by pydantic-settings,
    so every value is overridable per deployment without code changes.
    """

    # ── HTTP surface ─────────────────────────────────────────────────────────
    api_prefix: str = "/api/v1"
    #: Comma-separated host allow-list. ``"*"`` disables the host check (dev/test).
    trusted_hosts: str = "*"
    docs_enabled: bool = True

    # ── Diagnostics ──────────────────────────────────────────────────────────
    sql_echo: bool = False
    #: ISO-8601 build timestamp, injected at image build time (see Dockerfile.api).
    build_time: str = ""

    # ── Degradation policy ───────────────────────────────────────────────────
    #: Fall back to the in-process queue when the configured queue backend has no
    #: implementation in this process. The downgrade is reported by
    #: ``GET /system/health`` rather than hidden.
    allow_queue_fallback: bool = True
    rate_limit_enabled: bool = True

    # ── Uploads ──────────────────────────────────────────────────────────────
    # Names match ``.env.example`` §"File storage", which is the operator-facing
    # contract; inventing different ones here would make the documented configuration
    # silently ineffective.
    #: ``local`` is the only implemented backend; ``s3`` arrives with PHASE 15 and is
    #: refused loudly by ``assert_runtime_configuration`` rather than ignored.
    storage_backend: str = "local"
    #: Directory where an upload is spooled between the request that accepted it and the
    #: worker that parses it. Bytes cannot travel in the job payload (that column is
    #: JSON), and a spool file works for both queue backends — a per-process dict would
    #: lose the upload the moment the API and the worker are separate processes, which is
    #: exactly the deployment this has to work in.
    storage_local_path: str = "./data/uploads"
    #: Deployment-level upload limit in MiB. The AI core keeps its own hard ceiling
    #: (``MAX_DOCUMENT_BYTES``); the effective limit is the lower of the two.
    max_upload_mb: int = 10
    #: How long a spooled file may sit unclaimed before it is considered abandoned.
    upload_ttl_seconds: int = 3600

    @property
    def trusted_host_list(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def host_check_enabled(self) -> bool:
        hosts = self.trusted_host_list
        return bool(hosts) and hosts != ["*"]

    @property
    def api_docs_url(self) -> str | None:
        return "/docs" if self.docs_enabled else None

    @property
    def upload_path(self) -> Path:
        """Absolute spool directory, created on first use."""
        return Path(self.storage_local_path).expanduser().resolve()

    @property
    def max_upload_bytes(self) -> int:
        """``MAX_UPLOAD_MB`` in bytes, never above the AI core's own ceiling.

        Taking the minimum means raising the environment value cannot smuggle a file past
        the limit the ingestion layer enforces on its own.
        """
        return min(self.max_upload_mb * 1024 * 1024, MAX_DOCUMENT_BYTES)

    @property
    def storage_backend_supported(self) -> bool:
        """``s3`` is documented in ``.env.example`` but lands in PHASE 15."""
        return self.storage_backend == "local"

    @property
    def openapi_url(self) -> str | None:
        return f"{self.api_prefix}/openapi.json" if self.docs_enabled else None

    def redacted_provider_config(self) -> dict[str, object]:
        """Provider configuration for ``GET /system/info`` — keys never included."""
        return {
            "requested": self.llm_provider,
            "fallback": self.llm_fallback_provider,
            "chain": list(self.active_provider_chain()),
            "models": {
                "deepseek": self.deepseek_model,
                "openai": self.openai_model,
                "ollama": self.ollama_model,
            },
            "configured": {
                name: self.provider_is_configured(name)  # type: ignore[arg-type]
                for name in ("deepseek", "openai", "ollama", "heuristic")
            },
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "api_keys_present": {
                "deepseek": bool(self.deepseek_api_key),
                "openai": bool(self.openai_api_key),
                "github": bool(self.github_token),
            },
        }


@lru_cache(maxsize=1)
def get_api_settings() -> APISettings:
    """Process-wide API settings singleton."""
    return APISettings()


def reset_api_settings_cache() -> None:
    """Clear the settings cache (used by tests that mutate the environment)."""
    get_api_settings.cache_clear()


def assert_runtime_configuration(settings: APISettings) -> list[str]:
    """Fail fast on configuration that must not serve production traffic.

    A JWT secret left at the documented development default means any reader of
    ``.env.example`` can mint tokens for any account — including ``admin``. That
    is not something a warning in a log file can compensate for, so the process
    refuses to start (``docs/ARCHITECTURE.md`` §10, "密钥泄露").

    Returns advisory warnings (short secret, debug enabled) that are logged but
    do not stop the process: they are risks worth surfacing, not outages.
    """
    warnings: list[str] = []
    if not settings.is_production:
        return warnings

    if not settings.storage_backend_supported:
        # Accepting the value and quietly writing to local disk would look like it worked
        # right up to the point where an operator finds résumés on a container filesystem.
        raise ConfigurationError(
            f"STORAGE_BACKEND='{settings.storage_backend}' is not implemented in this build; "
            "it arrives with the deployment phase. Use STORAGE_BACKEND=local.",
            details={"field": "STORAGE_BACKEND", "value": settings.storage_backend},
        )
    if settings.jwt_secret == DEV_JWT_SECRET:
        raise ConfigurationError(
            "JWT_SECRET is still the development default and ENVIRONMENT=production; "
            "generate one with `openssl rand -hex 32` before starting the API",
            details={"field": "JWT_SECRET", "environment": settings.environment},
        )
    if len(settings.jwt_secret) < MIN_PRODUCTION_SECRET_LENGTH:
        warnings.append(
            f"JWT_SECRET is shorter than {MIN_PRODUCTION_SECRET_LENGTH} characters; "
            "HS256 keys this short are brute-forcible"
        )
    if settings.debug:
        warnings.append("DEBUG is enabled in production: stack traces and SQL echo stay available")
    return warnings
