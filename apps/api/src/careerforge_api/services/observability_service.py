"""Observability reads: runs, costs, cache hit rates and the prompt registry.

Every response here is read straight from ``agent_runs`` and ``llm_calls`` — the rows the
executor and the metered provider wrote (see :mod:`careerforge_api.services.metering`) — and
nothing is estimated. The mapping from workflow to product feature lives here because that is a
presentation decision: cost per agent answers "which part of the system spends money", cost per
feature answers "which button costs money", and only the second one is actionable for whoever is
paying.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.db.compat import utcnow
from careerforge_api.models.cache import AiCache
from careerforge_api.models.observability import AgentRun, LlmCall
from careerforge_api.services.metering import DatabaseCacheStore

__all__ = [
    "ObservabilityService",
    "WORKFLOW_FEATURES",
    "prompt_digest",
]

#: Workflow → the feature a candidate recognises. Cost per agent answers "which part of the
#: system spends money"; cost per feature answers "which button costs money", and only the second
#: one is actionable for whoever is paying.
WORKFLOW_FEATURES: dict[str, str] = {
    "jd_analysis": "JD 分析",
    "job_match": "匹配评分",
    "claim_validate": "断言验证",
    "resume_optimize": "简历优化",
    "profile_import": "简历导入",
    "evidence_graph": "证据图谱",
    "interview_plan": "模拟面试",
    "interview_turn": "模拟面试",
    "interview_finish": "模拟面试",
    "skill_gap": "技能缺口",
    "recruiter_publish": "公开页生成",
}

_COST_RANGES: dict[str, int | None] = {"7d": 7, "30d": 30, "90d": 90, "all": None}


def _cache_hit_sum() -> Any:
    """``SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END)`` — portable across SQLite and PostgreSQL."""
    from sqlalchemy import case

    return case((AgentRun.cache_hit.is_(True), 1), else_=0)


class ObservabilityService:
    """Reads for the AI Runs and Cost pages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── runs ─────────────────────────────────────────────────────────────────

    async def list_runs(
        self,
        *,
        user_id: UUID | None = None,
        agent: str | None = None,
        workflow: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
        include_system: bool = True,
    ) -> tuple[Sequence[AgentRun], int]:
        """Runs newest first, optionally filtered.

        A run with no ``user_id`` belongs to the system (a seed, a scheduled job). Those are
        included by default — an operator looking at costs wants the whole picture — and the
        filter is explicit so a candidate-scoped view can exclude them.
        """
        conditions = []
        if user_id is not None and not include_system:
            conditions.append(AgentRun.user_id == user_id)
        if agent:
            conditions.append(AgentRun.agent == agent)
        if workflow:
            conditions.append(AgentRun.workflow == workflow)
        if status:
            conditions.append(AgentRun.status == status)
        if since:
            conditions.append(AgentRun.started_at >= since)

        statement = select(AgentRun)
        count_statement = select(func.count()).select_from(AgentRun)
        for condition in conditions:
            statement = statement.where(condition)
            count_statement = count_statement.where(condition)
        statement = statement.order_by(AgentRun.started_at.desc()).limit(limit).offset(offset)
        rows = (await self._session.scalars(statement)).all()
        total = int(await self._session.scalar(count_statement) or 0)
        return rows, total

    async def get_run(self, run_id: UUID) -> AgentRun | None:
        return await self._session.get(AgentRun, run_id)

    async def calls_of(self, run_id: UUID) -> Sequence[LlmCall]:
        statement = (
            select(LlmCall).where(LlmCall.agent_run_id == run_id).order_by(LlmCall.created_at)
        )
        return (await self._session.scalars(statement)).all()

    # ── costs ────────────────────────────────────────────────────────────────

    async def cost_summary(self, *, range_key: str = "7d") -> dict[str, Any]:
        """Daily tokens and cost, plus the totals and the call count."""
        days = _COST_RANGES.get(range_key, 7)
        since = None if days is None else utcnow() - timedelta(days=days)

        daily = select(
            func.date(AgentRun.started_at).label("day"),
            func.count().label("runs"),
            func.sum(AgentRun.total_tokens).label("tokens"),
            func.sum(AgentRun.cost_usd).label("usd"),
            func.sum(AgentRun.cost_cny).label("cny"),
        )
        totals = select(
            func.count(AgentRun.id),
            func.coalesce(func.sum(AgentRun.total_tokens), 0),
            func.coalesce(func.sum(AgentRun.cost_usd), 0.0),
            func.coalesce(func.sum(AgentRun.cost_cny), 0.0),
            func.coalesce(func.sum(AgentRun.latency_ms), 0),
        )
        calls = select(func.count(LlmCall.id))
        if since is not None:
            daily = daily.where(AgentRun.started_at >= since)
            totals = totals.where(AgentRun.started_at >= since)
            calls = calls.where(LlmCall.created_at >= since)

        rows = (await self._session.execute(daily.group_by("day").order_by("day"))).all()
        run_count, tokens, usd, cny, latency = (await self._session.execute(totals)).one()
        return {
            "range": range_key,
            "days": [
                {
                    "day": str(row[0]),
                    "runs": int(row[1] or 0),
                    "tokens": int(row[2] or 0),
                    "costUsd": round(float(row[3] or 0.0), 6),
                    "costCny": round(float(row[4] or 0.0), 6),
                }
                for row in rows
            ],
            "totals": {
                "runs": int(run_count or 0),
                "modelCalls": int(await self._session.scalar(calls) or 0),
                "tokens": int(tokens or 0),
                "costUsd": round(float(usd or 0.0), 6),
                "costCny": round(float(cny or 0.0), 6),
                "latencyMs": int(latency or 0),
            },
        }

    async def cost_by_agent(self, *, range_key: str = "30d") -> list[dict[str, Any]]:
        days = _COST_RANGES.get(range_key, 30)
        since = None if days is None else utcnow() - timedelta(days=days)
        statement = select(
            AgentRun.agent,
            func.count(AgentRun.id),
            func.coalesce(func.sum(AgentRun.total_tokens), 0),
            func.coalesce(func.sum(AgentRun.cost_usd), 0.0),
            func.coalesce(func.sum(AgentRun.cost_cny), 0.0),
            func.coalesce(func.avg(AgentRun.latency_ms), 0.0),
            func.coalesce(func.sum(_cache_hit_sum()), 0),
        ).group_by(AgentRun.agent)
        if since is not None:
            statement = statement.where(AgentRun.started_at >= since)
        rows = (await self._session.execute(statement)).all()
        return [
            {
                "agent": str(row[0]),
                "runs": int(row[1] or 0),
                "tokens": int(row[2] or 0),
                "costUsd": round(float(row[3] or 0.0), 6),
                "costCny": round(float(row[4] or 0.0), 6),
                "avgLatencyMs": round(float(row[5] or 0.0), 1),
                "cacheHits": int(row[6] or 0),
            }
            for row in rows
        ]

    async def cost_by_feature(self, *, range_key: str = "30d") -> list[dict[str, Any]]:
        """The same totals, grouped by the product feature rather than by the agent name."""
        per_workflow = await self._session.execute(
            select(
                AgentRun.workflow,
                func.count(AgentRun.id),
                func.coalesce(func.sum(AgentRun.total_tokens), 0),
                func.coalesce(func.sum(AgentRun.cost_usd), 0.0),
                func.coalesce(func.sum(AgentRun.cost_cny), 0.0),
            )
            .where(
                AgentRun.started_at
                >= utcnow() - timedelta(days=_COST_RANGES.get(range_key, 30) or 3650)
            )
            .group_by(AgentRun.workflow)
        )
        buckets: dict[str, dict[str, Any]] = {}
        for workflow, runs, tokens, usd, cny in per_workflow.all():
            feature = WORKFLOW_FEATURES.get(str(workflow), str(workflow))
            entry = buckets.setdefault(
                feature,
                {
                    "feature": feature,
                    "workflows": [],
                    "runs": 0,
                    "tokens": 0,
                    "costUsd": 0.0,
                    "costCny": 0.0,
                },
            )
            entry["workflows"].append(str(workflow))
            entry["runs"] += int(runs or 0)
            entry["tokens"] += int(tokens or 0)
            entry["costUsd"] = round(entry["costUsd"] + float(usd or 0.0), 6)
            entry["costCny"] = round(entry["costCny"] + float(cny or 0.0), 6)
        return sorted(buckets.values(), key=lambda item: (-item["runs"], item["feature"]))

    # ── cache ────────────────────────────────────────────────────────────────

    async def cache_stats(self, *, store: DatabaseCacheStore | None = None) -> dict[str, Any]:
        """Per-kind entries and hits from the table, plus the in-process counters.

        The two are reported separately on purpose: the table survives a restart and answers
        "has this deployment been serving cached answers at all", while the process counters
        answer "is the cache working right now". Blending them would produce a hit rate that
        describes neither.
        """
        rows = (
            await self._session.execute(
                select(
                    AiCache.kind,
                    func.count(AiCache.id),
                    func.coalesce(func.sum(AiCache.hit_count), 0),
                    func.coalesce(func.sum(AiCache.size_bytes), 0),
                ).group_by(AiCache.kind)
            )
        ).all()
        by_kind: dict[str, dict[str, Any]] = {
            str(kind): {
                "kind": str(kind),
                "entries": int(entries or 0),
                "hits": int(hits or 0),
                "bytes": int(size or 0),
            }
            for kind, entries, hits, size in rows
        }
        for expected in ("llm", "embedding", "tool"):
            by_kind.setdefault(expected, {"kind": expected, "entries": 0, "hits": 0, "bytes": 0})
        total_hits = sum(int(item["hits"]) for item in by_kind.values())
        snapshot = store.snapshot() if store is not None else {}
        process_hits = int(snapshot.get("processHits", 0))
        process_misses = int(snapshot.get("processMisses", 0))
        return {
            "byKind": list(by_kind.values()),
            "persistedHits": total_hits,
            "process": {
                **snapshot,
                "hitRate": round(process_hits / (process_hits + process_misses), 4)
                if (process_hits + process_misses)
                else None,
            },
        }

    # ── prompts ──────────────────────────────────────────────────────────────

    async def prompt_versions(self) -> list[dict[str, Any]]:
        from careerforge_api.models.prompt import PromptVersion

        rows = (
            await self._session.scalars(
                select(PromptVersion).order_by(PromptVersion.name, PromptVersion.version.desc())
            )
        ).all()
        return [
            {
                "name": row.name,
                "version": row.version,
                "sha256": row.content_sha256,
                "isActive": row.is_active,
                "updatedAt": row.updated_at,
            }
            for row in rows
        ]


def case_cache_hits() -> Any:
    """``SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END)`` — portable across SQLite and PostgreSQL."""
    from sqlalchemy import case

    return case((AgentRun.cache_hit.is_(True), 1), else_=0)


def prompt_digest(text: str) -> str:
    """Stable digest for a prompt body, so a version bump is provable from the row."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
