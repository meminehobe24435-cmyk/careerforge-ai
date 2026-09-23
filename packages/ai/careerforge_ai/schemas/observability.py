"""Observability schemas: step traces, agent runs, token usage and cost.

Observability is a first-class feature of this project, not an afterthought:
the orchestrator emits these records for every workflow, which is what makes the
AI Runs and Cost dashboards real rather than decorative.
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

__all__ = [
    "AgentRunRecord",
    "CacheStats",
    "Cost",
    "CostByGroup",
    "ExtractedRunNarrative",
    "ProviderSelection",
    "StepTrace",
    "TokenUsage",
]


class TokenUsage(CFBaseModel):
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    estimated: bool = Field(
        default=False,
        description="True when tokens were estimated rather than reported by the provider",
    )

    def merged(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            estimated=self.estimated or other.estimated,
        )


class Cost(CFBaseModel):
    """Dual-currency cost so the dashboard works for both CNY and USD pricing."""

    usd: float = Field(default=0.0, ge=0.0)
    cny: float = Field(default=0.0, ge=0.0)
    currency: str = "USD"
    price_table_version: str = "pricing@1.0.0"

    def __add__(self, other: Cost) -> Cost:
        return Cost(
            usd=round(self.usd + other.usd, 8),
            cny=round(self.cny + other.cny, 8),
            currency=self.currency,
            price_table_version=self.price_table_version,
        )


class StepTrace(CFBaseModel):
    """Trace of one orchestrator step — the unit shown when a run is expanded."""

    name: str
    status: str = Field(default="ok", description="ok | failed | degraded | cached | skipped")
    latency_ms: int = 0
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    cost: Cost = Field(default_factory=Cost)
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
        """Derive run-level totals from the step traces (never hand-maintained)."""
        total = TokenUsage()
        cost = Cost()
        for trace in self.steps:
            total = total.merged(trace.tokens)
            cost = cost + trace.cost
        self.tokens = total
        self.cost = cost
        self.latency_ms = sum(trace.latency_ms for trace in self.steps)
        self.cache_hits = sum(1 for trace in self.steps if trace.cache_hit)

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
