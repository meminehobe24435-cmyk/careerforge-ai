"""Hybrid retrieval: dense + lexical arms fused with RRF.

Why both arms (ADR-008): job and project vocabulary is full of exact technical
nouns that dense retrieval generalises away, while intent-level queries need
semantics that lexical search cannot provide. Either arm alone fails on a
recognisable class of query; together they cover each other.

The retriever degrades rather than failing. If the embedding arm is unavailable —
no API key, an embedding outage, a dimension mismatch — retrieval continues
lexically and the result is flagged ``degraded`` so the caller can say so.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
import time
from typing import Any, Protocol
from uuid import UUID

from careerforge_ai.errors import CareerForgeError
from careerforge_ai.parsing.tokenize import estimate_tokens
from careerforge_ai.rag.fusion import RRF_K, fuse_with_ranks, normalize_scores
from careerforge_ai.rag.lexical import Bm25Index
from careerforge_ai.rag.store import InMemoryVectorStore
from careerforge_ai.schemas.common import EvidenceKind, RetrievalChannel
from careerforge_ai.schemas.evidence import (
    EvidenceLocator,
    RetrievalHit,
    RetrievalResult,
)

__all__ = [
    "Embedder",
    "RetrievalDocument",
    "HybridRetriever",
    "DEFAULT_TOP_K",
    "SEMANTIC_ARM",
    "KEYWORD_ARM",
]

DEFAULT_TOP_K = 8
SEMANTIC_ARM = "semantic"
KEYWORD_ARM = "keyword"

#: Retrieval corpus size above which the in-memory exact search is flagged.
_LEXICAL_CANDIDATE_LIMIT = 200


class Embedder(Protocol):
    """Anything that can embed text — the LLM provider satisfies this."""

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> Any: ...


@dataclass(slots=True)
class RetrievalDocument:
    """One indexable evidence fragment.

    ``text`` is what gets embedded and lexically indexed; ``snippet`` is what the
    UI shows. They are usually the same, but a code chunk may be indexed with its
    file path prepended while still displaying only the code.
    """

    evidence_id: UUID
    title: str
    text: str
    kind: EvidenceKind = EvidenceKind.DOCUMENT_CHUNK
    confidence: float = 0.0
    locator: EvidenceLocator = field(default_factory=EvidenceLocator)
    project_id: UUID | None = None
    occurred_at: datetime | None = None
    snippet: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def indexed_text(self) -> str:
        """Text used for both arms. Title is prepended so a query for a file name
        can find its contents even when the name never appears in the body."""
        return f"{self.title}\n{self.text}".strip()

    def display_snippet(self, *, limit: int = 400) -> str:
        source = self.snippet if self.snippet is not None else self.text
        source = source.strip()
        return source if len(source) <= limit else source[: limit - 1].rstrip() + "…"

    def index_metadata(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "kind": self.kind.value,
            "title": self.title,
            "confidence": self.confidence,
            "tokens": estimate_tokens(self.indexed_text()),
        }
        if self.project_id is not None:
            metadata["project_id"] = str(self.project_id)
        if self.occurred_at is not None:
            metadata["occurred_at"] = self.occurred_at.isoformat()
        metadata.update(self.metadata)
        return metadata


class HybridRetriever:
    """Dense + lexical retrieval with RRF fusion and per-channel provenance."""

    def __init__(
        self,
        *,
        vector_store: InMemoryVectorStore | None = None,
        embedder: Embedder | None = None,
        rrf_k: int = RRF_K,
        top_k: int = DEFAULT_TOP_K,
        embedding_model: str | None = None,
    ) -> None:
        self._store = vector_store or InMemoryVectorStore()
        self._embedder = embedder
        self._rrf_k = rrf_k
        self._top_k = top_k
        self._embedding_model = embedding_model
        self._documents: dict[UUID, RetrievalDocument] = {}
        self._lexical = Bm25Index([])
        self._indexed_user: UUID | None = None

    # ── indexing ─────────────────────────────────────────────────────────────

    @property
    def document_count(self) -> int:
        return len(self._documents)

    async def index(
        self,
        documents: Sequence[RetrievalDocument],
        *,
        user_id: UUID,
        store_only: bool = False,
    ) -> int:
        """Index documents for one user.

        Re-indexing a document replaces it. The lexical index is rebuilt because
        BM25 statistics (document frequency, average length) are corpus-global —
        incrementally patching them would silently skew every subsequent score.
        """
        if self._indexed_user is not None and self._indexed_user != user_id:
            # One retriever serves one tenant. Mixing would be a cross-user data
            # leak, which is exactly the kind of bug that is invisible in tests
            # and catastrophic in production.
            raise CareerForgeError(
                "this retriever is already bound to a different user",
                details={"bound_user": str(self._indexed_user)},
            )
        self._indexed_user = user_id

        for document in documents:
            self._documents[document.evidence_id] = document

        if not store_only and self._embedder is not None:
            await self._embed_documents(list(documents), user_id=user_id)

        self._lexical = Bm25Index(
            (str(doc_id), document.indexed_text()) for doc_id, document in self._documents.items()
        )
        return len(documents)

    async def _embed_documents(
        self, documents: Sequence[RetrievalDocument], *, user_id: UUID
    ) -> None:
        assert self._embedder is not None  # guarded by the caller
        from careerforge_ai.ports import VectorRecord  # local import avoids a cycle at module load

        texts = [document.indexed_text() for document in documents]
        result = await self._embedder.embed(texts, model=self._embedding_model)
        vectors = getattr(result, "vectors", [])
        model = getattr(result, "model", self._embedding_model) or "unknown"

        records: list[VectorRecord] = []
        for document, vector in zip(documents, vectors, strict=False):
            records.append(
                VectorRecord(
                    owner_type="evidence",
                    owner_id=document.evidence_id,
                    model=model,
                    vector=vector,
                    metadata=document.index_metadata(),
                )
            )
        if records:
            await self._store.upsert(records, user_id=user_id)

    def remove(self, evidence_ids: Sequence[UUID]) -> int:
        removed = 0
        for evidence_id in evidence_ids:
            if self._documents.pop(evidence_id, None) is not None:
                removed += 1
        if removed:
            self._lexical = Bm25Index(
                (str(doc_id), document.indexed_text())
                for doc_id, document in self._documents.items()
            )
        return removed

    # ── retrieval ────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        *,
        user_id: UUID,
        top_k: int | None = None,
        filters: Mapping[str, Any] | None = None,
        semantic_weight_enabled: bool = True,
    ) -> RetrievalResult:
        """Run both arms, fuse, and return hits with full provenance."""
        started = time.perf_counter()
        limit = top_k or self._top_k
        if not query.strip() or not self._documents:
            return RetrievalResult(query=query, rrf_k=self._rrf_k, took_ms=0)

        dense_ranked: list[tuple[UUID, float]] = []
        degraded = False
        dense_error: str | None = None

        if semantic_weight_enabled and self._embedder is not None:
            try:
                dense_ranked = await self._dense_arm(
                    query, user_id=user_id, filters=filters, limit=_LEXICAL_CANDIDATE_LIMIT
                )
            except (CareerForgeError, AttributeError, ValueError) as exc:
                # Retrieval continues lexically. The reason is carried on the
                # result rather than swallowed, because a silent degradation is
                # how "the search got worse" turns into an unfalsifiable report.
                degraded = True
                dense_error = f"{type(exc).__name__}: {exc}"
        elif self._embedder is None:
            degraded = True
            dense_error = "no embedder configured"

        keyword_ranked = self._lexical_arm(query, filters=filters, limit=_LEXICAL_CANDIDATE_LIMIT)

        rankings: dict[str, list[str]] = {
            SEMANTIC_ARM: [str(doc_id) for doc_id, _ in dense_ranked],
            KEYWORD_ARM: [str(doc_id) for doc_id, _ in keyword_ranked],
        }
        fused = fuse_with_ranks(rankings, k=self._rrf_k)
        if not fused:
            return RetrievalResult(query=query, rrf_k=self._rrf_k, degraded=degraded)

        ordered = sorted(fused.items(), key=lambda item: (-item[1][0], item[0]))[:limit]
        relevance = normalize_scores({doc_id: value for doc_id, (value, _) in ordered})

        hits: list[RetrievalHit] = []
        for doc_id, (score, arm_ranks) in ordered:
            document = self._documents.get(UUID(doc_id))
            if document is None:
                continue
            channel = _channel_of(arm_ranks)
            hits.append(
                RetrievalHit(
                    evidence_id=document.evidence_id,
                    title=document.title,
                    kind=document.kind,
                    snippet=document.display_snippet(),
                    locator=document.locator,
                    confidence=document.confidence,
                    relevance=relevance.get(doc_id, 0.0),
                    channel=channel,
                    semantic_rank=arm_ranks.get(SEMANTIC_ARM),
                    keyword_rank=arm_ranks.get(KEYWORD_ARM),
                    fused_score=score,
                )
            )

        result = RetrievalResult(
            query=query,
            hits=hits,
            filters=dict(filters or {}),
            semantic_candidates=len(dense_ranked),
            keyword_candidates=len(keyword_ranked),
            fused_candidates=len(fused),
            rrf_k=self._rrf_k,
            took_ms=int((time.perf_counter() - started) * 1000),
            degraded=degraded,
        )
        if dense_error:
            result.filters["_dense_error"] = dense_error
        return result

    async def _dense_arm(
        self,
        query: str,
        *,
        user_id: UUID,
        filters: Mapping[str, Any] | None,
        limit: int,
    ) -> list[tuple[UUID, float]]:
        assert self._embedder is not None
        result = await self._embedder.embed([query], model=self._embedding_model)
        vectors = getattr(result, "vectors", [])
        if not vectors:
            return []
        model = getattr(result, "model", self._embedding_model)
        hits = await self._store.search(
            vectors[0],
            user_id=user_id,
            owner_types=["evidence"],
            model=model,
            limit=limit,
            filters=filters,
        )
        return [(hit.owner_id, hit.score) for hit in hits]

    def _lexical_arm(
        self,
        query: str,
        *,
        filters: Mapping[str, Any] | None,
        limit: int,
    ) -> list[tuple[UUID, float]]:
        ranked = self._lexical.search(query, limit=max(limit, len(self._documents)))
        out: list[tuple[UUID, float]] = []
        for doc_id, score in ranked:
            document = self._documents.get(UUID(doc_id))
            if document is None:
                continue
            if filters and not _metadata_matches(document.index_metadata(), filters):
                continue
            out.append((document.evidence_id, score))
            if len(out) >= limit:
                break
        return out


def _channel_of(arm_ranks: Mapping[str, int]) -> RetrievalChannel:
    """Which arm(s) found this hit — shown in the UI, not just logged."""
    has_semantic = SEMANTIC_ARM in arm_ranks
    has_keyword = KEYWORD_ARM in arm_ranks
    if has_semantic and has_keyword:
        return RetrievalChannel.BOTH
    if has_semantic:
        return RetrievalChannel.SEMANTIC
    if has_keyword:
        return RetrievalChannel.KEYWORD
    return RetrievalChannel.METADATA


def _metadata_matches(metadata: Mapping[str, Any], filters: Mapping[str, Any]) -> bool:
    for key, expected in filters.items():
        if key.startswith("_"):
            continue
        actual = metadata.get(key)
        if isinstance(expected, (list, tuple, set, frozenset)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True
