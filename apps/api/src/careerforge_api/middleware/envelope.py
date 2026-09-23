"""The response envelope: ``{ success, data, error, requestId }`` for every JSON body.

``docs/API.md`` §1.1 freezes one envelope for every endpoint, so it is applied by
middleware rather than by each handler — a handler cannot forget it, and a new
endpoint is enveloped the moment it returns JSON.

Two mechanics are worth knowing when reading this file:

* Responses produced by :mod:`careerforge_api.middleware.errors` are already
  complete envelopes. They are marked with ``X-Envelope-Complete`` and passed
  through untouched (the marker is stripped before the response leaves), which is
  what prevents double wrapping. The marker never reaches the client.
* Only ``application/json`` bodies are buffered and rewritten. SSE
  (``text/event-stream``), file downloads and the HTML docs pass through
  unbuffered, because buffering a stream would break ``docs/API.md`` §1.5.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from careerforge_api.core.errors import ApiError, error_from_status
from careerforge_api.core.ids import new_request_id
from careerforge_api.middleware.request_id import request_id_of

__all__ = [
    "ENVELOPE_COMPLETE_HEADER",
    "EnvelopeMiddleware",
    "envelope",
    "error_envelope",
]

#: Internal handshake header between the error handlers and this middleware.
ENVELOPE_COMPLETE_HEADER = "X-Envelope-Complete"
_ENVELOPE_HEADER_BYTES = ENVELOPE_COMPLETE_HEADER.lower().encode("latin-1")
_ENVELOPE_DONE = "1"


def envelope(data: Any, *, request_id: str) -> dict[str, Any]:
    """The documented success body."""
    return {"success": True, "data": data, "error": None, "requestId": request_id}


def error_envelope(error: ApiError, *, request_id: str) -> dict[str, Any]:
    """The documented failure body."""
    return {"success": False, "data": None, "error": error.to_payload(), "requestId": request_id}


def _content_type(headers: list[tuple[bytes, bytes]]) -> str:
    for key, value in headers:
        if key.lower() == b"content-type":
            return value.decode("latin-1").lower()
    return ""


def _decode(body: bytes) -> tuple[bool, Any]:
    """``(decoded_ok, value)`` — invalid JSON is passed through rather than mangled."""
    if not body:
        return True, None
    try:
        return True, json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, None


class EnvelopeMiddleware:
    """Wraps every JSON response in the documented envelope."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = request_id_of(scope) or new_request_id()
        buffer: list[bytes] = []
        wrap = False
        start_message: Message = {"type": "http.response.start", "status": 200, "headers": []}

        async def send_wrapper(message: Message) -> None:
            nonlocal wrap, start_message

            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                already_enveloped = any(key.lower() == _ENVELOPE_HEADER_BYTES for key, _ in headers)
                stripped = {
                    **message,
                    "headers": [
                        (key, value)
                        for key, value in headers
                        if key.lower() != _ENVELOPE_HEADER_BYTES
                    ],
                }
                start_message = stripped
                wrap = not already_enveloped and _content_type(headers).startswith(
                    "application/json"
                )
                if not wrap:
                    await send(stripped)
                return

            if message["type"] == "http.response.body" and wrap:
                buffer.append(message.get("body") or b"")
                if message.get("more_body"):
                    return
                rendered = _render(start_message, b"".join(buffer), request_id)
                headers = [
                    (key, value)
                    for key, value in start_message.get("headers", [])
                    if key.lower() != b"content-length"
                ]
                # The envelope changes the byte length, so the length must be recomputed.
                headers.append((b"content-length", str(len(rendered)).encode("latin-1")))
                await send({**start_message, "headers": headers})
                await send(
                    {
                        "type": "http.response.body",
                        "body": rendered,
                        "more_body": False,
                    }
                )
                return

            await send(message)

        await self.app(scope, receive, send_wrapper)


def _render(start_message: Message, body: bytes, request_id: str) -> bytes:
    status = int(start_message.get("status", 200))
    decoded_ok, value = _decode(body)
    if not decoded_ok:
        # A body that is not JSON despite its content type is a bug somewhere
        # below; forwarding it unchanged is more honest than replacing it.
        return body
    if 200 <= status < 400:
        payload = envelope(value, request_id=request_id)
    elif isinstance(value, dict) and "code" in value:
        payload = {
            "success": False,
            "data": None,
            "error": {
                "code": value.get("code"),
                "message": value.get("message", ""),
                "details": value.get("details", []),
            },
            "requestId": request_id,
        }
    else:
        detail = value.get("detail") if isinstance(value, dict) else None
        payload = error_envelope(
            error_from_status(status, str(detail) if detail else None),
            request_id=request_id,
        )
    return json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
