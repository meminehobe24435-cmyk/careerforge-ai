"""Exception hierarchy for the CareerForge AI core.

Errors carry a stable machine-readable ``code`` so the API layer can map them to
HTTP responses without string matching, and so the observability layer can
bucket failures.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "BudgetExceededError",
    "CacheError",
    "CareerForgeError",
    "ConfigurationError",
    "DocumentParseError",
    "DocumentTooLargeError",
    "EvidenceGateError",
    "PortError",
    "ProviderError",
    "ProviderRateLimitedError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "RetrievalError",
    "SchemaValidationError",
    "StepFailedError",
    "StepTimeoutError",
    "UnsupportedDocumentError",
    "WorkflowError",
    "is_retryable",
]

#: Error codes that are worth retrying (transient upstream conditions).
_RETRYABLE_CODES = frozenset(
    {
        "PROVIDER_TIMEOUT",
        "PROVIDER_RATE_LIMITED",
        "PROVIDER_UNAVAILABLE",
        "PROVIDER_ERROR",
        "CACHE_ERROR",
    }
)


class CareerForgeError(Exception):
    """Base class for every error raised by the AI core."""

    code: str = "CAREERFORGE_ERROR"
    #: Whether the caller may sensibly retry the exact same operation.
    retryable: bool = False

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialise for logging, traces and API error payloads."""
        return {"code": self.code, "message": self.message, "details": self.details}

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.details:
            return f"[{self.code}] {self.message} {self.details}"
        return f"[{self.code}] {self.message}"


class ConfigurationError(CareerForgeError):
    """Raised when required configuration is missing or contradictory."""

    code = "CONFIGURATION_ERROR"


# ── Providers ────────────────────────────────────────────────────────────────


class ProviderError(CareerForgeError):
    """Base class for LLM / embedding provider failures."""

    code = "PROVIDER_ERROR"
    retryable = True


class ProviderTimeoutError(ProviderError):
    code = "PROVIDER_TIMEOUT"


class ProviderRateLimitedError(ProviderError):
    code = "PROVIDER_RATE_LIMITED"

    def __init__(
        self,
        message: str,
        *,
        retry_after_seconds: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(ProviderError):
    """No provider in the chain could serve the request."""

    code = "PROVIDER_UNAVAILABLE"


# ── Contracts & validation ────────────────────────────────────────────────────


class SchemaValidationError(CareerForgeError):
    """LLM output did not satisfy the declared schema.

    Never retried blindly: the orchestrator performs a single *repair* attempt
    that feeds the validation error back to the model (see ADR-007).
    """

    code = "SCHEMA_VALIDATION_ERROR"


class BudgetExceededError(CareerForgeError):
    """The user's AI budget guardrail was hit; degrade instead of failing."""

    code = "BUDGET_EXCEEDED"


class CacheError(CareerForgeError):
    code = "CACHE_ERROR"
    retryable = True


# ── Ports ─────────────────────────────────────────────────────────────────────


class PortError(CareerForgeError):
    """A storage/search port failed (vector store, repository, external API)."""

    code = "PORT_ERROR"


class RetrievalError(PortError):
    code = "RETRIEVAL_ERROR"


class EvidenceGateError(CareerForgeError):
    """A claim was blocked by the hallucination gate (expected, not a bug)."""

    code = "EVIDENCE_GATE_REJECTED"


# ── Ingestion ─────────────────────────────────────────────────────────────────


class DocumentParseError(CareerForgeError):
    """A document could not be read into text.

    Raised for a corrupt file, an unsupported internal structure, or a missing
    optional parser dependency — the message says which, because "could not parse
    your resume" with no reason is the least useful error a product can show.
    """

    code = "DOCUMENT_PARSE_FAILED"


class UnsupportedDocumentError(DocumentParseError):
    """The file type is not one this build can read."""

    code = "UNSUPPORTED_DOCUMENT_TYPE"


class DocumentTooLargeError(DocumentParseError):
    """The upload exceeded the ingestion limit; refused rather than truncated.

    Silently reading the first N bytes of a résumé would produce a *plausible*
    profile from partial material, which is worse than refusing it.
    """

    code = "DOCUMENT_TOO_LARGE"


# ── Workflow ──────────────────────────────────────────────────────────────────


class WorkflowError(CareerForgeError):
    code = "WORKFLOW_ERROR"


class StepFailedError(WorkflowError):
    code = "STEP_FAILED"

    def __init__(self, step: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, details={"step": step, **(details or {})})
        self.step = step


class StepTimeoutError(WorkflowError):
    code = "STEP_TIMEOUT"
    retryable = True

    def __init__(self, step: str, timeout_s: float) -> None:
        super().__init__(
            f"step '{step}' exceeded its {timeout_s:g}s timeout",
            details={"step": step, "timeout_s": timeout_s},
        )
        self.step = step


def is_retryable(error: BaseException) -> bool:
    """Return True when the error is transient and worth a retry."""
    if isinstance(error, CareerForgeError):
        return error.retryable or error.code in _RETRYABLE_CODES
    # Network-level failures from httpx are transient by nature.
    return error.__class__.__module__.startswith("httpx")
