"""Observability response models (``docs/API.md`` §2.12).

Two things every payload here does: it reports what was **measured** (tokens the provider
reported, latency the provider or the clock observed) and it carries the numbers a reader needs
to judge them — the provider that served the call, whether it came from the cache, and the
budget ceiling the spend is measured against.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AiCostsResponse",
    "AiRunDetailResponse",
    "AiRunResponse",
    "AiStepResponse",
    "CacheKindStats",
    "CacheProcessStats",
    "CacheStatsResponse",
    "CostBreakdown",
    "CostByEntity",
    "CostTotals",
    "DailyCost",
    "LlmCallResponse",
    "PromptVersionResponse",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class AiRunResponse(_CamelModel):
    """One traced run, as the list shows it.

    ``usageStatus`` is what makes the counters readable (PHASE 13):

    * ``reported`` — the provider said so;
    * ``estimated`` — computed locally, useful as a bound, not as spend;
    * ``cached`` — served from the cache, nothing was billed;
    * ``unavailable`` — **no usage was reported**. Every count beside it is ``null``, and a client
      must print "unavailable" rather than ``0``;
    * ``legacy`` — written before PHASE 13, when unknown usage was stored as ``0``. Reported as
      itself rather than silently re-labelled: those numbers are zeros of unknown provenance.
    """

    id: str
    user_id: str | None = Field(default=None, alias="userId")
    workflow: str
    agent: str
    status: str = "running"
    trigger: str = "api"
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = Field(default=None, alias="promptVersion")
    #: ``null`` means the provider did not report this count. It is not ``0``.
    prompt_tokens: int | None = Field(default=None, alias="promptTokens")
    completion_tokens: int | None = Field(default=None, alias="completionTokens")
    total_tokens: int | None = Field(default=None, alias="totalTokens")
    cached_tokens: int | None = Field(default=None, alias="cachedTokens")
    cost_usd: float | None = Field(default=None, alias="costUsd")
    cost_cny: float | None = Field(default=None, alias="costCny")
    usage_status: str | None = Field(default=None, alias="usageStatus")
    latency_ms: int | None = Field(default=None, alias="latencyMs")
    cache_hit: bool = Field(default=False, alias="cacheHit")
    request_id: str | None = Field(default=None, alias="requestId")
    error: str | None = None
    #: The machine-readable classification of ``error`` (``PROVIDER_UNAVAILABLE``, …). A reader can
    #: act on this where the free text is only a clue.
    error_code: str | None = Field(default=None, alias="errorCode")
    step_count: int = Field(default=0, alias="stepCount")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")


class AiStepResponse(_CamelModel):
    """One workflow step, from the run's own trace."""

    name: str
    status: str = "ok"
    latency_ms: int = Field(default=0, alias="latencyMs")
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = Field(default=None, alias="promptVersion")
    attempts: int = 1
    cache_hit: bool = Field(default=False, alias="cacheHit")
    #: ``null`` when the step made no model call *or* when the model call's usage was not reported;
    #: ``usageStatus`` distinguishes the two, and the distinction is why both fields exist.
    tokens: int | None = None
    cost_usd: float | None = Field(default=None, alias="costUsd")
    usage_status: str | None = Field(default=None, alias="usageStatus")
    #: Digests rather than payloads: the trace says *what was sent* without copying candidate
    #: material into a table an operator browses.
    input_digest: str = Field(default="", alias="inputDigest")
    output_digest: str = Field(default="", alias="outputDigest")
    error_code: str | None = Field(default=None, alias="errorCode")
    error_message: str | None = Field(default=None, alias="errorMessage")
    started_at: datetime | None = Field(default=None, alias="startedAt")


class LlmCallResponse(_CamelModel):
    """One metered model call."""

    id: str
    agent: str
    provider: str
    model: str = ""
    operation: str = "chat"
    prompt_version: str | None = Field(default=None, alias="promptVersion")
    prompt_tokens: int | None = Field(default=None, alias="promptTokens")
    completion_tokens: int | None = Field(default=None, alias="completionTokens")
    total_tokens: int | None = Field(default=None, alias="totalTokens")
    cached_tokens: int | None = Field(default=None, alias="cachedTokens")
    cost_usd: float | None = Field(default=None, alias="costUsd")
    cost_cny: float | None = Field(default=None, alias="costCny")
    usage_status: str | None = Field(default=None, alias="usageStatus")
    latency_ms: int | None = Field(default=None, alias="latencyMs")
    status: str = "ok"
    request_id: str | None = Field(default=None, alias="requestId")
    created_at: datetime | None = Field(default=None, alias="createdAt")


class AiRunDetailResponse(AiRunResponse):
    """``GET /ai-runs/{id}`` — the step chain and every call the run made."""

    steps: list[AiStepResponse] = Field(default_factory=list)
    calls: list[LlmCallResponse] = Field(default_factory=list)
    input_ref: dict[str, object] = Field(default_factory=dict, alias="inputRef")
    output_ref: dict[str, object] = Field(default_factory=dict, alias="outputRef")


class DailyCost(_CamelModel):
    day: str
    runs: int = 0
    tokens: int = 0
    cost_usd: float = Field(default=0.0, alias="costUsd")
    cost_cny: float = Field(default=0.0, alias="costCny")


class CostTotals(_CamelModel):
    runs: int = 0
    model_calls: int = Field(default=0, alias="modelCalls")
    tokens: int = 0
    cost_usd: float = Field(default=0.0, alias="costUsd")
    cost_cny: float = Field(default=0.0, alias="costCny")
    latency_ms: int = Field(default=0, alias="latencyMs")


class AiCostsResponse(_CamelModel):
    range: str
    days: list[DailyCost] = Field(default_factory=list)
    totals: CostTotals = Field(default_factory=CostTotals)
    daily_budget_usd: float = Field(default=0.0, alias="dailyBudgetUsd")
    #: Runs in the window whose usage was never reported (``unavailable``/``legacy``). Their
    #: counters are ``NULL`` and ``SUM`` skips them, so ``totals`` is a **floor** rather than a
    #: complete figure — a fact the payload states instead of leaving to be inferred (PHASE 13).
    unaccounted_runs: int = Field(default=0, alias="unaccountedRuns")
    notes: list[str] = Field(default_factory=list)


class CostByEntity(_CamelModel):
    agent: str
    runs: int = 0
    tokens: int = 0
    cost_usd: float = Field(default=0.0, alias="costUsd")
    cost_cny: float = Field(default=0.0, alias="costCny")
    avg_latency_ms: float = Field(default=0.0, alias="avgLatencyMs")
    cache_hits: int = Field(default=0, alias="cacheHits")


class CostBreakdown(_CamelModel):
    feature: str
    workflows: list[str] = Field(default_factory=list)
    runs: int = 0
    tokens: int = 0
    cost_usd: float = Field(default=0.0, alias="costUsd")
    cost_cny: float = Field(default=0.0, alias="costCny")


class CacheKindStats(_CamelModel):
    kind: str
    entries: int = 0
    hits: int = 0
    bytes: int = 0


class CacheProcessStats(_CamelModel):
    process_hits: int = Field(default=0, alias="processHits")
    process_misses: int = Field(default=0, alias="processMisses")
    process_entries: int = Field(default=0, alias="processEntries")
    events_flushed: int = Field(default=0, alias="eventsFlushed")
    #: ``null`` before the process has answered anything: an empty cache has no hit *rate*, and
    #: reporting 0.0 would read as "the cache never helps".
    hit_rate: float | None = Field(default=None, alias="hitRate")


class CacheStatsResponse(_CamelModel):
    by_kind: list[CacheKindStats] = Field(default_factory=list, alias="byKind")
    persisted_hits: int = Field(default=0, alias="persistedHits")
    process: CacheProcessStats = Field(default_factory=CacheProcessStats)


class PromptVersionResponse(_CamelModel):
    name: str
    version: int
    sha256: str = ""
    is_active: bool = Field(default=False, alias="isActive")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
