"""The result object a graph build returns.

Separated from the builder so that both the builder and the job layer can refer to
it without importing each other — a plain type dependency, no logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from careerforge_ai.schemas.common import EvidenceRelation
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLink, GraphEdge, GraphNode

__all__ = ["GraphBuildResult"]


@dataclass(slots=True)
class GraphBuildResult:
    """Everything one build produced, ready to persist or serialise."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    links: list[EvidenceLink] = field(default_factory=list)
    #: canonical skill id → number of independent sources supporting it
    skill_corroboration: dict[str, int] = field(default_factory=dict)
    #: canonical skill id → evidence ids, used by the match engine
    skill_evidence: dict[str, list[UUID]] = field(default_factory=dict)
    #: canonical skill id → mean confidence of its evidence
    skill_confidence: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def mean_confidence(self) -> float:
        if not self.evidence:
            return 0.0
        return round(sum(item.confidence for item in self.evidence) / len(self.evidence), 4)

    @property
    def orphan_evidence(self) -> list[EvidenceItem]:
        """Evidence that supports nothing — a signal that extraction over-reached.

        "Supports nothing" means no ``EVIDENCED_BY`` link points at it, which is the
        only link that says a skill is backed by this material.
        """
        linked = {
            link.to_id for link in self.links if link.relation is EvidenceRelation.EVIDENCED_BY
        }
        return [item for item in self.evidence if item.id is not None and item.id not in linked]
