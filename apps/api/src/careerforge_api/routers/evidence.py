"""``/evidence`` and ``/evidence-graph`` — the product's core surface (``docs/API.md`` §2.5).

Two endpoints carry the differentiator. ``GET /evidence-graph`` returns a depth-limited
neighbourhood, so a reviewer can start from a skill and walk to the file or the sentence
that proves it. ``GET /evidence/{id}/trace`` walks the other way: which conclusions rest on
this piece of evidence.

Both read the *derived* graph (see ``services/evidence_service.py``) rather than a stored
node table, so a skill node always reflects the current skill dictionary and a candidate
node always reflects the current profile.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from careerforge_ai.graph import extract_subgraph, graph_stats
from careerforge_ai.schemas.common import GraphNodeType
from careerforge_ai.schemas.evidence import GraphQuery
from careerforge_api.core.errors import ConflictError, NotFoundError, ValidationError
from careerforge_api.deps import CurrentUser, DbSession
from careerforge_api.models.document import Document
from careerforge_api.models.evidence import EVIDENCE_KINDS
from careerforge_api.schemas.evidence import (
    AnalysisResponse,
    CitedByEntry,
    EvidenceCreateResponse,
    EvidenceDetail,
    EvidenceGraphResponse,
    EvidenceListResponse,
    EvidenceResponse,
    GraphEdgeResponse,
    GraphNodeResponse,
    ManualEvidenceRequest,
    TraceResponse,
)
from careerforge_api.services.document_service import DocumentService
from careerforge_api.services.evidence_service import EvidenceService

__all__ = ["router"]

router = APIRouter(tags=["evidence"])

MAX_LIST_LIMIT = 200


def _parse_uuid(raw: str, *, what: str) -> UUID:
    """A malformed id is a ``404``: it is simply an id that does not exist."""
    try:
        return UUID(raw)
    except ValueError as exc:
        raise NotFoundError(f"{what} not found") from exc


def _parse_types(raw: str | None) -> list[GraphNodeType]:
    if not raw:
        return []
    parsed: list[GraphNodeType] = []
    for name in raw.split(","):
        candidate = name.strip()
        if not candidate:
            continue
        try:
            parsed.append(GraphNodeType(candidate))
        except ValueError as exc:
            raise ValidationError(
                f"unknown node type '{candidate}'",
                details=[
                    {
                        "field": "types",
                        "issue": "not_allowed",
                        "message": f"allowed: {', '.join(t.value for t in GraphNodeType)}",
                    }
                ],
            ) from exc
    return parsed


@router.get("/evidence", summary="List evidence")
async def list_evidence(
    session: DbSession,
    user: CurrentUser,
    kind: Annotated[str | None, Query(description="Filter by evidence kind")] = None,
    min_confidence: Annotated[float, Query(alias="minConfidence", ge=0, le=1)] = 0.0,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = 100,
) -> EvidenceListResponse:
    if kind is not None and kind not in EVIDENCE_KINDS:
        raise ValidationError(
            f"unknown evidence kind '{kind}'",
            details=[
                {
                    "field": "kind",
                    "issue": "not_allowed",
                    "message": f"allowed: {', '.join(EVIDENCE_KINDS)}",
                }
            ],
        )
    service = EvidenceService(session)
    rows = await service.list_for_user(
        user=user, kind=kind, min_confidence=min_confidence, limit=limit
    )
    return EvidenceListResponse(
        items=[EvidenceResponse.from_row(row) for row in rows], total=len(rows)
    )


@router.post(
    "/evidence",
    status_code=status.HTTP_201_CREATED,
    summary="Add evidence by hand (idempotent)",
)
async def create_evidence(
    payload: ManualEvidenceRequest,
    session: DbSession,
    user: CurrentUser,
    response: Response,
) -> EvidenceCreateResponse:
    """Manual evidence: something true that no upload contains (a shipped feature, an award).

    **Idempotent** (PHASE 14). ``evidence`` is unique on ``(user_id, kind, content_hash)``, and
    this endpoint used to insert blind: replaying the same payload was a ``500 INTERNAL_ERROR``
    on a request that had already succeeded. It is now ``get_or_create`` — ``201`` with
    ``created: true`` the first time, ``200`` with ``created: false`` and the stored row after
    that — because an ingestion pipeline is *expected* to replay and the honest answer to
    "store this" is the row that already holds it.

    Confidence is computed from the same five factors as everything else and can never be
    supplied by the client — a self-declared score would defeat the point of having one.
    """
    row, created = await EvidenceService(session).add_manual(
        user=user,
        title=payload.title,
        snippet=payload.snippet,
        locator=payload.evidence_locator,
        occurred_at=payload.occurred_at,
    )
    if not created:
        # The row exists already, so nothing was created. ``200`` is the honest status: a
        # repeated request that writes nothing is not a creation.
        response.status_code = status.HTTP_200_OK
    return EvidenceCreateResponse.project(row, created=created)


@router.get("/evidence/{evidence_id}", summary="Evidence detail")
async def get_evidence(evidence_id: str, session: DbSession, user: CurrentUser) -> EvidenceDetail:
    service = EvidenceService(session)
    row = await service.get(_parse_uuid(evidence_id, what="Evidence"), user=user)
    if row is None:
        raise NotFoundError("Evidence not found")
    traces = await service.traces_for(row, user=user)
    detail = EvidenceDetail.from_row(row)
    detail.cited_by_count = len(traces)
    return detail


@router.get("/evidence/{evidence_id}/trace", summary="Reverse provenance: who cites this")
async def trace_evidence(evidence_id: str, session: DbSession, user: CurrentUser) -> TraceResponse:
    service = EvidenceService(session)
    row = await service.get(_parse_uuid(evidence_id, what="Evidence"), user=user)
    if row is None:
        raise NotFoundError("Evidence not found")
    links = await service.traces_for(row, user=user)
    return TraceResponse(
        evidence_id=str(row.id),
        cited_by=[
            CitedByEntry(
                relation=link.relation,
                from_type=link.from_type,
                from_id=str(link.from_id),
                rationale=link.rationale,
            )
            for link in links
        ],
    )


@router.delete(
    "/evidence/{evidence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete evidence and every edge that references it",
)
async def delete_evidence(evidence_id: str, session: DbSession, user: CurrentUser) -> None:
    service = EvidenceService(session)
    row = await service.get(_parse_uuid(evidence_id, what="Evidence"), user=user)
    if row is None:
        raise NotFoundError("Evidence not found")
    await service.delete(row)


@router.get("/evidence-graph", summary="Evidence graph neighbourhood")
async def get_evidence_graph(
    session: DbSession,
    user: CurrentUser,
    focus: Annotated[str | None, Query(description="e.g. skill:stm32 or a node id")] = None,
    depth: Annotated[int, Query(ge=1, le=4)] = 2,
    types: Annotated[str | None, Query(description="Comma-separated node types")] = None,
    min_confidence: Annotated[float, Query(alias="minConfidence", ge=0, le=1)] = 0.0,
    limit: Annotated[int, Query(ge=10, le=2000)] = 500,
    include_orphans: Annotated[bool, Query(alias="includeOrphans")] = False,
) -> EvidenceGraphResponse:
    """A depth-limited slice of the graph.

    ``focus`` is resolved leniently: an unknown reference falls back to the whole graph
    rather than failing, because a stale bookmark is a normal event and the caller's
    correct response is to show something useful (see ``resolve_focus``).
    """
    service = EvidenceService(session)
    nodes, edges, unresolved = await service.nodes_and_edges(user=user)
    query = GraphQuery(
        focus=focus,
        depth=depth,
        node_types=_parse_types(types),
        min_confidence=min_confidence,
        limit=limit,
        include_orphans=include_orphans,
    )
    subgraph = extract_subgraph(nodes, edges, query=query)
    subgraph_by_id = {node.id: node for node in subgraph.nodes}
    subgraph_edges = list(subgraph.edges)
    return EvidenceGraphResponse(
        nodes=[
            GraphNodeResponse(
                id=str(node.id),
                type=node.type.value,
                label=node.label,
                confidence=float(node.confidence) if node.confidence is not None else None,
                group=node.group,
                meta=dict(node.meta),
            )
            for node in subgraph.nodes
        ],
        edges=[
            GraphEdgeResponse(
                id=edge.id,
                source=str(edge.source),
                target=str(edge.target),
                relation=edge.relation.value,
                confidence=float(edge.confidence) if edge.confidence is not None else None,
                rationale=edge.rationale,
            )
            for edge in subgraph_edges
        ],
        focus=subgraph.focus,
        depth=subgraph.depth,
        truncated=subgraph.truncated,
        node_count=subgraph.node_count,
        edge_count=subgraph.edge_count,
        # What the client actually received, so a summary strip cannot disagree with the
        # canvas it sits above.
        stats=dict(graph_stats(list(subgraph_by_id.values()), subgraph_edges)),
        # ... and the whole graph, for "showing 10 of 129".
        totals=dict(graph_stats(nodes, edges)),
        unresolved_node_count=unresolved,
    )


@router.post(
    "/documents/{document_id}/analyze",
    summary="Build evidence from a stored document",
)
async def analyze_document(
    document_id: str, session: DbSession, user: CurrentUser
) -> AnalysisResponse:
    """Turn a stored document's chunks into evidence, skill edges and confidence.

    **Synchronous**, unlike the upload that produced the document. This is a deliberate
    exception to the ``202`` convention: the work is deterministic, CPU-only and bounded by
    the number of chunks already in the database, so queueing it would add a poll
    round-trip to a sub-second operation. Anything that calls a model stays queued.

    Re-running it is idempotent — evidence de-duplicates on content and edges on their
    five-tuple — so it is safe to use as a "recompute" button.
    """
    documents = DocumentService(session)
    document: Document | None = await documents.get(
        _parse_uuid(document_id, what="Document"), user=user
    )
    if document is None:
        raise NotFoundError("Document not found")

    service = EvidenceService(session)
    try:
        result = await service.analyse_document(document, user=user)
    except ValueError as exc:
        # 409: the request is well-formed and the document exists, but its current state
        # (unparsed, or text not retained) makes the analysis impossible.
        raise ConflictError(str(exc)) from exc

    return AnalysisResponse(
        document_id=str(result.document_id),
        evidence_created=result.evidence_created,
        evidence_updated=result.evidence_updated,
        links_written=result.links_written,
        skill_count=result.skill_count,
        node_count=result.nodes,
        edge_count=result.edges,
        mean_confidence=result.mean_confidence,
        warnings=result.warnings,
    )
