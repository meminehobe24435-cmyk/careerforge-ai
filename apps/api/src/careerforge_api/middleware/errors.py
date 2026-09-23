"""Exception handling: every failure leaves the API as a documented envelope.

``docs/API.md`` §1.6 is a closed table, and a bare FastAPI/Starlette error body
would fall outside it. Two mechanisms are installed here and they are not
redundant:

* :func:`register_exception_handlers` wires FastAPI's own hook points
  (``RequestValidationError``, ``HTTPException``, :class:`ApiError`). These cover
  anything raised inside a route, including Starlette's own "no route matched"
  404 and its 405 for a known path with the wrong method.
* :class:`ErrorHandlingMiddleware` sits *outside* them, so it also catches failures
  raised by inner middleware (the envelope writer, the rate limiter) and anything
  the handlers themselves could not digest. Unexpected exceptions are logged with a
  traceback and returned as ``INTERNAL_ERROR`` carrying the request id — never the
  exception text, which is what would leak internals.

Both paths produce the same body and mark it with ``X-Envelope-Complete`` so the
envelope middleware does not wrap it twice.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from careerforge_api.core.errors import ApiError, InternalError, ValidationError, error_from_status
from careerforge_api.core.ids import new_request_id
from careerforge_api.core.logging import get_logger, redact
from careerforge_api.middleware.envelope import ENVELOPE_COMPLETE_HEADER, error_envelope
from careerforge_api.middleware.request_id import REQUEST_ID_HEADER, request_id_of

__all__ = [
    "ErrorHandlingMiddleware",
    "api_error_handler",
    "http_exception_handler",
    "json_error_response",
    "register_exception_handlers",
    "validation_details",
    "validation_exception_handler",
]

_LOCATION_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})


def _request_id(request: Any) -> str:
    state = getattr(request, "state", None)
    value = getattr(state, "request_id", None) if state is not None else None
    return str(value) if value else new_request_id()


def _field(loc: Any) -> str:
    parts = [str(part) for part in (loc or [])]
    if parts and parts[0] in _LOCATION_PREFIXES:
        parts = parts[1:]
    return ".".join(parts) or "request"


def validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Flatten pydantic errors into the frozen ``ApiErrorDetail`` shape.

    ``{ field, issue }`` is what ``packages/shared`` declares; ``message`` is added
    because a field name plus an error *type* is not something a human can act on.
    """
    return [
        {
            "field": _field(error.get("loc")),
            "issue": str(error.get("type") or "invalid"),
            "message": str(error.get("msg") or "invalid value"),
        }
        for error in exc.errors()
    ]


def json_error_response(error: ApiError, request_id: str) -> JSONResponse:
    """Enveloped error response, marked complete for the envelope middleware."""
    headers = {
        **error.headers,
        ENVELOPE_COMPLETE_HEADER: "1",
        REQUEST_ID_HEADER: request_id,
    }
    return JSONResponse(
        status_code=error.status_code,
        content=error_envelope(error, request_id=request_id),
        headers=headers,
    )


# ── FastAPI hook points ──────────────────────────────────────────────────────


async def api_error_handler(request: Any, exc: ApiError) -> JSONResponse:
    """``ApiError`` (and subclasses) raised anywhere inside a route."""
    return json_error_response(exc, _request_id(request))


async def validation_exception_handler(request: Any, exc: RequestValidationError) -> JSONResponse:
    """Request validation → ``VALIDATION_ERROR`` at **400**, as §1.6 documents."""
    error = ValidationError(details=validation_details(exc))
    return json_error_response(error, _request_id(request))


async def http_exception_handler(request: Any, exc: StarletteHTTPException) -> JSONResponse:
    """Framework errors (404 for an unknown route, 405, …) → the documented table."""
    message = exc.detail if isinstance(exc.detail, str) else None
    error = error_from_status(exc.status_code, message)
    if exc.headers:
        error.headers.update({key: value for key, value in exc.headers.items()})
    return json_error_response(error, _request_id(request))


def register_exception_handlers(app: FastAPI) -> None:
    """Install the handlers on a FastAPI app (called by :func:`create_app`)."""
    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]


# ── safety net for exceptions escaping the inner middleware ──────────────────


class ErrorHandlingMiddleware:
    """Turns any escaping exception into the envelope; never re-raises."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        logger: logging.Logger | None = None,
        debug: bool = False,
    ) -> None:
        self.app = app
        self.logger = logger or get_logger()
        self.debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = request_id_of(scope) or new_request_id()
        # Per-request state: the middleware instance is shared across connections.
        response_started = False

        async def track(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track)
        except ApiError as exc:
            await self._respond(scope, receive, send, exc, request_id, response_started)
        except Exception as exc:  # noqa: BLE001 - catching everything is the job here
            self.logger.error(
                "unhandled_exception",
                exc_info=exc,
                extra={
                    "event": "unhandled_exception",
                    "request_id": request_id,
                    "error_code": "INTERNAL_ERROR",
                    "detail": redact(f"{type(exc).__name__}: {exc}"),
                },
            )
            await self._respond(
                scope, receive, send, self._internal_error(exc), request_id, response_started
            )

    def _internal_error(self, exc: Exception) -> InternalError:
        details: list[dict[str, Any]] = []
        if self.debug:
            details.append({"field": "exception", "issue": type(exc).__name__})
        return InternalError(details=details)

    async def _respond(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        error: ApiError,
        request_id: str,
        response_started: bool,
    ) -> None:
        if response_started:
            # The status line is already on the wire; a second response would be
            # protocol corruption. The access log already recorded the failure.
            self.logger.error(
                "response_already_started",
                extra={
                    "event": "response_already_started",
                    "request_id": request_id,
                    "error_code": error.code,
                    "detail": redact(error.message),
                },
            )
            return
        await json_error_response(error, request_id)(scope, receive, send)
