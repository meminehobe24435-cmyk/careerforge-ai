"""Evidence graph schemas — the heart of the product.

An *evidence* is a locatable fragment of real material. A *link* is a typed,
directed relation between two graph entities. A *claim* is a sentence a
candidate wants on their resume; it is allowed there only when evidence
supports it.

Everything the UI needs to explain a number lives in these models — that is the
whole point of the product (Explainability > Black Box).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from careerforge_ai.schemas.common import (
    CFBaseModel,
    Confidence,
    EvidenceKind,
    EvidenceRelation,
    GraphNodeType,
    RetrievalChannel,
    SourceAuthority,
    StrictModel,
    Unit,
    utcnow,
)

__all__ = [
    "ConfidenceBreakdown",
    "ConfidenceInputs",
    "EvidenceCandidate",
    "EvidenceGraph",
    "EvidenceItem",
    "EvidenceLink",
    "EvidenceLocator",
    "GraphEdge",
    "GraphNode",
    "GraphQuery",
    "RetrievalHit",
    "RetrievalResult",
]


class EvidenceLocator(CFBaseModel):
    """Where exactly the evidence lives, so a human can go and check it."""

    path: str | None = Field(default=None, description="Repository-relative file path")
    line: int | None = Field(default=None, ge=1, description="1-based line number")
    url: str | None = Field(default=None, description="Human-checkable URL")
    sha: str | None = Field(default=None, description="Commit SHA")
    page: int | None = Field(default=None, ge=1, description="Page number in a document")
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    section: str | None = Field(default=None, description="Document section or heading path")

    @property
    def display(self) -> str:
        """Compact one-line rendering used in the UI."""
        if self.path:
            return f"{self.path}:{self.line}" if self.line else self.path
        if self.sha:
            return f"commit {self.sha[:7]}"
        if self.page:
            return f"page {self.page}"
        if self.section:
            return self.section
        return "—"


class ConfidenceInputs(CFBaseModel):
    """The five factors that feed the confidence formula (ADR-013)."""

    source_authority: Unit = Field(description="Authority score of the source tier")
    recency: Unit = Field(description="Time decay score; 0.6 when the date is unknown")
    specificity: Unit = Field(description="How precisely the evidence is locatable")
    corroboration: Unit = Field(description="Independent-source coverage")
    extraction_quality: Unit = Field(description="Reliability of the extraction method")

    #: Kept alongside the inputs so a stored score can be reproduced after the
    #: weights themselves change.
    weights: dict[str, float] = Field(default_factory=dict)
    formula_version: str = "confidence@1.0.0"
    corroboration_sources: int = Field(default=1, ge=0)


class ConfidenceBreakdown(CFBaseModel):
    """Inputs plus per-factor contributions — rendered as the meter in the Drawer."""

    inputs: ConfidenceInputs
    contributions: dict[str, float] = Field(
        default_factory=dict,
        description="weighted contribution of each factor, summing to ``score``",
    )
    score: Confidence
    formula_version: str = "confidence@1.0.0"

    def explanation(self) -> list[tuple[str, float, float]]:
        """``(factor, weight, contribution)`` triples ordered by impact."""
        rows = [
            (name, self.inputs.weights.get(name, 0.0), value)
            for name, value in self.contributions.items()
        ]
        return sorted(rows, key=lambda row: row[2], reverse=True)


class EvidenceItem(CFBaseModel):
    """A single piece of evidence stored in the graph."""

    id: UUID | None = None
    kind: EvidenceKind
    title: str = Field(min_length=1, max_length=300)
    snippet: str = Field(default="", max_length=2000)
    locator: EvidenceLocator = Field(default_factory=EvidenceLocator)

    confidence: Confidence
    breakdown: ConfidenceBreakdown | None = None

    source_authority: SourceAuthority = SourceAuthority.RESUME_SELF_REPORT
    occurred_at: datetime | None = None
    corroboration_count: int = Field(default=1, ge=0)

    # Polymorphic provenance — at most one is populated.
    document_chunk_id: UUID | None = None
    repo_file_id: UUID | None = None
    repo_commit_id: UUID | None = None

    content_hash: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"{self.kind.value}:{self.title}"


class EvidenceLink(CFBaseModel):
    """A typed edge in the evidence graph."""

    id: UUID | None = None
    from_type: GraphNodeType
    from_id: UUID
    to_type: GraphNodeType
    to_id: UUID
    relation: EvidenceRelation
    weight: Unit = 1.0
    confidence: Confidence | None = None
    rationale: str | None = Field(
        default=None,
        description="Why this edge exists — shown to the user, never invented silently",
    )


class GraphNode(CFBaseModel):
    id: UUID
    type: GraphNodeType
    label: str
    confidence: Confidence | None = None
    group: str | None = Field(default=None, description="Skill id or project id used for filtering")
    meta: dict[str, object] = Field(default_factory=dict)


class GraphEdge(CFBaseModel):
    id: str
    source: UUID
    target: UUID
    relation: EvidenceRelation
    confidence: Confidence | None = None
    rationale: str | None = None


class EvidenceGraph(CFBaseModel):
    """A serialised subgraph, ready for the React Flow canvas."""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    focus: str | None = None
    depth: int = Field(default=2, ge=1, le=4)
    truncated: bool = False
    node_count: int = 0
    edge_count: int = 0
    generated_at: datetime = Field(default_factory=utcnow)


class GraphQuery(CFBaseModel):
    """Parameters accepted by ``GET /evidence-graph``."""

    focus: str | None = Field(
        default=None,
        description="Node reference such as ``skill:stm32``, ``project:<uuid>`` or ``claim:<uuid>``",
    )
    depth: int = Field(default=2, ge=1, le=4)
    node_types: list[GraphNodeType] = Field(default_factory=list)
    min_confidence: Confidence = 0.0
    limit: int = Field(default=500, ge=10, le=2000)
    include_orphans: bool = False
    since: datetime | None = None


class RetrievalHit(CFBaseModel):
    """One retrieved piece of evidence, with its provenance for explainability."""

    evidence_id: UUID
    title: str
    kind: EvidenceKind
    snippet: str = ""
    locator: EvidenceLocator = Field(default_factory=EvidenceLocator)
    confidence: Confidence = 0.0

    relevance: Confidence
    channel: RetrievalChannel = RetrievalChannel.SEMANTIC
    semantic_rank: int | None = None
    keyword_rank: int | None = None
    fused_score: float = 0.0


class RetrievalResult(CFBaseModel):
    """Result of a hybrid retrieval, including per-channel diagnostics."""

    query: str
    hits: list[RetrievalHit] = Field(default_factory=list)
    filters: dict[str, object] = Field(default_factory=dict)
    semantic_candidates: int = 0
    keyword_candidates: int = 0
    fused_candidates: int = 0
    rrf_k: int = 60
    took_ms: int = 0
    degraded: bool = False
    #: *Why* it was degraded — "no embedder configured", "the dense arm raised X". PHASE 14 added
    #: this because the reason was computed by the retriever and then dropped by the caller, which
    #: then had to invent one: the claim gate reported "证据检索降级：检索不可用" while returning two
    #: retrieved sources, a sentence that contradicted the payload it was attached to.
    degraded_reason: str | None = None

    def by_channel(self, channel: RetrievalChannel) -> list[RetrievalHit]:
        return [hit for hit in self.hits if hit.channel == channel]


class EvidenceCandidate(StrictModel):
    """LLM-facing shape: a proposed evidence node extracted from raw material.

    Kept separate from :class:`EvidenceItem` because the model must not be able
    to set a confidence score — that is computed deterministically afterwards.
    """

    kind: EvidenceKind = Field(description="Category of the evidence")
    title: str = Field(description="Short human-readable title, e.g. a file name or commit subject")
    snippet: str = Field(default="", description="Verbatim supporting excerpt, max ~300 chars")
    locator_path: str | None = Field(default=None, description="File path if applicable")
    locator_line: int | None = Field(default=None, description="Line number if known")
    locator_url: str | None = Field(default=None, description="URL if known")
    occurred_at: str | None = Field(default=None, description="ISO-8601 date if known")
    rationale: str | None = Field(default=None, description="One sentence on why this is evidence")
