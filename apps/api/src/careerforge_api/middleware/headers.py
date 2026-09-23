"""Header names shared across the middleware chain, and response hygiene.

These live in their own module because they are the one thing two middleware layers
must agree on without importing each other: the request-id echo (outermost layer) and
the envelope marker (innermost layer) are both written into the same header list, and a
mutual import between those modules would be circular.

``X-Envelope-Complete`` is an *internal* handshake: the error handlers and the rate
limiter mark a body that is already the documented envelope so the envelope writer does
not wrap it twice. The outermost middleware strips the marker from every response,
because a response produced outside the envelope writer never passes through it.
"""

from __future__ import annotations

__all__ = [
    "ENVELOPE_COMPLETE_HEADER",
    "ENVELOPE_DONE",
    "REQUEST_ID_HEADER",
    "STRIPPED_HEADERS",
    "has_envelope_marker",
    "strip_internal_headers",
]

#: Response/request header frozen by ``docs/API.md`` §1.1.
REQUEST_ID_HEADER = "X-Request-Id"

#: Internal handshake header between the error handlers and the envelope writer.
ENVELOPE_COMPLETE_HEADER = "X-Envelope-Complete"

#: Value of the marker on a body that already is the documented envelope.
ENVELOPE_DONE = "1"

_REQUEST_ID_BYTES = REQUEST_ID_HEADER.lower().encode("latin-1")
_ENVELOPE_HEADER_BYTES = ENVELOPE_COMPLETE_HEADER.lower().encode("latin-1")

#: Headers that exist only between middleware layers.
STRIPPED_HEADERS: frozenset[bytes] = frozenset({_ENVELOPE_HEADER_BYTES})


def strip_internal_headers(headers: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """Drop internal handshake headers before a client can see them."""
    return [(key, value) for key, value in headers if key.lower() not in STRIPPED_HEADERS]


def has_envelope_marker(headers: list[tuple[bytes, bytes]]) -> bool:
    """Whether these headers carry the envelope marker (set by an inner layer)."""
    return any(key.lower() == _ENVELOPE_HEADER_BYTES for key, _ in headers)


def request_id_header_bytes() -> bytes:
    """Lower-case ``bytes`` form of the request-id header, for ASGI header lists."""
    return _REQUEST_ID_BYTES
