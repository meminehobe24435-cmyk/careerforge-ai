"""``ai_caches`` — persisted LLM/embedding/tool cache entries (§2.11).

The AI core keeps its hot cache in memory (``InMemoryCacheStore``); this table is
the durable layer that survives a restart and gives ``GET /cache/stats`` something
real to report. ``unique(cache_key)`` plus ``hit_count`` makes "cache hit" a fact
recorded in the database rather than a log line.

Rows are cleaned up when expired; ``user_id`` is nullable because shared
system-level prompts may be cached for everyone.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType, TimestampType, UUIDType

__all__ = ["AI_CACHE_KINDS", "AiCache"]

AI_CACHE_KINDS: tuple[str, ...] = ("llm", "embedding", "tool")

_KIND_LIST = ", ".join(f"'{kind}'" for kind in AI_CACHE_KINDS)


class AiCache(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One cache entry (``kind`` distinguishes LLM, embedding and tool results)."""

    __tablename__ = "ai_caches"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_KIND_LIST})", name="kind_valid"),
        CheckConstraint("hit_count >= 0", name="hit_count_non_negative"),
        CheckConstraint("size_bytes IS NULL OR size_bytes >= 0", name="size_bytes_non_negative"),
        UniqueConstraint("cache_key", name="uq_ai_caches_cache_key"),
        Index("ix_ai_caches_kind_expires_at", "kind", "expires_at"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    #: Deterministic digest of the request (model + messages + temperature).
    cache_key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False, default="llm")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
