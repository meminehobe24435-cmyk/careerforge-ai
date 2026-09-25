"""Observability schemas: step traces, agent runs and cost.

Observability is a first-class feature of this project, not an afterthought:
the orchestrator emits these records for every workflow, which is what makes the
AI Runs and Cost dashboards real rather than decorative.

Token usage lives in :mod:`careerforge_ai.schemas.usage` and is re-exported here, so a caller that
has always written ``from careerforge_ai.schemas.observability import TokenUsage`` still can.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from careerforge_ai.schemas.common import (
    AgentRunStatus,
    CacheKind,
    CFBaseModel,
    Confidence,
    DegradationReason,
    StrictModel,
    utcnow,
)
from careerforge_ai.schemas.usage import Cost, LLMUsage, TokenUsage, usage_status_of

__all__ = [
    "AgentRunRecord",
    "CacheStats",
    # Re-exported with the other cost types: the split is internal.
    "Cost",
    "CostByGroup",
    "ExtractedRunNarrative",
    # Re-exported from ``schemas.usage``: the split is internal, the import path is not.
    "LLMUsage",
    "ProviderSelection",
    "StepTrace",
    "TokenUsage",
    "usage_status_of",
]


class StepTrace(CFBaseModel):
    """Trace of one orchestrator step — the unit shown when a run is expanded."""

    name: str
    status: str = Field(default="ok", description="ok | failed | degraded | cached | skipped")
    latency_ms: int = 0
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    cost: Cost = Field(default_factory=Cost)
    #: The same call's usage as an envelope, or ``None`` when the step made no model call.
    #: ``None`` here is a statement: a pure function step has no usage *at all*, which is a
    #: different thing from a model call whose usage the provider did not report (that is an
    #: :class:`LLMUsage` with ``usage_status="unavailable"``). Before PHASE 13 both were
    #: written as zero and the AI Runs page could not tell them apart.
    usage: LLMUsage | None = None
    cache_hit: bool = False
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    attempts: int = Field(default=1, ge=1)
    input_digest: str = Field(default="", description="sha256 prefix of normalised input")
    output_digest: str = Field(default="", description="sha256 prefix of serialised output")
    error_code: str | None = None
    error_message: str | None = None
    degradation_reason: DegradationReason | None = None
    started_at: datetime = Field(default_factory=utcnow)

    @property
    def failed(self) -> bool:
        return self.status == "failed"

    def usage_or_unavailable(self) -> LLMUsage:
        """This step's envelope, or an ``unavailable`` one when the step made no model call."""
        return self.usage or LLMUsage.unavailable(provider=self.provider, model=self.model)


class ProviderSelection(CFBaseModel):
    """Which provider actually served a step, and whether that was a fallback."""

    provider: str
    model: str | None = None
    requested_provider: str | None = None
    degraded: bool = False
    reason: DegradationReason = DegradationReason.NONE
    chain_position: int = Field(default=0, ge=0)


class AgentRunRecord(CFBaseModel):
    """A complete workflow execution, persisted to ``agent_runs``."""

    id: UUID | None = None
    user_id: UUID | None = None
    workflow: str
    agent: str
    status: AgentRunStatus = AgentRunStatus.RUNNING
    trigger: str = Field(default="api", description="api | job | manual | seed | eval")
    steps: list[StepTrace] = Field(default_factory=list)

    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    degraded: bool = False
    degradation_reason: DegradationReason = DegradationReason.NONE

    tokens: TokenUsage = Field(default_factory=TokenUsage)
    cost: Cost = Field(default_factory=Cost)
    #: The run's usage as one envelope, accumulated from the steps' own envelopes. Absent
    #: (``None``) for a run in which no model call reported anything — which includes every
    #: run on the zero-key heuristic provider, whose calls honestly declare ``unavailable``.
    usage: LLMUsage | None = None
    latency_ms: int = 0
    cache_hits: int = Field(default=0, ge=0)

    input_digest: str = ""
    output_digest: str = ""
    input_ref: dict[str, object] = Field(default_factory=dict)
    output_ref: dict[str, object] = Field(default_factory=dict)

    error_code: str | None = None
    error_message: str | None = None
    request_id: str | None = None
    parent_run_id: UUID | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None

    def step(self, name: str) -> StepTrace | None:
        return next((trace for trace in self.steps if trace.name == name), None)

    def recompute_totals(self) -> None:
        """Derive run-level totals from the step traces (never hand-maintained).

        Two accumulations rather than one, and they are not redundant: ``tokens``/``cost``
        are the counters every existing consumer reads (and the seeded, hand-built traces
        in tests still populate), while ``usage`` is the envelope that knows whether the
        counters are a measurement, an estimate, or an absence of both.
        """
        total = TokenUsage()
        cost = Cost()
        envelope: LLMUsage | None = None
        for trace in self.steps:
            total = total.merged(trace.tokens)
            cost = cost + trace.cost
            if trace.usage is not None:
                envelope = trace.usage if envelope is None else envelope.merge(trace.usage)
        self.tokens = total
        self.cost = cost
        self.usage = envelope
        self.latency_ms = sum(trace.latency_ms for trace in self.steps)
        self.cache_hits = sum(1 for trace in self.steps if trace.cache_hit)

    def usage_or_unavailable(self) -> LLMUsage:
        """The run's envelope, or an ``unavailable`` one when nothing reported usage."""
        return self.usage or LLMUsage.unavailable(
            provider=self.provider, model=self.model, request_id=self.request_id
        )

    @property
    def degraded_steps(self) -> list[StepTrace]:
        return [trace for trace in self.steps if trace.status == "degraded"]


class CacheStats(CFBaseModel):
    """Cache effectiveness, surfaced on the cost dashboard."""

    kind: CacheKind
    hits: int = 0
    misses: int = 0
    entries: int = 0
    saved_tokens: int = 0
    saved_usd: float = 0.0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0


class CostByGroup(CFBaseModel):
    """Cost aggregated by agent, workflow or feature for the charts."""

    key: str
    label: str = ""
    calls: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    cost_cny: float = 0.0
    avg_latency_ms: int = 0
    cache_hit_rate: float = 0.0


class ExtractedRunNarrative(StrictModel):
    """Optional LLM-written one-paragraph summary attached to an agent run."""

    summary: str = Field(default="", description="What this run produced, in one or two sentences")
    confidence: Confidence = Field(default=0.5, description="How complete the result looks, 0–1")
