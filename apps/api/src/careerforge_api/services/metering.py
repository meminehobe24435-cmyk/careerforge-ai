"""Metering: what the system records about its own model calls.

Three pieces, and every design choice in them follows from one rule: **a number the operator
cannot check is worse than no number.** So the metering records what the provider actually
reported — tokens, cost, latency, whether the answer came from the cache — and invents nothing.
A deployment on the zero-key heuristic provider really does use zero tokens; the run says
``provider=heuristic`` and the dashboard labels it, rather than estimating spend that never
happened.

* :class:`MeteredProvider` wraps the request's provider and records one row per model call. It
  wraps the *shared* chain rather than rebuilding it, so the cache and the resilience state the
  app built once are the ones that stay in use.
* :class:`DatabaseCacheStore` satisfies the AI core's synchronous ``CacheStore`` protocol — a
  provider's hot path cannot await — while buffering durable events for the request to flush
  into ``ai_caches``. Writing synchronously there would block an event loop on the database.
* :class:`RunRecorder` buffers the calls and writes them, together with the cache events, at the
  end of the request that owns the session; writing inline would open a second connection in the
  middle of a transaction, which is what caused "database is locked" in PHASE 2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import timedelta
import json
import time
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    LLMProvider,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    StructuredContext,
)
from careerforge_ai.providers.caching import CacheStore, InMemoryCacheStore
from careerforge_ai.schemas.common import CacheKind
from careerforge_api.db.compat import utcnow
from careerforge_api.models.cache import AiCache
from careerforge_api.models.observability import LlmCall

__all__ = [
    "CacheEvent",
    "DatabaseCacheStore",
    "MeteredProvider",
    "RunRecorder",
]


@dataclass(slots=True)
class CacheEvent:
    """One cache interaction, buffered for the database."""

    key: str
    kind: str
    outcome: str  # "store" | "hit" | "miss"
    size_bytes: int | None = None
    ttl_seconds: int | None = None


class DatabaseCacheStore:
    """The AI core's cache, with durable accounting.

    Satisfies ``CacheStore`` — which is **synchronous**, because a provider's hot path cannot
    await — by serving reads and writes from memory and appending an event for each one. The
    request that owns the session flushes those events into ``ai_caches`` when it finishes a
    model call (:meth:`RunRecorder.flush_cache`), so the table describes what really happened
    without ever blocking the event loop.
    """

    def __init__(self, inner: CacheStore | None = None) -> None:
        self._inner: CacheStore = inner or InMemoryCacheStore(kind=CacheKind.LLM)
        self._events: list[CacheEvent] = []
        self._flushed = 0

    # ── CacheStore protocol (sync on purpose) ────────────────────────────────
    def get(self, key: str) -> Any | None:
        value = self._inner.get(key)
        self._events.append(
            CacheEvent(key=key, kind="llm", outcome="hit" if value is not None else "miss")
        )
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._inner.set(key, value, ttl_seconds)
        self._events.append(
            CacheEvent(
                key=key,
                kind="llm",
                outcome="store",
                size_bytes=_digest_size(value),
                ttl_seconds=ttl_seconds,
            )
        )

    def record_hit(self, key: str) -> None:
        self._inner.record_hit(key)
        self._events.append(CacheEvent(key=key, kind="llm", outcome="hit"))

    # ── durable side ────────────────────────────────────────────────────────
    def drain(self) -> list[CacheEvent]:
        """Take the buffered events. Called by the recorder, which holds a session."""
        events, self._events = self._events, []
        self._flushed += len(events)
        return events

    @property
    def inner(self) -> CacheStore:
        return self._inner

    def snapshot(self) -> dict[str, Any]:
        """The in-process view, reported beside the durable one rather than mixed into it."""
        hits = getattr(self._inner, "hits", 0)
        misses = getattr(self._inner, "misses", 0)
        entries = getattr(self._inner, "entries", {})
        return {
            "processHits": int(hits),
            "processMisses": int(misses),
            "processEntries": len(entries),
            "eventsFlushed": self._flushed,
        }


def _digest_size(value: Any) -> int | None:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return None


class MeteredProvider:
    """Wraps a provider and records one ``llm_calls`` row per call.

    Delegates ``name`` and ``capabilities`` so the rest of the system cannot tell the difference,
    and records **from the result the provider returned** — tokens, cost, latency and whether it
    was a cache hit. When a provider reports no latency (the heuristic path returns instantly and
    reports nothing), the measured wall time is used instead, because "0 ms" for a call that took
    3 ms is a number that would make the dashboard lie.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        recorder: RunRecorder,
        agent: str,
        workflow: str,
        prompt_version: str | None = None,
    ) -> None:
        self._inner = inner
        self._recorder = recorder
        self._agent = agent
        self._workflow = workflow
        self._prompt_version = prompt_version

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._inner.capabilities

    def __getattr__(self, name: str) -> Any:
        """Delegate anything this wrapper does not define to the wrapped provider.

        The chain exposes more than the ``LLMProvider`` protocol, and one of those extras decides
        whether a call counts as degraded: the orchestrator reads ``last_chain_info`` after every
        structured call (``orchestrator/core.py``), and ``RunContext.degraded`` is
        ``chain.degraded``. A wrapper that forwarded only the protocol silently turned "degraded
        to the heuristic path" into "succeeded" — which is how the first version of this file made
        ``job_service`` crash on a path that had never been taken: it asks the executor for a
        model name only when the outcome is *not* degraded.

        A decorator whose purpose is measurement must not change the thing it measures.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        started = time.perf_counter()
        result = await self._inner.chat(
            messages, temperature=temperature, max_tokens=max_tokens, model=model
        )
        await self._record("chat", result, started)
        return result

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> SchemaT:
        started = time.perf_counter()
        result = await self._inner.structured_output(
            messages, schema, context=context, temperature=temperature, model=model
        )
        # A structured call returns the parsed schema, not the provider's envelope, so there is
        # no model name to record here. The run row carries the model the router selected; this
        # row carries the call's cost facts, and inventing a model name would be worse than
        # leaving it empty.
        self._recorder.note_call(
            agent=self._agent,
            workflow=self._workflow,
            operation="structured",
            provider=self._inner.name,
            model="",
            prompt_version=self._prompt_version,
            latency_ms=int((time.perf_counter() - started) * 1000),
            tokens=None,
            cost=None,
            cache_hit=False,
            status="ok",
        )
        return result

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult:
        started = time.perf_counter()
        result = await self._inner.embed(texts, model=model)
        await self._record("embedding", result, started)
        return result

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming is not metered per token: the chunks arrive after the fact.

        The underlying call still runs (and the run itself is traced); only the per-call row is
        skipped, because a row written before the stream ends would report a token count nobody
        knows yet. The interview SSE path is the only user.
        """
        async for chunk in self._inner.stream(
            messages, temperature=temperature, max_tokens=max_tokens, model=model
        ):
            yield chunk

    async def _record(self, operation: str, result: Any, started: float) -> None:
        latency = int(getattr(result, "latency_ms", 0) or 0)
        measured = int((time.perf_counter() - started) * 1000)
        self._recorder.note_call(
            agent=self._agent,
            workflow=self._workflow,
            operation=operation,
            provider=str(getattr(result, "provider", self._inner.name)),
            model=str(getattr(result, "model", "")) or self._inner.name,
            prompt_version=self._prompt_version,
            latency_ms=max(latency, measured),
            tokens=getattr(result, "tokens", None),
            cost=getattr(result, "cost", None),
            cache_hit=bool(getattr(result, "cached", False)),
            status="ok",
        )


@dataclass(slots=True)
class _PendingCall:
    """A call that has happened; the row is written when the request has a session."""

    agent: str
    workflow: str
    operation: str
    provider: str
    model: str
    prompt_version: str | None
    latency_ms: int
    tokens: Any
    cost: Any
    cache_hit: bool
    status: str


class RunRecorder:
    """Buffers metered calls and writes them beside the cache events.

    Buffered rather than written inline because a provider call happens deep inside an agent
    where no session is in scope, and the request that owns the session is the only place that
    can write without opening a second connection mid-transaction (the mistake that caused
    "database is locked" in PHASE 2).
    """

    def __init__(self, session: AsyncSession, *, user_id: UUID | None = None) -> None:
        self._session = session
        self._user_id = user_id
        self._calls: list[_PendingCall] = []
        self._run_id: UUID | None = None
        self._provider_cache_hits = 0

    def bind_run(self, run_id: UUID | None) -> None:
        """Attach subsequent calls to the run they belong to."""
        self._run_id = run_id

    def note_call(self, **fields: Any) -> None:
        if fields.get("cache_hit"):
            self._provider_cache_hits += 1
        self._calls.append(
            _PendingCall(
                agent=str(fields["agent"]),
                workflow=str(fields["workflow"]),
                operation=str(fields["operation"]),
                provider=str(fields["provider"]),
                model=str(fields["model"]),
                prompt_version=fields.get("prompt_version"),
                latency_ms=int(fields.get("latency_ms") or 0),
                tokens=fields.get("tokens"),
                cost=fields.get("cost"),
                cache_hit=bool(fields.get("cache_hit")),
                status=str(fields.get("status") or "ok"),
            )
        )

    async def flush(self, *, cache_store: DatabaseCacheStore | None = None) -> int:
        """Write the buffered calls and cache events. Returns how many rows were touched."""
        written = 0
        for call in self._calls:
            tokens = call.tokens
            cost = call.cost
            self._session.add(
                LlmCall(
                    user_id=self._user_id,
                    agent_run_id=self._run_id,
                    agent=call.agent,
                    provider=call.provider,
                    model=call.model,
                    operation=call.operation
                    if call.operation in {"chat", "embedding", "structured", "stream"}
                    else "chat",
                    prompt_version=call.prompt_version,
                    prompt_tokens=int(getattr(tokens, "prompt_tokens", 0) or 0),
                    completion_tokens=int(getattr(tokens, "completion_tokens", 0) or 0),
                    total_tokens=int(getattr(tokens, "total_tokens", 0) or 0),
                    cost_usd=float(getattr(cost, "usd", 0.0) or 0.0),
                    cost_cny=float(getattr(cost, "cny", 0.0) or 0.0),
                    latency_ms=call.latency_ms,
                    status=call.status,
                )
            )
            written += 1
        self._calls.clear()
        if self._provider_cache_hits:
            # The run's own ``cache_hit`` flag comes from the executor's *step* cache. A provider
            # cache hit is the other kind, and leaving the row saying ``false`` while
            # ``/cache/stats`` reports a hit is an inconsistency a reader would rightly stop
            # trusting — so the flag is raised to true as soon as either kind fired.
            await self._mark_run_cached()
            self._provider_cache_hits = 0
        if cache_store is not None:
            written += await self._flush_cache(cache_store)
        await self._session.flush()
        return written

    async def _mark_run_cached(self) -> None:
        if self._run_id is None:
            return
        from careerforge_api.models.observability import AgentRun

        row = await self._session.get(AgentRun, self._run_id)
        if row is not None and not row.cache_hit:
            row.cache_hit = True

    async def _flush_cache(self, store: DatabaseCacheStore) -> int:
        """Upsert the cache events: one row per key, with its hit count and expiry.

        Fetched in **one** statement and then updated in memory. Asking per event is what the
        first version did, and it broke immediately: a ``set`` followed by a ``get`` on the same
        key produced two events, the second lookup could not see the row the first had just
        added (it was still pending in the session), and the flush inserted the same cache key
        twice — a UNIQUE violation at commit.
        """
        events = store.drain()
        if not events:
            return 0

        keys = {event.key for event in events}
        existing = {
            row.cache_key: row
            for row in (
                await self._session.scalars(select(AiCache).where(AiCache.cache_key.in_(keys)))
            ).all()
        }
        touched = 0
        for event in events:
            row = existing.get(event.key)
            if row is None:
                if event.outcome == "miss":
                    # A miss on a key nobody ever stored is not an entry; recording it would fill
                    # the table with rows representing nothing.
                    continue
                row = AiCache(
                    user_id=self._user_id,
                    cache_key=event.key,
                    kind=event.kind,
                    payload={},
                    hit_count=1 if event.outcome == "hit" else 0,
                    expires_at=(
                        utcnow() + timedelta(seconds=event.ttl_seconds)
                        if event.ttl_seconds
                        else None
                    ),
                    size_bytes=event.size_bytes,
                )
                self._session.add(row)
                existing[event.key] = row
            else:
                if event.outcome == "hit":
                    row.hit_count += 1
                if event.size_bytes is not None:
                    row.size_bytes = event.size_bytes
            touched += 1
        return touched
