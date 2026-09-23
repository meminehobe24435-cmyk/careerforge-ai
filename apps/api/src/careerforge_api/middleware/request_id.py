"""Request correlation: honour ``X-Request-Id`` or mint one, and echo it back.

First middleware in the chain (``docs/ARCHITECTURE.md`` §8.2) because every other
layer — the access log, the error handlers, the response envelope, and later
``agent_runs.request_id`` / ``llm_calls.request_id`` — reads the id from
``request.state``.

The inbound value is only echoed when it matches
:data:`careerforge_api.core.ids.REQUEST_ID_PATTERN`; an arbitrary header value
would otherwise reach the logs and the response as a header-injection vector.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from careerforge_api.core.ids import is_valid_request_id, new_request_id

__all__ = ["REQUEST_ID_HEADER", "RequestIDMiddleware", "request_id_of"]

#: Response/request header used by ``docs/API.md`` §1.1.
REQUEST_ID_HEADER = "X-Request-Id"

_HEADER_BYTES = REQUEST_ID_HEADER.lower().encode("latin-1")


def request_id_of(scope: Scope) -> str:
    """The correlation id for a scope, generating a fallback when unset."""
    state = scope.get("state") or {}
    return str(state.get("request_id") or "")


def _read_inbound(scope: Scope) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() == _HEADER_BYTES:
            try:
                decoded = value.decode("latin-1")
            except UnicodeDecodeError:  # pragma: no cover - latin-1 never fails
                return None
            return decoded if is_valid_request_id(decoded) else None
    return None


class RequestIDMiddleware:
    """Pure-ASGI middleware (no ``BaseHTTPMiddleware`` overhead or task-group quirks)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _read_inbound(scope) or new_request_id()
        # ``scope["state"]`` is the same mapping Starlette's ``request.state`` reads,
        # so ``request.state.request_id`` works in routers and dependencies.
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != _HEADER_BYTES
                ]
                headers.append((_HEADER_BYTES, request_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)
