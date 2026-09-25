"""Evidence and edge data access.

Tenant rule as everywhere: every query filters by ``user_id``, and a cross-tenant lookup
returns ``None``. ``evidence_links`` has no foreign keys on its endpoints (a node may be a
candidate, a skill or an evidence item), so the tenancy filter is the *only* thing keeping
one candidate's edges away from another's — which is why it lives here and not at the call
site.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.models.evidence import Evidence, EvidenceLinkRow

__all__ = ["EvidenceRepository"]


class EvidenceRepository:
    """Tenant-scoped reads and writes for ``evidence`` / ``evidence_links``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── evidence ─────────────────────────────────────────────────────────────

    async def get(self, evidence_id: UUID, *, user_id: UUID) -> Evidence | None:
        statement = select(Evidence).where(Evidence.id == evidence_id, Evidence.user_id == user_id)
        return await self._session.scalar(statement)

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        kind: str | None = None,
        min_confidence: float = 0.0,
        document_chunk_id: UUID | None = None,
        limit: int = 100,
    ) -> Sequence[Evidence]:
        statement = select(Evidence).where(Evidence.user_id == user_id)
        if kind is not None:
            statement = statement.where(Evidence.kind == kind)
        if min_confidence:
            statement = statement.where(Evidence.confidence >= Decimal(str(min_confidence)))
        if document_chunk_id is not None:
            statement = statement.where(Evidence.document_chunk_id == document_chunk_id)
        statement = statement.order_by(Evidence.confidence.desc(), Evidence.created_at.desc())
        return (await self._session.scalars(statement.limit(limit))).all()

    async def count(self, *, user_id: UUID, kind: str | None = None) -> int:
        statement = select(func.count()).select_from(Evidence).where(Evidence.user_id == user_id)
        if kind is not None:
            statement = statement.where(Evidence.kind == kind)
        return int(await self._session.scalar(statement) or 0)

    async def content_hashes(self, *, user_id: UUID, kind: str) -> set[str]:
        """Existing hashes for one kind, so a re-analysis can skip what is already stored."""
        statement = select(Evidence.content_hash).where(
            Evidence.user_id == user_id, Evidence.kind == kind
        )
        return set((await self._session.scalars(statement)).all())

    async def by_content_hash(
        self, *, user_id: UUID, kind: str, content_hash: str
    ) -> Evidence | None:
        """The row ``uq_evidence_user_id`` would collide with, if it exists.

        The tenancy triple is the constraint's own key, so this is the lookup that turns an
        ``IntegrityError`` into an answer — see :meth:`EvidenceService.add_manual`.
        """
        statement = select(Evidence).where(
            Evidence.user_id == user_id,
            Evidence.kind == kind,
            Evidence.content_hash == content_hash,
        )
        return await self._session.scalar(statement)

    async def upsert_many(self, rows: Iterable[dict[str, Any]]) -> list[Evidence]:
        """Insert evidence, reusing the row when the same content was already extracted.

        Upsert rather than insert because ``uq_evidence_user_id`` makes a second copy of
        identical evidence impossible — and *should*: the same sentence extracted twice is
        one piece of evidence, not two, and counting it twice would inflate corroboration.
        """
        stored: list[Evidence] = []
        for row in rows:
            statement = select(Evidence).where(
                Evidence.user_id == row["user_id"],
                Evidence.kind == row["kind"],
                Evidence.content_hash == row["content_hash"],
            )
            existing = await self._session.scalar(statement)
            if existing is None:
                existing = Evidence(**row)
                self._session.add(existing)
            else:
                # Refresh the factors: a re-analysis may have new corroboration.
                existing.confidence = row["confidence"]
                existing.corroboration_count = row["corroboration_count"]
                existing.recency_score = row["recency_score"]
                existing.metadata_ = row["metadata_"]
            await self._session.flush()
            stored.append(existing)
        return stored

    async def delete(self, evidence: Evidence) -> None:
        """Delete the item and every edge that points at it.

        The edges are not covered by a foreign key (their endpoints are polymorphic), so
        they are removed explicitly — otherwise the graph would keep edges to evidence that
        no longer exists and the UI would render a node it cannot open.
        """
        await self._session.execute(
            delete(EvidenceLinkRow).where(
                EvidenceLinkRow.user_id == evidence.user_id,
                EvidenceLinkRow.to_id == evidence.id,
            )
        )
        await self._session.execute(
            delete(EvidenceLinkRow).where(
                EvidenceLinkRow.user_id == evidence.user_id,
                EvidenceLinkRow.from_id == evidence.id,
            )
        )
        await self._session.delete(evidence)

    # ── links ────────────────────────────────────────────────────────────────

    async def list_links(self, *, user_id: UUID, limit: int = 5000) -> Sequence[EvidenceLinkRow]:
        statement = (
            select(EvidenceLinkRow)
            .where(EvidenceLinkRow.user_id == user_id)
            .order_by(EvidenceLinkRow.created_at)
            .limit(limit)
        )
        return (await self._session.scalars(statement)).all()

    async def links_for(self, node_id: UUID, *, user_id: UUID) -> Sequence[EvidenceLinkRow]:
        """Edges touching one node, in either direction."""
        statement = select(EvidenceLinkRow).where(
            EvidenceLinkRow.user_id == user_id,
            ((EvidenceLinkRow.from_id == node_id) | (EvidenceLinkRow.to_id == node_id)),
        )
        return (await self._session.scalars(statement)).all()

    async def insert_links(self, rows: Iterable[dict[str, Any]]) -> int:
        """Insert edges, skipping ones that already exist; returns how many were new.

        The five-tuple is unique, so a rebuild must not duplicate. The existing keys are
        read once into a set rather than tested per row: one query instead of N, and it
        stays portable. ``INSERT ... ON CONFLICT DO NOTHING`` would be shorter but its
        spelling differs between SQLite and PostgreSQL, and CI runs both (ADR-004).
        """
        pending = list(rows)
        if not pending:
            return 0

        known = {
            (row.from_type, row.from_id, row.to_type, row.to_id, row.relation)
            for row in await self.list_links(user_id=pending[0]["user_id"])
        }

        written = 0
        for row in pending:
            key = (row["from_type"], row["from_id"], row["to_type"], row["to_id"], row["relation"])
            if key in known:
                continue
            known.add(key)
            self._session.add(EvidenceLinkRow(**row))
            written += 1
        await self._session.flush()
        return written

    async def delete_links_for(self, *, user_id: UUID, document_chunk_ids: Sequence[UUID]) -> int:
        """Drop edges whose evidence came from these chunks, before re-analysing them."""
        if not document_chunk_ids:
            return 0
        evidence_ids = select(Evidence.id).where(
            Evidence.user_id == user_id, Evidence.document_chunk_id.in_(document_chunk_ids)
        )
        result = await self._session.execute(
            delete(EvidenceLinkRow).where(
                EvidenceLinkRow.user_id == user_id,
                EvidenceLinkRow.to_id.in_(evidence_ids),
            )
        )
        # ``rowcount`` is on CursorResult, which the ``Result`` protocol does not declare.
        return int(getattr(result, "rowcount", 0) or 0)

    async def count_links(self, *, user_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(EvidenceLinkRow)
            .where(EvidenceLinkRow.user_id == user_id)
        )
        return int(await self._session.scalar(statement) or 0)
