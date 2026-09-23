"""Structured JSON logging with request correlation and PII redaction.

``docs/ARCHITECTURE.md`` §8.2 puts structured logging second in the middleware
chain so every line can be joined on ``request_id`` with the frontend, the agent
runs and the LLM calls (``agent_runs.request_id`` / ``llm_calls.request_id``).

Two rules are enforced here rather than left to discipline at the call site
(``docs/ARCHITECTURE.md`` §10, ``docs/DATABASE.md`` §7):

1. **An allow-list of extra fields.** A logger can only contribute the fields
   declared in :data:`LOG_EXTRA_FIELDS`; anything else is dropped instead of being
   serialised. That is what makes "we never log request bodies" a structural
   property instead of a promise.
2. **Redaction of anything string-shaped.** Even allow-listed values pass through
   :func:`redact`, so an email or a bearer token that ends up in a message or in a
   path is masked before it reaches stdout.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any, Final

from careerforge_api.core.config import APISettings

__all__ = [
    "LOG_EXTRA_FIELDS",
    "REDACTION_PLACEHOLDER",
    "configure_logging",
    "get_logger",
    "log_request",
    "redact",
    "safe_path",
]

#: Fields a log record may carry beyond level/logger/message.
LOG_EXTRA_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "request_id",
        "method",
        "path",
        "status",
        "duration_ms",
        "event",
        "error_code",
        "task_id",
        "user_id",
        "agent",
        "workflow",
        "provider",
        "backend",
        "kind",
        "stage",
        "attempts",
        "detail",
    }
)

REDACTION_PLACEHOLDER: Final = "[redacted]"

#: `user@host.tld`
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
#: Three base64url segments — i.e. a JWT, refresh token or bearer value.
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]{4,}\b")
#: `Bearer <opaque>` / `token=<opaque>` style values.
_BEARER_RE = re.compile(r"(?i)\b(bearer|token|api[_-]?key|secret|password)\b[=:\s]+\S+")
#: Long hex/base64 blobs that are far more likely to be a secret than content.
_OPAQUE_SECRET_RE = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")


def redact(value: str) -> str:
    """Mask emails, bearer tokens and long opaque secrets in a loggable string."""
    masked = _JWT_RE.sub(REDACTION_PLACEHOLDER, value)
    masked = _BEARER_RE.sub(lambda match: f"{match.group(1)}={REDACTION_PLACEHOLDER}", masked)
    masked = _EMAIL_RE.sub(REDACTION_PLACEHOLDER, masked)
    return _OPAQUE_SECRET_RE.sub(REDACTION_PLACEHOLDER, masked)


def safe_path(raw_path: str) -> str:
    """Log the request path only.

    Query strings can carry credentials (``?token=…``) and are never logged; the
    route itself is enough to correlate a request with a handler.
    """
    return raw_path.split("?", 1)[0]


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the documented request fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        for field in LOG_EXTRA_FIELDS:
            if not hasattr(record, field):
                continue
            value = getattr(record, field)
            payload[field] = redact(value) if isinstance(value, str) else value
        if record.exc_info:
            # The traceback is code, not user data; it is the one thing an
            # unexpected 500 must leave behind.
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(settings: APISettings, *, force: bool = False) -> logging.Logger:
    """Install the JSON handler on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    handler_name = "careerforge-json"
    existing = [h for h in root.handlers if getattr(h, "_careerforge_handler", None) == handler_name]
    if existing and not force:
        return logging.getLogger("careerforge_api")
    for handler in existing:
        root.removeHandler(handler)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._careerforge_handler = handler_name  # type: ignore[attr-defined]
    root.addHandler(handler)
    if settings.debug:
        # uvicorn's own access log would be unstructured noise next to ours.
        logging.getLogger("uvicorn.access").disabled = True
    return logging.getLogger("careerforge_api")


def get_logger(name: str = "careerforge_api") -> logging.Logger:
    return logging.getLogger(name)


def log_request(
    logger: logging.Logger,
    *,
    request_id: str,
    method: str,
    path: str,
    status: int,
    duration_ms: float,
    detail: str | None = None,
) -> None:
    """Emit the per-request line: request_id, method, path, status, duration_ms."""
    level = logging.INFO if status < 500 else logging.ERROR
    logger.log(
        level,
        "request",
        extra={
            "event": "http_request",
            "request_id": request_id,
            "method": method,
            "path": safe_path(path),
            "status": status,
            "duration_ms": duration_ms,
            "detail": detail,
        },
    )
