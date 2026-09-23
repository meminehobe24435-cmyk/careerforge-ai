"""Evidence graph queries: subgraph extraction, focus resolution and provenance tracing.

The API never ships the whole graph. A single candidate's graph is small, but the
response size and the React Flow render cost are both driven by node count, so the
query layer exists to answer "the two hops around this skill" rather than "give me
everything".

Traversal is undirected for exploration (a user clicking a file wants to see the
project that owns it) but provenance tracing is directional on purpose: a claim is
justified by the evidence that *supports* it, not by anything reachable from it.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from uuid import UUID

from careerforge_ai.schemas.common import EvidenceRelation, GraphNodeType
from careerforge_ai.schemas.evidence import (
    EvidenceGraph,
    GraphEdge,
    GraphNode,
    GraphQuery,
)

__all__ = [
    "resolve_focus",
    "extract_subgraph",
    "trace_claim",
    "graph_stats",
    "MAX_DEPTH",
]

MAX_DEPTH = 4

#: Relations that justify a claim, in the order a human reads them:
#: the claim is supported by evidence, which originates from a source.
_PROVENANCE_RELATIONS = frozenset(
    {
        EvidenceRelation.SUPPORTS,
        EvidenceRelation.EVIDENCED_BY,
        EvidenceRelation.DERIVED_FROM,
        EvidenceRelation.DEMONSTRATES,
    }
)


def resolve_focus(nodes: Sequence[GraphNode], focus: str | None) -> UUID | None:
    """Resolve a focus reference like ``skill:stm32``, ``project:<uuid>`` or a raw id.

    Returns ``None`` rather than raising when nothing matches: a stale bookmark is
    a normal event, and the caller's correct response is to fall back to the
    default view rather than to fail the request.
    """
    if not focus:
        return None
    reference = focus.strip()

    if ":" in reference:
        kind, _, key = reference.partition(":")
        kind = kind.strip().lower()
        key = key.strip()
        for node in nodes:
            if node.type.value != kind:
                continue
            if str(node.id) == key or node.label == key or node.group == key:
                return node.id
        return None

    try:
        candidate = UUID(reference)
    except ValueError:
        for node in nodes:
            if node.label == reference or node.group == reference:
                return node.id
        return None
    return next((node.id for node in nodes if node.id == candidate), None)


def _adjacency(edges: Sequence[GraphEdge]) -> dict[UUID, list[tuple[UUID, GraphEdge]]]:
    adjacency: dict[UUID, list[tuple[UUID, GraphEdge]]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source, []).append((edge.target, edge))
        adjacency.setdefault(edge.target, []).append((edge.source, edge))
    return adjacency


def extract_subgraph(
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge],
    *,
    query: GraphQuery | None = None,
    focus: str | None = None,
    depth: int = 2,
    node_types: Iterable[GraphNodeType] | None = None,
    min_confidence: float = 0.0,
    limit: int = 500,
    include_orphans: bool = False,
) -> EvidenceGraph:
    """Extract a depth-limited neighbourhood around ``focus``.

    Without a focus the whole (filtered) graph is returned, which is what the
    initial page load wants. Filters are applied after traversal so that a focus
    node is never dropped by its own filter — clicking a low-confidence skill
    should still show you that skill and its neighbourhood.
    """
    settings = query
    effective_focus = settings.focus if settings else focus
    effective_depth = min(settings.depth if settings else depth, MAX_DEPTH)
    effective_types = set(node_types or (settings.node_types if settings else []) or [])
    effective_min = settings.min_confidence if settings else min_confidence
    effective_limit = settings.limit if settings else limit

    by_id: dict[UUID, GraphNode] = {node.id: node for node in nodes}
    adjacency = _adjacency(edges)

    focus_id = resolve_focus(nodes, effective_focus)
    if focus_id is not None:
        keep: set[UUID] = {focus_id}
        frontier: deque[tuple[UUID, int]] = deque([(focus_id, 0)])
        while frontier:
            current, current_depth = frontier.popleft()
            if current_depth >= effective_depth:
                continue
            for neighbour, _edge in adjacency.get(current, ()):
                if neighbour in keep:
                    continue
                keep.add(neighbour)
                frontier.append((neighbour, current_depth + 1))
        selected = [by_id[node_id] for node_id in keep if node_id in by_id]
    else:
        selected = list(nodes)

    filtered: list[GraphNode] = []
    for node in selected:
        if node.id == focus_id:
            filtered.append(node)
            continue
        if effective_types and node.type not in effective_types:
            continue
        if node.confidence is not None and node.confidence < effective_min:
            continue
        filtered.append(node)

    if not include_orphans:
        connected = {endpoint for edge in edges for endpoint in (edge.source, edge.target)}
        filtered = [node for node in filtered if node.id in connected or node.id == focus_id]

    truncated = len(filtered) > effective_limit
    if truncated:
        # Keep the highest-confidence nodes, but never drop the focus.
        ordered = sorted(
            filtered,
            key=lambda node: (
                node.id != focus_id,
                -(node.confidence or 0.0),
                node.label,
            ),
        )
        filtered = ordered[:effective_limit]

    kept_ids = {node.id for node in filtered}
    kept_edges = [edge for edge in edges if edge.source in kept_ids and edge.target in kept_ids]

    return EvidenceGraph(
        nodes=filtered,
        edges=kept_edges,
        focus=effective_focus,
        depth=effective_depth,
        truncated=truncated,
        node_count=len(filtered),
        edge_count=len(kept_edges),
    )


def trace_claim(
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge],
    claim_node_id: UUID,
    *,
    max_paths: int = 12,
) -> list[list[GraphEdge]]:
    """Return the provenance paths that justify a claim.

    Walks *backwards* along justification relations only, so the result contains
    "because of this" rather than "related to this". Cycles are cut by tracking the
    nodes already on the current path.
    """
    by_id = {node.id: node for node in nodes}
    if claim_node_id not in by_id:
        return []

    incoming: dict[UUID, list[GraphEdge]] = {}
    for edge in edges:
        if edge.relation in _PROVENANCE_RELATIONS:
            incoming.setdefault(edge.target, []).append(edge)

    paths: list[list[GraphEdge]] = []
    stack: list[tuple[UUID, list[GraphEdge], frozenset[UUID]]] = [
        (claim_node_id, [], frozenset({claim_node_id}))
    ]

    while stack and len(paths) < max_paths:
        current, trail, seen = stack.pop()
        parents = incoming.get(current, [])
        if not parents:
            if trail:
                paths.append(trail)
            continue
        for edge in parents:
            if edge.source in seen:
                continue
            stack.append((edge.source, [edge, *trail], seen | {edge.source}))

    # Shortest justification first: a claim backed by a direct file link is
    # easier to defend than one that needs three hops.
    paths.sort(key=len)
    return paths[:max_paths]


def graph_stats(nodes: Sequence[GraphNode], edges: Sequence[GraphEdge]) -> dict[str, object]:
    """Counts used by the summary strip on the graph page."""
    by_type: dict[str, int] = {}
    confidences: list[float] = []
    for node in nodes:
        by_type[node.type.value] = by_type.get(node.type.value, 0) + 1
        if node.confidence is not None:
            confidences.append(node.confidence)

    by_relation: dict[str, int] = {}
    for edge in edges:
        by_relation[edge.relation.value] = by_relation.get(edge.relation.value, 0) + 1

    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "nodes_by_type": dict(sorted(by_type.items())),
        "edges_by_relation": dict(sorted(by_relation.items())),
        "mean_confidence": (round(sum(confidences) / len(confidences), 4) if confidences else 0.0),
        "high_confidence": sum(1 for value in confidences if value >= 0.75),
        "low_confidence": sum(1 for value in confidences if value < 0.45),
    }


def adjacency_summary(edges: Sequence[GraphEdge]) -> Mapping[str, int]:
    """Degree histogram, used to spot a graph that is really a star or a chain."""
    degree: dict[UUID, int] = {}
    for edge in edges:
        degree[edge.source] = degree.get(edge.source, 0) + 1
        degree[edge.target] = degree.get(edge.target, 0) + 1
    buckets = {"0": 0, "1": 0, "2-3": 0, "4-9": 0, "10+": 0}
    for value in degree.values():
        if value == 0:
            buckets["0"] += 1
        elif value == 1:
            buckets["1"] += 1
        elif value <= 3:
            buckets["2-3"] += 1
        elif value <= 9:
            buckets["4-9"] += 1
        else:
            buckets["10+"] += 1
    return buckets
