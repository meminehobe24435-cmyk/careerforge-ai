"""In-memory vector store.

A complete implementation of the :class:`careerforge_ai.ports.VectorStore` port,
used for local runs, tests and the evaluation runner. Production uses
``PgVectorStore`` (pgvector + HNSW) behind the same contract; nothing above this
layer knows which one is active (ADR-004).

Exact search rather than an approximate index, on purpose: below roughly fifty
thousand vectors the difference is unmeasurable, and exact results remove a whole
class of "why did retrieval miss that" investigations during development. The
scale limit is asserted rather than assumed — see :meth:`InMemoryVectorStore.warn_if_large`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import numpy as np

from careerforge_ai.errors import RetrievalError
from careerforge_ai.ports import VectorHit, VectorRecord

__all__ = ["InMemoryVectorStore", "SCALE_WARNING_THRESHOLD"]

#: Above this many vectors, exact in-memory search stops being the right tool.
SCALE_WARNING_THRESHOLD = 50_000


@dataclass(slots=True)
class _Entry:
    owner_type: str
    owner_id: UUID
    model: str
    vector: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)


class InMemoryVectorStore:
    """Cosine-similarity search over L2-normalised vectors.

    Vectors are normalised on write, so cosine similarity reduces to a dot
    product and the query path stays a single matrix multiplication.
    """

    def __init__(self) -> None:
        # Keyed by (user_id, owner_type, owner_id, model) so re-indexing the same
        # entity with the same model overwrites rather than duplicates.
        self._entries: dict[tuple[UUID, str, UUID, str], _Entry] = {}

    # ── port surface ─────────────────────────────────────────────────────────

    async def upsert(self, records: Sequence[VectorRecord], *, user_id: UUID) -> int:
        """Insert or replace vectors. Returns the number written."""
        written = 0
        for record in records:
            if not record.vector:
                continue
            vector = np.asarray(record.vector, dtype=np.float32)
            expected_dim = record.dim
            if expected_dim and vector.shape[0] != expected_dim:
                raise RetrievalError(
                    "vector dimension does not match its declared dim",
                    details={"declared": expected_dim, "actual": int(vector.shape[0])},
                )
            norm = float(np.linalg.norm(vector))
            if norm > 0:
                vector = vector / norm
            key = (user_id, record.owner_type, record.owner_id, record.model)
            self._entries[key] = _Entry(
                owner_type=record.owner_type,
                owner_id=record.owner_id,
                model=record.model,
                vector=vector,
                metadata=dict(record.metadata),
            )
            written += 1
        return written

    async def search(
        self,
        vector: Sequence[float],
        *,
        user_id: UUID,
        owner_types: Sequence[str] | None = None,
        model: str | None = None,
        limit: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[VectorHit]:
        """Nearest neighbours for ``vector``, best first."""
        if limit <= 0 or not self._entries:
            return []

        query = np.asarray(vector, dtype=np.float32)
        if query.size == 0:
            return []
        query_norm = float(np.linalg.norm(query))
        if query_norm > 0:
            query = query / query_norm

        allowed_types = set(owner_types) if owner_types else None
        candidates: list[_Entry] = []
        for (entry_user, _owner_type, _owner_id, entry_model), entry in self._entries.items():
            if entry_user != user_id:
                continue
            if allowed_types is not None and entry.owner_type not in allowed_types:
                continue
            if model is not None and entry_model != model:
                continue
            if entry.vector.shape[0] != query.shape[0]:
                # A dimension mismatch means a different embedding model produced
                # the stored vector; mixing them would produce meaningless
                # similarity, so the entry is skipped rather than silently scored.
                continue
            if filters and not _matches(entry.metadata, filters):
                continue
            candidates.append(entry)

        if not candidates:
            return []

        matrix = np.vstack([entry.vector for entry in candidates])
        scores = matrix @ query

        take = min(limit, len(candidates))
        # argpartition avoids sorting the whole corpus for a small k.
        top = (
            np.argpartition(-scores, take - 1)[:take]
            if take < len(candidates)
            else np.arange(len(candidates))
        )
        ordered = sorted(
            top.tolist(), key=lambda index: (-float(scores[index]), candidates[index].owner_id.int)
        )

        return [
            VectorHit(
                owner_type=candidates[index].owner_type,
                owner_id=candidates[index].owner_id,
                score=round(float(scores[index]), 6),
                metadata=candidates[index].metadata,
            )
            for index in ordered[:take]
        ]

    async def delete(self, *, user_id: UUID, owner_type: str, owner_ids: Sequence[UUID]) -> int:
        targets = set(owner_ids)
        keys = [
            key
            for key in self._entries
            if key[0] == user_id and key[1] == owner_type and key[2] in targets
        ]
        for key in keys:
            del self._entries[key]
        return len(keys)

    # ── inspection ───────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._entries)

    def owner_types(self, *, user_id: UUID) -> set[str]:
        return {key[1] for key in self._entries if key[0] == user_id}

    def warn_if_large(self) -> str | None:
        """Return an advisory message once the exact-search assumption breaks."""
        if self.size > SCALE_WARNING_THRESHOLD:
            return (
                f"in-memory exact search holds {self.size} vectors "
                f"(advisory limit {SCALE_WARNING_THRESHOLD}); switch to the pgvector store"
            )
        return None

    def clear(self) -> None:
        self._entries.clear()


def _matches(metadata: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    """Metadata filter where a list value means "any of" and scalars mean equality."""
    for key, expected in filters.items():
        actual = metadata.get(key)
        if isinstance(expected, (list, tuple, set, frozenset)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True
