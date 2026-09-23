"""Hybrid retrieval: dense + lexical search fused with Reciprocal Rank Fusion.

Both arms exist for a domain-specific reason: job and project vocabulary is full
of exact technical nouns (``STM32F407``, ``heap_4``, ``CANopen``) that pure vector
search generalises away, while intent-level queries ("multi-task real-time
scheduling") need semantics that keyword search cannot provide. See ADR-008.

Public surface::

    chunk_text(text, kind="resume")  # heading-aware, overlapping chunks
    HybridRetriever(embedder=provider)  # index + retrieve
    InMemoryVectorStore()  # the local VectorStore port
    Bm25Index(documents)  # the lexical arm on its own
    reciprocal_rank_fusion(rankings)  # the fusion, usable standalone
"""

from __future__ import annotations

from careerforge_ai.rag.chunking import Chunk, ChunkingConfig, SourceKind, chunk_text
from careerforge_ai.rag.fusion import (
    RRF_K,
    fuse_with_ranks,
    normalize_scores,
    reciprocal_rank_fusion,
)
from careerforge_ai.rag.lexical import BM25_B, BM25_K1, Bm25Index
from careerforge_ai.rag.retriever import (
    DEFAULT_TOP_K,
    KEYWORD_ARM,
    SEMANTIC_ARM,
    Embedder,
    HybridRetriever,
    RetrievalDocument,
)
from careerforge_ai.rag.store import SCALE_WARNING_THRESHOLD, InMemoryVectorStore

__all__ = [
    "BM25_B",
    "BM25_K1",
    "DEFAULT_TOP_K",
    "KEYWORD_ARM",
    "RRF_K",
    "SCALE_WARNING_THRESHOLD",
    "SEMANTIC_ARM",
    "Bm25Index",
    "Chunk",
    "ChunkingConfig",
    "Embedder",
    "HybridRetriever",
    "InMemoryVectorStore",
    "RetrievalDocument",
    "SourceKind",
    "chunk_text",
    "fuse_with_ranks",
    "normalize_scores",
    "reciprocal_rank_fusion",
]
