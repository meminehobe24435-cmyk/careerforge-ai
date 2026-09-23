"""Cursor pagination, exactly as ``docs/API.md`` §1.3 specifies.

Default ``limit`` 20, maximum 100, an opaque ``nextCursor``, and a ``total``. The
cursor is base64-encoded JSON (the document shows ``eyJjcmVhdGVkX2F0Ijoi…`` — i.e.
``{"created_at": "…"}``), which keeps it opaque to clients without inventing a
signing scheme for PHASE 1.

No PHASE 1 endpoint returns a list, so this module is the contract the PHASE 2 list
endpoints (`/jobs`, `/evidence`, `/applications`, …) are built on.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
import json
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

from careerforge_api.core.errors import ValidationError

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "CursorPage",
    "PageParams",
    "decode_cursor",
    "encode_cursor",
]

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def encode_cursor(payload: dict[str, Any]) -> str:
    """Opaque cursor from a keyset position (e.g. ``{"created_at": ...}``)."""
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Inverse of :func:`encode_cursor`; a malformed cursor is a 400, not a 500."""
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        value = json.loads(decoded.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            "Invalid pagination cursor",
            details=[{"field": "cursor", "issue": "invalid_cursor"}],
        ) from exc
    if not isinstance(value, dict):
        raise ValidationError(
            "Invalid pagination cursor",
            details=[{"field": "cursor", "issue": "invalid_cursor"}],
        )
    return value


class PageParams:
    """The documented list parameters, usable as a FastAPI dependency."""

    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Page size")] = DEFAULT_LIMIT,
        cursor: Annotated[str | None, Query(description="Opaque keyset cursor")] = None,
        sort: Annotated[str | None, Query(description="Whitelisted sort field")] = None,
        order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
    ) -> None:
        self.limit = limit
        self.cursor = cursor
        self.sort = sort
        self.order = order

    @property
    def position(self) -> dict[str, Any] | None:
        return decode_cursor(self.cursor) if self.cursor else None

    def cursor_from(self, row: dict[str, Any]) -> str:
        """Build the cursor that continues after ``row``."""
        return encode_cursor(row)

    def allowed_sort(self, whitelist: set[str], *, default: str) -> str:
        """Reject an unwhitelisted sort field — no SQL identifier ever comes from input."""
        if self.sort is None:
            return default
        if self.sort not in whitelist:
            raise ValidationError(
                f"Unsupported sort field '{self.sort}'",
                details=[
                    {
                        "field": "sort",
                        "issue": "not_allowed",
                        "message": f"allowed: {', '.join(sorted(whitelist))}",
                    }
                ],
            )
        return self.sort


class CursorPage[ItemT](BaseModel):
    """``{ items, nextCursor, total }`` (``docs/API.md`` §1.3)."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[ItemT] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    total: int = 0


def page_meta(limit: int, total: int, *, returned: int) -> dict[str, int | bool]:
    """Small helper for endpoints that also want to report truncation."""
    return {"limit": limit, "total": total, "returned": returned, "truncated": returned >= limit}


def iso_cursor(value: datetime) -> str:
    """Cursor payload for a ``created_at``-ordered list."""
    return encode_cursor({"created_at": value.isoformat()})
