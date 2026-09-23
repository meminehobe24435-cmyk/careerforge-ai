"""Runtime configuration for the CareerForge AI core.

All settings are environment driven (12-factor). The same settings object is
consumed by the API, the worker and the evaluation runner, so a benchmark run
uses exactly the configuration the product uses.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from careerforge_ai.errors import ConfigurationError

__all__ = ["PROVIDER_NAMES", "Settings", "get_settings", "reset_settings_cache"]

PROVIDER_NAMES = ("deepseek", "openai", "ollama", "heuristic")
ProviderName = Literal["deepseek", "openai", "ollama", "heuristic"]
QueueBackend = Literal["redis", "inprocess"]
VectorBackend = Literal["pgvector", "sqlite"]
StorageBackend = Literal["local", "s3"]


def _repo_root() -> Path:
    """Locate the repository root so defaults work from any working directory."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pnpm-workspace.yaml").exists() or (parent / ".git").exists():
            return parent
    return here.parents[3]


class Settings(BaseSettings):
    """CareerForge AI settings.

    Values are read from the environment, optionally seeded by a ``.env`` file at
    the repository root.
    """

    model_config = SettingsConfigDict(
        env_file=(_repo_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "CareerForge AI"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    git_sha: str = ""

    # ── Paths ────────────────────────────────────────────────────────────────
    repo_root: Path = Field(default_factory=_repo_root)
    prompts_dir: Path | None = None
    data_dir: Path | None = None
    reports_dir: Path | None = None

    # ── Storage / vector / queue ─────────────────────────────────────────────
    use_sqlite: bool = False
    database_url: str = "postgresql+asyncpg://careerforge:careerforge@localhost:5432/careerforge"
    sqlite_path: str = "./data/careerforge.db"

    storage_backend: StorageBackend = "local"
    storage_local_path: str = "./data/uploads"
    max_upload_mb: int = 10

    vector_backend: VectorBackend | None = None
    embedding_dim: int = 1536
    vector_top_k: int = 8
    rrf_k: int = 60

    queue_backend: QueueBackend | None = None
    redis_url: str = "redis://localhost:6379/0"
    worker_concurrency: int = 2

    # ── LLM providers ────────────────────────────────────────────────────────
    llm_provider: ProviderName = "heuristic"
    llm_fallback_provider: ProviderName = "heuristic"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # ── Embeddings ───────────────────────────────────────────────────────────
    embedding_provider: ProviderName = "heuristic"
    embedding_model: str = "text-embedding-3-small"

    # ── Routing (cost control) ───────────────────────────────────────────────
    route_extraction_model: str = ""
    route_generation_model: str = ""
    route_interview_model: str = ""

    # ── Cost guardrails ──────────────────────────────────────────────────────
    ai_daily_budget_usd: float = 1.0
    ai_max_tokens_per_call: int = 4096
    ai_request_timeout_seconds: float = 60.0
    ai_max_retries: int = 2
    cache_ttl_llm_seconds: int = 86_400
    cache_ttl_embedding_seconds: int = 604_800

    # ── GitHub ───────────────────────────────────────────────────────────────
    github_token: str = ""
    github_cache_ttl_seconds: int = 21_600

    # ── Scoring weights (must sum to 1.0) ────────────────────────────────────
    match_weight_skill: float = 0.40
    match_weight_experience: float = 0.25
    match_weight_project: float = 0.20
    match_weight_education: float = 0.05
    match_weight_evidence: float = 0.10

    # ── Evidence confidence weights (must sum to 1.0) ────────────────────────
    confidence_weight_authority: float = 0.30
    confidence_weight_recency: float = 0.15
    confidence_weight_specificity: float = 0.20
    confidence_weight_corroboration: float = 0.20
    confidence_weight_extraction: float = 0.15

    # ── Claim gate thresholds ────────────────────────────────────────────────
    claim_supported_threshold: float = 0.75
    claim_partial_threshold: float = 0.45
    claim_min_sources: int = 2

    # ── Security ─────────────────────────────────────────────────────────────
    jwt_secret: str = "dev-only-insecure-secret-change-me-32bytes-min"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:3000"

    rate_limit_read_per_min: int = 300
    rate_limit_write_per_min: int = 60
    rate_limit_ai_per_min: int = 20
    rate_limit_auth_per_min: int = 10

    # ── Demo seed ────────────────────────────────────────────────────────────
    demo_user_email: str = "demo@careerforge.ai"
    demo_user_name: str = "Alex Chen"
    demo_user_slug: str = "alex"

    # ── Validators & derived values ──────────────────────────────────────────

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if level not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return level

    @model_validator(mode="after")
    def _apply_derived_defaults(self) -> Settings:
        # Local mode implies the dependency-free ports unless explicitly set.
        if self.vector_backend is None:
            self.vector_backend = "sqlite" if self.use_sqlite else "pgvector"
        if self.queue_backend is None:
            self.queue_backend = "inprocess" if self.use_sqlite else "redis"

        if self.prompts_dir is None:
            self.prompts_dir = self.repo_root / "prompts"
        if self.data_dir is None:
            self.data_dir = self.repo_root / "data"
        if self.reports_dir is None:
            self.reports_dir = self.repo_root / "reports"

        self._validate_weights(
            "MATCH_WEIGHT",
            (
                self.match_weight_skill,
                self.match_weight_experience,
                self.match_weight_project,
                self.match_weight_education,
                self.match_weight_evidence,
            ),
        )
        self._validate_weights(
            "CONFIDENCE_WEIGHT",
            (
                self.confidence_weight_authority,
                self.confidence_weight_recency,
                self.confidence_weight_specificity,
                self.confidence_weight_corroboration,
                self.confidence_weight_extraction,
            ),
        )
        if self.claim_supported_threshold <= self.claim_partial_threshold:
            raise ConfigurationError(
                "CLAIM_SUPPORTED_THRESHOLD must be greater than CLAIM_PARTIAL_THRESHOLD",
                details={
                    "supported": self.claim_supported_threshold,
                    "partial": self.claim_partial_threshold,
                },
            )
        return self

    @staticmethod
    def _validate_weights(label: str, weights: tuple[float, ...]) -> None:
        total = sum(weights)
        if abs(total - 1.0) > 1e-6:
            raise ConfigurationError(
                f"{label}_* values must sum to 1.0",
                details={"sum": round(total, 6), "values": list(weights)},
            )
        if any(w < 0 for w in weights):
            raise ConfigurationError(f"{label}_* values must be non-negative")

    # ── Convenience ──────────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def resolved_database_url(self) -> str:
        """Database URL honouring the SQLite fallback path (ADR-004)."""
        if self.use_sqlite:
            path = Path(self.sqlite_path)
            if not path.is_absolute():
                path = self.repo_root / path
            return f"sqlite+aiosqlite:///{path.as_posix()}"
        return self.database_url

    @property
    def resolved_data_dir(self) -> Path:
        assert self.data_dir is not None  # guaranteed by the model validator
        return self.data_dir

    @property
    def resolved_prompts_dir(self) -> Path:
        assert self.prompts_dir is not None
        return self.prompts_dir

    def provider_is_configured(self, name: ProviderName) -> bool:
        """Whether a provider has everything it needs to be usable."""
        if name == "heuristic":
            return True
        if name == "deepseek":
            return bool(self.deepseek_api_key)
        if name == "openai":
            return bool(self.openai_api_key)
        if name == "ollama":
            return bool(self.ollama_base_url)
        return False

    def active_provider_chain(self) -> list[ProviderName]:
        """The provider chain that will actually be attempted, in order."""
        chain: list[ProviderName] = []
        for candidate in (self.llm_provider, self.llm_fallback_provider, "heuristic"):
            if candidate not in chain and self.provider_is_configured(candidate):
                chain.append(candidate)
        if "heuristic" not in chain:
            chain.append("heuristic")
        return chain


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


def reset_settings_cache() -> None:
    """Clear the settings cache (used by tests that mutate the environment)."""
    get_settings.cache_clear()
