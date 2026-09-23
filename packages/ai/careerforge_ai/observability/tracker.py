"""Run tracking: the sink the orchestrator writes traces into.

Two implementations ship here:

* :class:`InMemoryTracker` — used by unit tests and by the evaluation runner, so
  evals do not need a database.
* A database-backed tracker lives in the API layer and satisfies the same
  protocol; that is how the AI Runs page gets its data.

The protocol is deliberately small: the orchestrator should not know whether its
traces end up in Postgres, a list, or stdout.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from careerforge_ai.schemas.common import CacheKind
from careerforge_ai.schemas.observability import (
    AgentRunRecord,
    CacheStats,
    Cost,
    CostByGroup,
    StepTrace,
    TokenUsage,
)

__all__ = ["InMemoryTracker", "RunTracker", "UsageLedger"]


class RunTracker(Protocol):
    """Where agent-run traces go."""

    async def start_run(self, record: AgentRunRecord) -> AgentRunRecord: ...

    async def record_step(self, run: AgentRunRecord, step: StepTrace) -> None: ...

    async def finish_run(self, run: AgentRunRecord) -> None: ...


@dataclass(slots=True)
class InMemoryTracker:
    """Keeps runs in a list. Fast, deterministic, and enough for assertions."""

    runs: list[AgentRunRecord] = field(default_factory=list)
    started: int = 0
    finished: int = 0

    async def start_run(self, record: AgentRunRecord) -> AgentRunRecord:
        self.started += 1
        self.runs.append(record)
        return record

    async def record_step(self, run: AgentRunRecord, step: StepTrace) -> None:
        run.steps.append(step)
        run.recompute_totals()

    async def finish_run(self, run: AgentRunRecord) -> None:
        self.finished += 1
        run.recompute_totals()

    # ── test helpers ─────────────────────────────────────────────────────────

    def by_workflow(self, workflow: str) -> list[AgentRunRecord]:
        return [run for run in self.runs if run.workflow == workflow]

    def last(self) -> AgentRunRecord | None:
        return self.runs[-1] if self.runs else None


@dataclass(slots=True)
class UsageLedger:
    """Aggregates usage for cost dashboards.

    Kept separate from the tracker so the dashboard can be rebuilt from persisted
    ``llm_calls`` rows without re-running anything.
    """

    tokens: TokenUsage = field(default_factory=TokenUsage)
    cost: Cost = field(default_factory=Cost)
    calls: int = 0
    cache_hits: int = 0
    by_agent: dict[str, CostByGroup] = field(default_factory=dict)

    def record(
        self,
        *,
        agent: str,
        tokens: TokenUsage,
        cost: Cost,
        latency_ms: int,
        cache_hit: bool = False,
        label: str = "",
    ) -> None:
        self.calls += 1
        self.tokens = self.tokens.merged(tokens)
        self.cost = self.cost + cost
        if cache_hit:
            self.cache_hits += 1

        group = self.by_agent.get(agent)
        if group is None:
            group = CostByGroup(key=agent, label=label or agent)
            self.by_agent[agent] = group
        group.calls += 1
        group.tokens += tokens.total_tokens
        group.cost_usd = round(group.cost_usd + cost.usd, 8)
        group.cost_cny = round(group.cost_cny + cost.cny, 6)
        previous = group.avg_latency_ms * (group.calls - 1)
        group.avg_latency_ms = int((previous + latency_ms) / group.calls)

    @property
    def cache_hit_rate(self) -> float:
        return round(self.cache_hits / self.calls, 4) if self.calls else 0.0

    def groups(self) -> Sequence[CostByGroup]:
        return sorted(self.by_agent.values(), key=lambda group: group.cost_usd, reverse=True)

    def cache_stats(self, kind: CacheKind, *, entries: int = 0) -> CacheStats:
        return CacheStats(
            kind=kind,
            hits=self.cache_hits,
            misses=max(0, self.calls - self.cache_hits),
            entries=entries,
            saved_tokens=self.tokens.total_tokens if self.cache_hits else 0,
            saved_usd=0.0,
        )
