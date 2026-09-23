"""Evidence: from stored material to a queryable graph.

The division of labour matters here. The AI core decides *what is evidence* and *how
confident it is* (``careerforge_ai.graph.build_evidence_graph``); this service does the
three things the core cannot, because they need the database:

1. turn stored ``document_chunks`` into ``EvidenceItem`` inputs, with a locator a human
   can follow back to a page and a character range;
2. persist the result, and **remap the engine's node ids onto the stored rows** — the
   core derives ids from content (``node_id``) while the database generates its own, so
   an edge written with the engine's id would point at a node no join can resolve;
3. load the rows back as nodes and edges. The graph is *derived*, never stored as nodes:
   skills come from the ``skills`` table, the candidate from ``profiles``, and only
   evidence and edges are rows of their own (ADR-005).

Re-analysis is idempotent: evidence de-duplicates on ``(user_id, kind, content_hash)`` and
edges on their five-tuple, so running the same analysis twice cannot double the graph.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.graph import build_evidence_graph, node_id
from careerforge_ai.graph.builder_types import GraphBuildResult
from careerforge_ai.schemas.common import (
    EvidenceKind,
    EvidenceRelation,
    GraphNodeType,
    SourceAuthority,
)
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator, GraphEdge, GraphNode
from careerforge_ai.schemas.profile import CandidateProfile
from careerforge_ai.scoring.confidence import compute_confidence
from careerforge_api.models.document import Document, DocumentChunk
from careerforge_api.models.evidence import Evidence, EvidenceLinkRow
from careerforge_api.models.skill import Skill
from careerforge_api.models.user import Profile, User
from careerforge_api.repositories.evidence_repository import EvidenceRepository
from careerforge_api.services.profile_service import ProfileService

__all__ = [
    "EvidenceAnalysisResult",
    "EvidenceService",
    "evidence_from_chunks",
    "node_type_of",
    "snippet_of",
]

#: A snippet is what a human reads to judge the evidence: long enough to carry the
#: sentence, short enough to render in a drawer beside a claim.
SNIPPET_CHARS = 400

#: Chunks shorter than this carry no claim worth citing — a heading or a page number.
MIN_CHUNK_CHARS = 12

#: Evidence kind → the node type the graph draws it as. The two vocabularies overlap but
#: do not coincide: two kinds of evidence can be the same kind of node ("readme" and
#: "document_chunk" are both documents to a reader).
_NODE_TYPE_BY_KIND: dict[EvidenceKind, GraphNodeType] = {
    EvidenceKind.REPO_FILE: GraphNodeType.REPO_FILE,
    EvidenceKind.COMMIT: GraphNodeType.COMMIT,
    EvidenceKind.README: GraphNodeType.DOCUMENT,
    EvidenceKind.DOCUMENT_CHUNK: GraphNodeType.DOCUMENT,
    EvidenceKind.EXPERIENCE: GraphNodeType.EXPERIENCE,
    EvidenceKind.PROJECT: GraphNodeType.PROJECT,
    EvidenceKind.ACHIEVEMENT: GraphNodeType.ACHIEVEMENT,
    EvidenceKind.MANUAL: GraphNodeType.DOCUMENT,
    EvidenceKind.LLM_INFERENCE: GraphNodeType.CLAIM,
}


@dataclass(slots=True)
class EvidenceAnalysisResult:
    """What one analysis pass stored."""

    document_id: UUID
    evidence_created: int
    evidence_updated: int
    links_written: int
    skill_count: int
    nodes: int = 0
    edges: int = 0
    mean_confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


def snippet_of(text: str, *, limit: int = SNIPPET_CHARS) -> str:
    """First ``limit`` characters, cut on a sentence boundary when one is nearby.

    Cutting mid-word makes the quote unreadable, and the quote is the point of showing
    evidence next to a claim.
    """
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    window = cleaned[:limit]
    for separator in ("。", ". ", "；", "; ", "\n"):
        cut = window.rfind(separator)
        if cut >= limit // 2:
            return window[: cut + len(separator)].strip()
    return window.strip()


def node_type_of(kind: str) -> GraphNodeType:
    """Node type for a stored evidence kind; unknown kinds become claims.

    ``GraphNodeType.CLAIM`` is the honest fallback: a node that references evidence but
    whose own nature this build does not know.
    """
    try:
        return _NODE_TYPE_BY_KIND[EvidenceKind(kind)]
    except ValueError:
        return GraphNodeType.CLAIM


def evidence_from_chunks(
    document: Document,
    chunks: Sequence[DocumentChunk],
) -> list[EvidenceItem]:
    """Turn stored chunks into evidence inputs.

    The authority tier is ``UPLOADED_DOCUMENT``: material the candidate supplied is weaker
    than code they wrote and stronger than a claim they typed. Confidence is left at 0.0
    on purpose — the builder computes it from the five factors, and anything invented here
    would be overwritten.
    """
    items: list[EvidenceItem] = []
    for chunk in chunks:
        content = chunk.content.strip()
        if len(content) < MIN_CHUNK_CHARS:
            continue
        heading = chunk.heading_path or ""
        title = f"{document.filename} · {heading}" if heading else document.filename
        items.append(
            EvidenceItem(
                kind=EvidenceKind.DOCUMENT_CHUNK,
                title=title[:300],
                snippet=snippet_of(content),
                locator=EvidenceLocator(
                    section=heading or None,
                    page=chunk.page_no,
                    char_start=chunk.char_start,
                    char_end=chunk.char_end,
                ),
                source_authority=SourceAuthority.UPLOADED_DOCUMENT,
                confidence=0.0,
                occurred_at=document.created_at,
                document_chunk_id=chunk.id,
                content_hash=content_hash_of(document, chunk),
                metadata={
                    "documentId": str(document.id),
                    "chunkIndex": chunk.chunk_index,
                    "filename": document.filename,
                    "tokenCount": chunk.token_count,
                },
            )
        )
    return items


def content_hash_of(document: Document, chunk: DocumentChunk) -> str:
    """Stable hash for de-duplication: the text plus where it came from.

    Includes the chunk index, because the same paragraph appearing twice in one document
    is two locators and a reviewer following a citation must land on the right one.
    """
    payload = f"{document.id}:{chunk.chunk_index}:{chunk.content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class EvidenceService:
    """Analysis and graph reads for one user."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._evidence = EvidenceRepository(session)

    # ── analysis ─────────────────────────────────────────────────────────────

    async def analyse_document(self, document: Document, *, user: User) -> EvidenceAnalysisResult:
        """Build the graph from one document's chunks and persist it.

        Raises:
            ValueError: the document holds no stored text, so there is nothing to cite.
        """
        chunks = await self._chunks_of(document)
        if not chunks:
            detail = (
                " raw-text retention is disabled for this account"
                if document.raw_text is None
                else " it has not been parsed yet"
            )
            raise ValueError(f"{document.filename} has nothing to analyse:{detail}")

        items = evidence_from_chunks(document, chunks)
        if not items:
            raise ValueError(f"{document.filename} has no chunk long enough to cite")

        profile = await self._profile_of(user)
        result = build_evidence_graph(profile=profile, evidence=items)

        created, updated = await self._persist_evidence(user_id=user.id, result=result)
        links = await self._persist_links(user_id=user.id, result=result)
        await self._session.flush()

        return EvidenceAnalysisResult(
            document_id=document.id,
            evidence_created=created,
            evidence_updated=updated,
            links_written=links,
            skill_count=len(result.skill_evidence),
            nodes=result.node_count,
            edges=result.edge_count,
            mean_confidence=result.mean_confidence,
            warnings=list(result.warnings),
        )

    async def _chunks_of(self, document: Document) -> list[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document.id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list((await self._session.scalars(statement)).all())

    async def _profile_of(self, user: User) -> CandidateProfile:
        """The stored profile, assembled from rows.

        Every consumer reads the profile the same way — this service, the match engine and the
        dashboard all go through ``ProfileService.load`` — so a project the candidate added is
        both a node in the graph and an input to the project match dimension, rather than one
        or the other.
        """
        return await ProfileService(self._session).load(user)

    async def _persist_evidence(
        self, *, user_id: UUID, result: GraphBuildResult
    ) -> tuple[int, int]:
        known = await self._evidence.content_hashes(user_id=user_id, kind="document_chunk")
        rows = [_row_for(user_id, item) for item in result.evidence]
        updated = sum(1 for row in rows if row["content_hash"] in known)
        stored = await self._evidence.upsert_many(rows)
        self._remap_engine_ids(stored, result)
        return len(stored) - updated, updated

    @staticmethod
    def _remap_engine_ids(stored: Sequence[Evidence], result: GraphBuildResult) -> None:
        """Replace the engine's derived ids with the stored primary keys, everywhere.

        The core assigns each evidence item an id derived from its content
        (``GRAPH_NAMESPACE``), and writes its links against that id. The database generates
        a different id on insert, so the links have to be rewritten too — remapping the
        items alone would leave every edge pointing at a node no query can resolve.

        The content hash is the join key, and it is exactly the key the engine used to
        derive its ids, so the mapping is exact rather than heuristic.
        """
        by_hash = {row.content_hash: row.id for row in stored}
        remap: dict[UUID, UUID] = {}
        for item in result.evidence:
            replacement = by_hash.get(item.content_hash)
            if item.id is not None and replacement is not None and replacement != item.id:
                remap[item.id] = replacement
        if not remap:
            return

        for item in result.evidence:
            if item.id in remap:
                item.id = remap[item.id]
        for link in result.links:
            link.from_id = remap.get(link.from_id, link.from_id)
            link.to_id = remap.get(link.to_id, link.to_id)
        for edge in result.edges:
            edge.source = remap.get(edge.source, edge.source)
            edge.target = remap.get(edge.target, edge.target)

    async def _persist_links(self, *, user_id: UUID, result: GraphBuildResult) -> int:
        rows = [
            {
                "user_id": user_id,
                "from_type": link.from_type.value,
                "from_id": link.from_id,
                "to_type": link.to_type.value,
                "to_id": link.to_id,
                "relation": link.relation.value,
                "weight": float(link.weight),
                "confidence": float(link.confidence) if link.confidence is not None else None,
                "rationale": link.rationale,
            }
            for link in result.links
        ]
        return await self._evidence.insert_links(rows)

    # ── reads ────────────────────────────────────────────────────────────────

    async def nodes_and_edges(self, *, user: User) -> tuple[list[GraphNode], list[GraphEdge], int]:
        """Rebuild the graph from stored rows, for the query layer to slice.

        Returns ``(nodes, edges, unresolved_count)``. The count is reported rather than
        hidden: an edge whose endpoint has no table yet (a project, before §2.2 exists)
        still gets a placeholder node, and the UI should be able to say so.
        """
        evidence_rows = await self._evidence.list_for_user(user_id=user.id, limit=2000)
        nodes: dict[UUID, GraphNode] = {
            row.id: GraphNode(
                id=row.id,
                type=node_type_of(row.kind),
                label=row.title,
                confidence=float(row.confidence),
                meta={"kind": row.kind, "locator": row.locator, **row.metadata_},
            )
            for row in evidence_rows
        }

        skills = (await self._session.scalars(select(Skill).where(Skill.is_active))).all()
        for skill in skills:
            identifier = node_id(GraphNodeType.SKILL, skill.canonical_id)
            nodes[identifier] = GraphNode(
                id=identifier,
                type=GraphNodeType.SKILL,
                label=skill.display_name,
                group=skill.canonical_id,
                meta={"category": skill.category, "canonicalId": skill.canonical_id},
            )

        profile_row = await self._session.scalar(select(Profile).where(Profile.user_id == user.id))
        slug = (
            profile_row.slug
            if profile_row is not None and profile_row.slug
            else f"user-{user.id.hex[:8]}"
        )
        candidate_id = node_id(GraphNodeType.CANDIDATE, slug)
        nodes[candidate_id] = GraphNode(
            id=candidate_id,
            type=GraphNodeType.CANDIDATE,
            label=(
                profile_row.headline
                if profile_row is not None and profile_row.headline
                else user.display_name
            ),
            meta={"slug": slug},
        )
        # Entity nodes, recomputed with the same keys the builder used. Without them every
        # candidate->project edge ends in a placeholder node.
        nodes.update(await ProfileService(self._session).graph_nodes(user))

        links = await self._evidence.list_links(user_id=user.id)
        edges: list[GraphEdge] = []
        unresolved: set[UUID] = set()
        for link in links:
            for endpoint, endpoint_type in (
                (link.from_id, link.from_type),
                (link.to_id, link.to_type),
            ):
                if endpoint in nodes:
                    continue
                unresolved.add(endpoint)
                nodes[endpoint] = GraphNode(
                    id=endpoint,
                    type=_node_type(endpoint_type),
                    label=f"{endpoint_type}:{str(endpoint)[:8]}",
                    meta={"unresolved": True, "nodeType": endpoint_type},
                )
            edges.append(
                GraphEdge(
                    id=str(link.id),
                    source=link.from_id,
                    target=link.to_id,
                    relation=EvidenceRelation(link.relation),
                    confidence=float(link.confidence) if link.confidence is not None else None,
                    rationale=link.rationale,
                )
            )

        return list(nodes.values()), edges, len(unresolved)

    # ── single-item operations ───────────────────────────────────────────────

    async def add_manual(
        self,
        *,
        user: User,
        title: str,
        snippet: str = "",
        locator: EvidenceLocator | None = None,
        occurred_at: datetime | None = None,
    ) -> Evidence:
        """Store evidence the candidate typed themselves (``evidence.kind = 'manual'``).

        Confidence is *computed*, never accepted from the caller. A manual entry is the
        weakest tier that still counts, and letting a client choose its own confidence
        would make the number meaningless exactly where the product claims it is not.
        """
        resolved_locator = locator or EvidenceLocator()
        breakdown = compute_confidence(
            kind=EvidenceKind.MANUAL,
            occurred_at=occurred_at,
            locator=resolved_locator,
            independent_sources=1,
            extraction_method="user_corrected",
        )
        payload = f"{title}:{snippet}:{resolved_locator.model_dump_json()}"
        row = Evidence(
            user_id=user.id,
            kind=EvidenceKind.MANUAL.value,
            title=title[:300],
            snippet=snippet[:2000],
            locator=resolved_locator.model_dump(exclude_none=True),
            source_authority=float(breakdown.inputs.source_authority),
            specificity=float(breakdown.inputs.specificity),
            extraction_quality=float(breakdown.inputs.extraction_quality),
            recency_score=float(breakdown.inputs.recency),
            corroboration_count=1,
            confidence=float(breakdown.score),
            occurred_at=occurred_at,
            content_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            metadata_={"source": "manual"},
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, evidence_id: UUID, *, user: User) -> Evidence | None:
        return await self._evidence.get(evidence_id, user_id=user.id)

    async def list_for_user(
        self,
        *,
        user: User,
        kind: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> Sequence[Evidence]:
        return await self._evidence.list_for_user(
            user_id=user.id, kind=kind, min_confidence=min_confidence, limit=limit
        )

    async def delete(self, evidence: Evidence) -> None:
        await self._evidence.delete(evidence)

    async def traces_for(self, evidence: Evidence, *, user: User) -> list[EvidenceLinkRow]:
        """Backward provenance: who cites this evidence."""
        links = await self._evidence.links_for(evidence.id, user_id=user.id)
        return [link for link in links if link.to_id == evidence.id]


def _row_for(user_id: UUID, item: EvidenceItem) -> dict[str, Any]:
    """Map an engine-produced item onto the ``evidence`` columns.

    The five factors are read from the builder's breakdown rather than recomputed: the
    breakdown *is* the record of why the score is what it is, and the database CHECK
    requires the stored inputs to reproduce the stored confidence.
    """
    return {
        "user_id": user_id,
        "kind": item.kind.value,
        "title": item.title,
        "snippet": item.snippet,
        "locator": item.locator.model_dump(exclude_none=True),
        "source_authority": _factor(item, "source_authority"),
        "specificity": _factor(item, "specificity"),
        "extraction_quality": _factor(item, "extraction_quality"),
        "recency_score": _factor(item, "recency"),
        "corroboration_count": item.corroboration_count,
        "confidence": float(item.confidence),
        "occurred_at": item.occurred_at,
        "document_chunk_id": item.document_chunk_id,
        "content_hash": item.content_hash,
        "metadata_": dict(item.metadata),
    }


def _factor(item: EvidenceItem, name: str) -> float:
    """One confidence factor, from the breakdown the builder produced."""
    breakdown = item.breakdown
    if breakdown is None:  # pragma: no cover - the builder always sets it
        return 0.0
    return float(getattr(breakdown.inputs, name, 0.0))


def _node_type(value: str) -> GraphNodeType:
    try:
        return GraphNodeType(value)
    except ValueError:
        return GraphNodeType.CLAIM
