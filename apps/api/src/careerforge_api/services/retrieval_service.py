"""Retrieval over the user's *stored* evidence.

The Claim Validator needs a retriever, and without one it does not degrade gracefully — it
rejects. The gate's retrieval phase reports "no retriever configured" and returns zero hits, so
every claim reaches the verdict with nothing behind it, including the sentences the candidate's
own résumé plainly supports. A live run showed exactly that: "使用 STM32 与 FreeRTOS 开发电机
控制固件" came back ``unsupported``, with ``skill_not_in_graph`` and ``no_evidence_match``, while
the graph held eight pieces of evidence for those two skills.

This module closes it by building the project's own hybrid retriever (BM25 + vectors, RRF-fused,
ADR-0006) over the rows in ``evidence``. Per request, because the corpus is one candidate's
material — a few hundred fragments at most — and because a shared index would leak one tenant's
evidence into another's ranking.

The vector arm is used when the provider can embed. Without an embedding model the retriever
still runs on BM25 alone and says so through each hit's ``channel``, which is the honest
degradation rather than a silent one.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.rag.retriever import HybridRetriever, RetrievalDocument
from careerforge_ai.schemas.common import EvidenceKind
from careerforge_ai.schemas.evidence import EvidenceLocator
from careerforge_api.models.evidence import Evidence

__all__ = ["EvidenceRetrieverService", "build_retriever"]

#: How many stored fragments one candidate's index holds. Well above a real résumé's evidence
#: count, and low enough that indexing per request stays cheap.
MAX_INDEXED_EVIDENCE = 2000


class EvidenceRetrieverService:
    """Builds a retriever over one user's stored evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def documents(self, *, user_id: UUID) -> list[RetrievalDocument]:
        rows = (
            await self._session.scalars(
                select(Evidence)
                .where(Evidence.user_id == user_id)
                .order_by(Evidence.confidence.desc())
                .limit(MAX_INDEXED_EVIDENCE)
            )
        ).all()
        return [document_of(row) for row in rows]

    async def retriever(self, *, user_id: UUID, embedder: Any | None = None) -> HybridRetriever:
        """A retriever populated with this user's evidence.

        Returns an empty-but-usable retriever when the user has no evidence: the gate then
        correctly reports that nothing supports the claim, which is different from the
        retriever itself being absent.
        """
        retriever = HybridRetriever(embedder=embedder if _can_embed(embedder) else None)
        documents = await self.documents(user_id=user_id)
        if documents:
            await retriever.index(documents, user_id=user_id)
        return retriever


def _can_embed(embedder: Any | None) -> bool:
    """Whether the provider can actually embed.

    Checked rather than assumed: passing a provider whose embedding endpoint is unavailable
    would make every indexing call raise, turning a working lexical retriever into a failure.
    """
    if embedder is None:
        return False
    capabilities = getattr(embedder, "capabilities", None)
    if capabilities is None:
        return hasattr(embedder, "embed")
    return bool(getattr(capabilities, "embeddings", False))


def document_of(row: Evidence) -> RetrievalDocument:
    """Map a stored evidence row onto an indexable fragment.

    ``text`` is the snippet — the material a reviewer would read — and the title is prepended by
    ``RetrievalDocument.indexed_text``, so a query naming a file can find its contents even when
    the name never appears in the body.
    """
    metadata = dict(row.metadata_ or {})
    return RetrievalDocument(
        evidence_id=row.id,
        title=row.title,
        text=row.snippet or row.title,
        kind=_kind_of(row.kind),
        confidence=float(row.confidence),
        locator=EvidenceLocator.model_validate(row.locator or {}),
        occurred_at=row.occurred_at,
        snippet=row.snippet or None,
        metadata=metadata,
    )


def _kind_of(value: str) -> EvidenceKind:
    try:
        return EvidenceKind(value)
    except ValueError:
        return EvidenceKind.MANUAL


async def build_retriever(
    session: AsyncSession, *, user_id: UUID, embedder: Any | None = None
) -> HybridRetriever:
    """Convenience wrapper for call sites that do not need the service object."""
    return await EvidenceRetrieverService(session).retriever(user_id=user_id, embedder=embedder)
