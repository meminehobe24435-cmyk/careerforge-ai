"""Evidence graph: construction, traversal and confidence assignment.

The graph is stored as an adjacency structure (``evidence`` + ``evidence_links``)
rather than in a graph database — see ADR-005 for the reasoning and the accepted
trade-offs.

Public surface::

    build_evidence_graph(profile=..., evidence=...)  # construct
    extract_subgraph(nodes, edges, focus="skill:stm32")
    trace_claim(nodes, edges, claim_node_id)  # why this claim is allowed
    graph_stats(nodes, edges)
    node_id(GraphNodeType.SKILL, "stm32")  # stable ids
"""

from __future__ import annotations

from careerforge_ai.graph.builder import (
    GRAPH_NAMESPACE,
    GraphBuildResult,
    build_evidence_graph,
    node_id,
)
from careerforge_ai.graph.query import (
    MAX_DEPTH,
    adjacency_summary,
    extract_subgraph,
    graph_stats,
    resolve_focus,
    trace_claim,
)

__all__ = [
    "GRAPH_NAMESPACE",
    "MAX_DEPTH",
    "GraphBuildResult",
    "adjacency_summary",
    "build_evidence_graph",
    "extract_subgraph",
    "graph_stats",
    "node_id",
    "resolve_focus",
    "trace_claim",
]
