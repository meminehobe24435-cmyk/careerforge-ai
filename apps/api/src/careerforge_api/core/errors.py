"""The HTTP error model — ``docs/API.md`` §1.6 implemented as named classes.

One class per documented code so call sites read as domain statements
(``raise NotFoundError("job")``) and the code↔status pairing lives in exactly one
place. The middleware layer only knows how to turn an :class:`ApiError` into the
documented envelope; it never inspects messages.

Two properties matter for the contract:

* ``code`` is stable and machine-readable — the frontend switches on it
  (``packages/shared`` keeps the same union).
* ``details`` is always a JSON array, because ``ApiErrorDetail`` in the frozen
  client type is ``{ field, issue }[]``.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ERROR_CODE_STATUS",
    "ApiError",
    "AiBudgetExceededError",
    "AiProviderError",
    "AiProviderUnavailableError",
    "ClaimRejectedError",
    "ConflictError",
    "DependencyUnavailableError",
    "FileTooLargeError",
    "ForbiddenError",
    "GitHubError",
    "InternalError",
    "MethodNotAllowedError",
    "NotFoundError",
    "PayloadTooLargeError",
    "RateLimitedError",
    "TokenExpiredError",
    "UnauthorizedError",
    "UnsupportedFileTypeError",
    "ValidationError",
    "error_from_status",
]

#: ``error.code`` → ``error.message`` used when a class does not override it.
_DEFAULT_MESSAGES: dict[str, str] = {
    "VALIDATION_ERROR": "Request validation failed",
    "UNSUPPORTED_FILE_TYPE": "Unsupported file type",
    "FILE_TOO_LARGE": "Uploaded file exceeds the size limit",
    "UNAUTHORIZED": "Authentication required",
    "TOKEN_EXPIRED": "Access token expired",
    "FORBIDDEN": "Insufficient permissions",
    "NOT_FOUND": "Resource not found",
    "CONFLICT": "Resource conflict",
    "PAYLOAD_TOO_LARGE": "Request payload too large",
    "CLAIM_REJECTED": "Claim rejected by the evidence gate",
    "RATE_LIMITED": "Too many requests",
    "AI_BUDGET_EXCEEDED": "Daily AI budget exceeded",
    "AI_PROVIDER_ERROR": "Upstream AI provider failed",
    "GITHUB_ERROR": "GitHub API request failed",
    "DEPENDENCY_UNAVAILABLE": "A required dependency is unavailable",
    "AI_PROVIDER_UNAVAILABLE": "No AI provider in the chain could serve the request",
    "INTERNAL_ERROR": "Unexpected server error",
}


class ApiError(Exception):
    """Base class for every error the API reports to a client."""

    #: HTTP status paired with :attr:`code`.
    status_code: int = 500
    #: Machine-readable, frozen by ``docs/API.md`` §1.6.
    code: str = "INTERNAL_ERROR"
    #: Overridden per class; ``None`` falls back to ``_DEFAULT_MESSAGES[code]``.
    default_message: str | None = None

    def __init__(
        self,
        message: str | None = None,
        *,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.message = (
            message
            or self.default_message
            or _DEFAULT_MESSAGES.get(self.code, "Unexpected server error")
        )
        self.details: list[dict[str, Any]] = list(details or [])
        #: Extra response headers (``Retry-After``, ``WWW-Authenticate``, …).
        self.headers: dict[str, str] = dict(headers or {})
        super().__init__(self.message)

    # ── serialisation ────────────────────────────────────────────────────────

    def to_payload(self) -> dict[str, Any]:
        """The documented ``error`` object of the response envelope."""
        return {"code": self.code, "message": self.message, "details": self.details}

    def with_details(self, details: list[dict[str, Any]]) -> ApiError:
        self.details = list(details)
        return self

    def __str__(self) -> str:
        if self.details:
            return f"[{self.code}] {self.message} {self.details}"
        return f"[{self.code}] {self.message}"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# ── 400 ──────────────────────────────────────────────────────────────────────


class ValidationError(ApiError):
    """`VALIDATION_ERROR` — request body/parameter validation failed.

    Note the deliberate difference from FastAPI's default: ``docs/API.md`` §1.6
    freezes this code at **400**, not the framework's 422.
    """

    status_code = 400
    code = "VALIDATION_ERROR"
    default_message = "Request validation failed"


class UnsupportedFileTypeError(ApiError):
    """`UNSUPPORTED_FILE_TYPE` — MIME/magic-number check failed."""

    status_code = 400
    code = "UNSUPPORTED_FILE_TYPE"


class FileTooLargeError(ApiError):
    """`FILE_TOO_LARGE` — upload exceeds ``MAX_UPLOAD_MB`` (10MB by default)."""

    status_code = 400
    code = "FILE_TOO_LARGE"


# ── 401 / 403 / 404 / 409 ────────────────────────────────────────────────────


class UnauthorizedError(ApiError):
    """`UNAUTHORIZED` — missing, malformed or revoked credentials."""

    status_code = 401
    code = "UNAUTHORIZED"
    default_message = "Authentication required"


class TokenExpiredError(ApiError):
    """`TOKEN_EXPIRED` — the client should refresh and retry."""

    status_code = 401
    code = "TOKEN_EXPIRED"
    default_message = "Access token expired"


class ForbiddenError(ApiError):
    """`FORBIDDEN` — authenticated, but not allowed.

    Cross-tenant reads are **not** forbidden: ``docs/API.md`` §1.2 requires
    ``404 NOT_FOUND`` so resource existence never leaks. Use
    :class:`NotFoundError` for those.
    """

    status_code = 403
    code = "FORBIDDEN"


class NotFoundError(ApiError):
    """`NOT_FOUND` — absent, or present but owned by another user."""

    status_code = 404
    code = "NOT_FOUND"


class ConflictError(ApiError):
    """`CONFLICT` — unique-constraint collision (duplicate email, re-imported JD)."""

    status_code = 409
    code = "CONFLICT"


class MethodNotAllowedError(ApiError):
    """`METHOD_NOT_ALLOWED` — not in §1.6, kept because a bare 405 would escape the envelope."""

    status_code = 405
    code = "METHOD_NOT_ALLOWED"
    default_message = "Method not allowed for this resource"


# ── 413 / 422 / 429 ──────────────────────────────────────────────────────────


class PayloadTooLargeError(ApiError):
    """`PAYLOAD_TOO_LARGE` — request body over the server limit."""

    status_code = 413
    code = "PAYLOAD_TOO_LARGE"


class ClaimRejectedError(ApiError):
    """`CLAIM_REJECTED` — business refusal: the evidence gate blocked a claim."""

    status_code = 422
    code = "CLAIM_REJECTED"


class RateLimitedError(ApiError):
    """`RATE_LIMITED` — token bucket exhausted; always carries ``Retry-After``."""

    status_code = 429
    code = "RATE_LIMITED"
    default_message = "Rate limit exceeded"

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after_seconds: int = 1,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        merged = {"Retry-After": str(self.retry_after_seconds), **(headers or {})}
        super().__init__(message, details=details, headers=merged)


class AiBudgetExceededError(ApiError):
    """`AI_BUDGET_EXCEEDED` — the per-user daily AI budget guardrail fired."""

    status_code = 429
    code = "AI_BUDGET_EXCEEDED"


# ── 502 / 503 / 500 ──────────────────────────────────────────────────────────


class AiProviderError(ApiError):
    """`AI_PROVIDER_ERROR` — upstream LLM failed; safe to retry."""

    status_code = 502
    code = "AI_PROVIDER_ERROR"


class GitHubError(ApiError):
    """`GITHUB_ERROR` — GitHub API failure (rate limit, 5xx, auth)."""

    status_code = 502
    code = "GITHUB_ERROR"


class DependencyUnavailableError(ApiError):
    """`DEPENDENCY_UNAVAILABLE` — database, Redis or vector store is unreachable."""

    status_code = 503
    code = "DEPENDENCY_UNAVAILABLE"


class AiProviderUnavailableError(ApiError):
    """`AI_PROVIDER_UNAVAILABLE` — every provider, including the heuristic tail, failed."""

    status_code = 503
    code = "AI_PROVIDER_UNAVAILABLE"


class InternalError(ApiError):
    """`INTERNAL_ERROR` — unexpected; logged with a traceback and the request id."""

    status_code = 500
    code = "INTERNAL_ERROR"


# ── registry helpers ─────────────────────────────────────────────────────────

#: Every documented code → the HTTP status the API pairs it with.
ERROR_CODE_STATUS: dict[str, int] = {
    "VALIDATION_ERROR": 400,
    "UNSUPPORTED_FILE_TYPE": 400,
    "FILE_TOO_LARGE": 400,
    "UNAUTHORIZED": 401,
    "TOKEN_EXPIRED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "CONFLICT": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "CLAIM_REJECTED": 422,
    "RATE_LIMITED": 429,
    "AI_BUDGET_EXCEEDED": 429,
    "AI_PROVIDER_ERROR": 502,
    "GITHUB_ERROR": 502,
    "DEPENDENCY_UNAVAILABLE": 503,
    "AI_PROVIDER_UNAVAILABLE": 503,
    "INTERNAL_ERROR": 500,
}

#: ``code`` → class, for mapping a code received from another layer (or a test).
_CLASS_BY_CODE: dict[str, type[ApiError]] = {
    "VALIDATION_ERROR": ValidationError,
    "UNSUPPORTED_FILE_TYPE": UnsupportedFileTypeError,
    "FILE_TOO_LARGE": FileTooLargeError,
    "UNAUTHORIZED": UnauthorizedError,
    "TOKEN_EXPIRED": TokenExpiredError,
    "FORBIDDEN": ForbiddenError,
    "NOT_FOUND": NotFoundError,
    "METHOD_NOT_ALLOWED": MethodNotAllowedError,
    "CONFLICT": ConflictError,
    "PAYLOAD_TOO_LARGE": PayloadTooLargeError,
    "CLAIM_REJECTED": ClaimRejectedError,
    "RATE_LIMITED": RateLimitedError,
    "AI_BUDGET_EXCEEDED": AiBudgetExceededError,
    "AI_PROVIDER_ERROR": AiProviderError,
    "GITHUB_ERROR": GitHubError,
    "DEPENDENCY_UNAVAILABLE": DependencyUnavailableError,
    "AI_PROVIDER_UNAVAILABLE": AiProviderUnavailableError,
    "INTERNAL_ERROR": InternalError,
}

#: HTTP status → the code the framework's own failures map onto. Where §1.6 lists
#: several codes for one status (400, 401, 429, 502, 503) the most generic member
#: of the group wins, because a framework-raised error carries no domain meaning.
_STATUS_TO_CODE: dict[int, str] = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "CLAIM_REJECTED",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "AI_PROVIDER_ERROR",
    503: "DEPENDENCY_UNAVAILABLE",
}


def error_class(code: str) -> type[ApiError]:
    """Look up the class for a documented code (``InternalError`` for unknown ones)."""
    return _CLASS_BY_CODE.get(code, InternalError)


def error_from_status(status_code: int, message: str | None = None) -> ApiError:
    """Map a framework ``HTTPException`` onto the documented code table.

    Used by the exception handlers so a bare Starlette 404/405 — the normal
    "unknown route" path — still leaves the API inside the envelope.
    """
    documented = _STATUS_TO_CODE.get(status_code)
    if documented is not None:
        return error_class(documented)(message)
    if status_code >= 500:
        return InternalError(message)
    # Codes outside §1.6 get a self-describing fallback rather than a wrong label.
    return ApiError(
        message or f"Request failed with status {status_code}",
        code=f"HTTP_{status_code}",
        status_code=status_code,
    )
