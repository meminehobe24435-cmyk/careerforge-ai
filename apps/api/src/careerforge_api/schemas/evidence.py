"""Evidence models: ``/evidence``, ``/evidence-graph`` (``docs/API.md`` §2.5).

The confidence block is always returned **with its factors**. A bare number invites the
question "0.72 out of what?", and the answer has to be in the payload rather than in a
document: the five factors, the corroboration count and the recomputed value, so a client
can show the arithmetic instead of asking the reader to trust it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AnalysisResponse",
    "EvidenceDetail",
    "EvidenceGraphResponse",
    "EvidenceListResponse",
    "EvidenceResponse",
    "GraphEdgeResponse",
    "GraphNodeResponse",
    "LocatorResponse",
    "ManualEvidenceRequest",
    "TraceResponse",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ConfidenceFactors(_CamelModel):
    """The inputs behind one confidence score (``docs/PRD.md`` §4)."""

    source_authority: float = Field(alias="sourceAuthority")
    recency: float = Field(default=0.0)
    specificity: float = 0.0
    corroboration: float = 0.0
    extraction_quality: float = Field(default=0.0, alias="extractionQuality")
    corroboration_sources: int = Field(default=1, alias="corroborationSources")
    #: The formula applied to these factors. Equal to ``confidence`` unless something
    #: wrote a row the database should have rejected — a self-check the UI can surface.
    recomputed: float = 0.0
    formula_version: str = Field(default="confidence@1.0.0", alias="formulaVersion")


class LocatorResponse(_CamelModel):
    """Where the evidence lives, in the API's camelCase vocabulary.

    Modelled explicitly rather than passed through as the stored dict: the store keeps
    ``char_start`` while every other field on the wire is camelCase, and a client that had
    to special-case one nested object would be right to call that a bug.
    """

    path: str | None = None
    line: int | None = None
    url: str | None = None
    sha: str | None = None
    page: int | None = None
    char_start: int | None = Field(default=None, alias="charStart")
    char_end: int | None = Field(default=None, alias="charEnd")
    section: str | None = None

    @classmethod
    def from_stored(cls, stored: dict[str, Any] | None) -> LocatorResponse:
        """Accept the stored snake_case keys, which is what the database holds."""
        value = dict(stored or {})
        return cls(
            path=value.get("path"),
            line=value.get("line"),
            url=value.get("url"),
            sha=value.get("sha"),
            page=value.get("page"),
            char_start=value.get("char_start", value.get("charStart")),
            char_end=value.get("char_end", value.get("charEnd")),
            section=value.get("section"),
        )


class EvidenceResponse(_CamelModel):
    """One piece of evidence, with everything needed to judge and to check it."""

    id: str
    kind: str
    title: str
    snippet: str = ""
    locator: LocatorResponse = Field(default_factory=LocatorResponse)
    confidence: float
    factors: ConfidenceFactors | None = None
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")
    document_chunk_id: str | None = Field(default=None, alias="documentChunkId")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_row(cls, row: Any) -> Self:
        """Project an ORM row. ``Self`` so ``EvidenceDetail.from_row`` stays a detail."""
        corroboration = min(1.0, 0.4 + 0.2 * float(row.corroboration_count))
        return cls(
            id=str(row.id),
            kind=row.kind,
            title=row.title,
            snippet=row.snippet,
            locator=LocatorResponse.from_stored(row.locator),
            confidence=float(row.confidence),
            factors=ConfidenceFactors(
                source_authority=float(row.source_authority),
                recency=float(row.recency_score),
                specificity=float(row.specificity),
                corroboration=round(corroboration, 3),
                extraction_quality=float(row.extraction_quality),
                corroboration_sources=int(row.corroboration_count),
                recomputed=row.recomputed_confidence,
            ),
            occurred_at=row.occurred_at,
            document_chunk_id=str(row.document_chunk_id) if row.document_chunk_id else None,
            metadata=dict(row.metadata_ or {}),
        )


class EvidenceDetail(EvidenceResponse):
    """``GET /evidence/{id}`` — adds the reverse provenance summary."""

    cited_by_count: int = Field(default=0, alias="citedByCount")


class EvidenceListResponse(_CamelModel):
    items: list[EvidenceResponse] = Field(default_factory=list)
    total: int = 0


class CitedByEntry(_CamelModel):
    """One edge that points at this evidence, i.e. who relies on it."""

    relation: str
    from_type: str = Field(alias="fromType")
    from_id: str = Field(alias="fromId")
    rationale: str | None = None


class TraceResponse(_CamelModel):
    """``GET /evidence/{id}/trace`` — reverse provenance."""

    evidence_id: str = Field(alias="evidenceId")
    cited_by: list[CitedByEntry] = Field(default_factory=list, alias="citedBy")


class GraphNodeResponse(_CamelModel):
    id: str
    type: str
    label: str
    confidence: float | None = None
    group: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeResponse(_CamelModel):
    id: str
    source: str
    target: str
    relation: str
    confidence: float | None = None
    rationale: str | None = None


class EvidenceGraphResponse(_CamelModel):
    """``GET /evidence-graph`` — a depth-limited slice, with the stats strip.

    ``stats`` describes **what this response contains** and ``totals`` describes the whole
    graph. Computing both from the whole graph put "129 nodes" above a ten-node canvas;
    keeping them apart lets the UI say "showing 10 of 129", which is the honest version.
    """

    nodes: list[GraphNodeResponse] = Field(default_factory=list)
    edges: list[GraphEdgeResponse] = Field(default_factory=list)
    focus: str | None = None
    depth: int = 2
    truncated: bool = False
    node_count: int = Field(default=0, alias="nodeCount")
    edge_count: int = Field(default=0, alias="edgeCount")
    stats: dict[str, Any] = Field(default_factory=dict)
    totals: dict[str, Any] = Field(default_factory=dict)
    #: Edges whose endpoint has no table yet (projects, before §2.2 exists). Reported
    #: rather than hidden, so the UI can say "1 node not yet resolvable".
    unresolved_node_count: int = Field(default=0, alias="unresolvedNodeCount")


class AnalysisResponse(_CamelModel):
    """``POST /documents/{id}/analyze`` — what one pass produced."""

    document_id: str = Field(alias="documentId")
    evidence_created: int = Field(default=0, alias="evidenceCreated")
    evidence_updated: int = Field(default=0, alias="evidenceUpdated")
    links_written: int = Field(default=0, alias="linksWritten")
    skill_count: int = Field(default=0, alias="skillCount")
    node_count: int = Field(default=0, alias="nodeCount")
    edge_count: int = Field(default=0, alias="edgeCount")
    mean_confidence: float = Field(default=0.0, alias="meanConfidence")
    warnings: list[str] = Field(default_factory=list)


class ManualEvidenceRequest(_CamelModel):
    """``POST /evidence`` body.

    No confidence field: the server computes it from the same five factors as every other
    piece of evidence. ``occurred_at`` is accepted because recency is one of those factors
    and only the candidate knows when the work happened.

    Unlike the response models this one **forbids** unknown fields. A client that sends
    ``confidence`` must be told it is not accepted; silently dropping it would let someone
    believe they had set a score that the server computed instead.
    """

    model_config = ConfigDict(populate_by_name=True, from_attributes=True, extra="forbid")

    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(default="", max_length=2000)
    locator: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = Field(default=None, alias="occurredAt")

    @property
    def evidence_locator(self) -> Any:
        from careerforge_ai.schemas.evidence import EvidenceLocator

        return EvidenceLocator.model_validate(self.locator)
