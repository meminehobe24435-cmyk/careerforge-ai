"""Identifier generation: request ids, task ids and ULID helpers.

``docs/API.md`` §1.1 uses ULID-looking correlation ids (``req_01HQ8Z…``) and §1.4
shows ``tsk_01HQ…`` for async tasks. ULIDs are used because they are sortable by
creation time while staying opaque to clients.
"""

from __future__ import annotations

import re
import secrets
import time
from uuid import UUID

__all__ = [
    "REQUEST_ID_PATTERN",
    "TASK_ID_PREFIX",
    "is_valid_request_id",
    "new_request_id",
    "new_ulid",
    "parse_task_id",
    "task_public_id",
]

#: Crockford base32 — the ULID alphabet (no I, L, O, U).
_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: Inbound ``X-Request-Id`` values are echoed, so they must not be able to carry
#: header-injection payloads or unbounded length into logs.
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:\-]{1,128}$")

#: Public prefix for background-job ids (the database primary key stays a UUID).
TASK_ID_PREFIX = "tsk_"


def _encode(value: int, length: int) -> str:
    chars = ["0"] * length
    for index in range(length - 1, -1, -1):
        chars[index] = _CROCKFORD32[value & 0x1F]
        value >>= 5
    return "".join(chars)


def new_ulid(*, timestamp_ms: int | None = None) -> str:
    """A 26-character ULID: 48-bit millisecond timestamp + 80 bits of randomness."""
    stamp = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    randomness = secrets.randbits(80)
    return _encode(stamp, 10) + _encode(randomness, 16)


def new_request_id() -> str:
    """Server-generated correlation id, per ``docs/API.md`` §1.1."""
    return f"req_{new_ulid()}"


def is_valid_request_id(value: str | None) -> bool:
    """Whether an inbound ``X-Request-Id`` is safe to echo and log."""
    return bool(value) and bool(REQUEST_ID_PATTERN.match(value or ""))


def task_public_id(job_id: UUID) -> str:
    """``tsk_<uuid hex>`` — the id clients use for ``/tasks/{id}``.

    ``docs/DATABASE.md`` fixes ``background_jobs.id`` as a ``uuid`` primary key
    while ``docs/API.md`` §1.4 shows a ``tsk_…`` handle; deriving one from the
    other keeps both contracts without adding an undocumented column.
    """
    return f"{TASK_ID_PREFIX}{job_id.hex}"


def parse_task_id(raw: str) -> UUID | None:
    """Accept ``tsk_<hex>``, ``tsk-<uuid>`` or a bare UUID; ``None`` when malformed."""
    candidate = raw.strip()
    if candidate.lower().startswith(("tsk_", "tsk-")):
        candidate = candidate[4:]
    try:
        if len(candidate) == 32:
            return UUID(hex=candidate)
        return UUID(candidate)
    except ValueError:
        return None
