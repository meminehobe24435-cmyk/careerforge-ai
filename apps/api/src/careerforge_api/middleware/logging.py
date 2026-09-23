"""Access logging: one structured JSON line per request.

Second middleware in the chain (``docs/ARCHITECTURE.md`` §8.2), outside the error
handlers so it also sees the status code of a failed request. Nothing from the
request body is logged; :mod:`careerforge_api.core.logging` additionally redacts
anything string-shaped.
"""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from careerforge_api.core.logging import get_logger, log_request, safe_path
from careerforge_api.middleware.request_id import request_id_of

__all__ = ["RequestLoggingMiddleware"]

#: Paths that would otherwise flood the log with infrastructure noise.
_QUIET_PATHS = frozenset({"/docs", "/redoc", "/favicon.ico", "/openapi.json"})


class RequestLoggingMiddleware:
    """Times each request and emits ``request_id``/``method``/``path``/``status``/``duration_ms``."""

    def __init__(self, app: ASGIApp, *, logger: logging.Logger | None = None) -> None:
        self.app = app
        self.logger = logger or get_logger()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET"))
        path = safe_path(str(scope.get("path", "")))
        started = time.perf_counter()
        status = 500

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            if path not in _QUIET_PATHS:
                log_request(
                    self.logger,
                    request_id=request_id_of(scope) or "-",
                    method=method,
                    path=path,
                    status=status,
                    duration_ms=duration_ms,
                )
