"""Stable node identity for the evidence graph."""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

from careerforge_ai.schemas.common import GraphNodeType

__all__ = ["GRAPH_NAMESPACE", "node_id"]

#: Namespace for every derived node id. Changing it invalidates stored graphs,
#: which is the correct behaviour: it is a schema change.
GRAPH_NAMESPACE = uuid5(NAMESPACE_URL, "careerforge.ai/evidence-graph")


def node_id(kind: GraphNodeType | str, key: str) -> UUID:
    """Stable node id from a kind and a human-readable key.

    Deterministic on purpose: the same profile must always produce the same graph,
    so that two builds can be diffed and a test can assert a specific edge exists.
    """
    kind_value = kind.value if isinstance(kind, GraphNodeType) else str(kind)
    return uuid5(GRAPH_NAMESPACE, f"{kind_value}:{key}")
