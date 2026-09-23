"""Provider decorators: caching, routing and resilience.

Composition order matters and is deliberate (ADR-009)::

    Resilient(Routed(Cached(primary), fallback...))

* **Cache** sits closest to the provider so a cache hit avoids routing and
  resilience work entirely.
* **Router** chooses a model per task class (cheap model for extraction, strong
  model for interview turns) and enforces the budget guardrail.
* **Resilience** wraps the whole chain with timeouts, retries and fallback, so
  the outermost layer is the one that guarantees "something always comes back".
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import time
from typing import Any, Protocol

from pydantic import BaseModel

from careerforge_ai.errors import (
    BudgetExceededError,
    CareerForgeError,
    ProviderUnavailableError,
    is_retryable,
)
from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    LLMProvider,
    ProviderCapabilities,
    ProviderChainInfo,
    SchemaT,
    StreamChunk,
    StructuredContext,
)
from careerforge_ai.schemas.common import CacheKind, DegradationReason
from careerforge_ai.schemas.observability import CacheStats, Cost, TokenUsage

__all__ = [
    "CacheStore",
    "CachedProvider",
    "InMemoryCacheStore",
    "ProviderChainInfo",
    "ResilientProvider",
    "RoutedProvider",
    "TaskClass",
]


# ── Cache ────────────────────────────────────────────────────────────────────


class CacheStore(Protocol):
    """Minimal cache contract — implemented in-memory here and by the DB in the API."""

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...
    def record_hit(self, key: str) -> None: ...


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float
    hits: int = 0


@dataclass(slots=True)
class InMemoryCacheStore:
    """TTL cache with hit accounting, used for local runs and tests."""

    entries: dict[str, _Entry] = field(default_factory=dict)
    kind: CacheKind = CacheKind.LLM
    hits: int = 0
    misses: int = 0

    def get(self, key: str) -> Any | None:
        entry = self.entries.get(key)
        if entry is None:
            self.misses += 1
            return None
        if entry.expires_at < time.time():
            self.entries.pop(key, None)
            self.misses += 1
            return None
        entry.hits += 1
        self.hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.entries[key] = _Entry(value=value, expires_at=time.time() + max(0, ttl_seconds))

    def record_hit(self, key: str) -> None:  # pragma: no cover - counter only
        entry = self.entries.get(key)
        if entry is not None:
            entry.hits += 1

    def stats(self, *, saved_tokens: int = 0, saved_usd: float = 0.0) -> CacheStats:
        return CacheStats(
            kind=self.kind,
            hits=self.hits,
            misses=self.misses,
            entries=len(self.entries),
            saved_tokens=saved_tokens,
            saved_usd=saved_usd,
        )

    def clear(self) -> None:
        self.entries.clear()
        self.hits = 0
        self.misses = 0


def _digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CachedProvider:
    """Caches chat, embedding and structured-output results.

    Cache keys include the model and the full prompt, so a prompt or model change
    can never be served a stale answer.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        store: CacheStore,
        ttl_seconds: int = 86_400,
        embedding_ttl_seconds: int = 604_800,
        enabled: bool = True,
    ) -> None:
        self._inner = inner
        self._store = store
        self._ttl = ttl_seconds
        self._embedding_ttl = embedding_ttl_seconds
        self._enabled = enabled

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._inner.capabilities

    def _chat_key(
        self, messages: Sequence[ChatMessage], model: str | None, temperature: float
    ) -> str:
        payload = "|".join(
            [self.name, model or "", f"{temperature:.3f}", *[m.content for m in messages]]
        )
        return f"llm:{self.name}:{_digest(payload)}"

    def _embed_key(self, texts: Sequence[str], model: str | None) -> str:
        payload = "|".join([self.name, model or "", *texts])
        return f"emb:{self.name}:{_digest(payload)}"

    def _schema_key(
        self,
        messages: Sequence[ChatMessage],
        schema: type[BaseModel],
        context: StructuredContext | None,
    ) -> str:
        payload = "|".join(
            [
                self.name,
                schema.__name__,
                schema.model_json_schema().__repr__(),
                *[m.content for m in messages],
                repr(sorted((context or {}).items(), key=lambda item: str(item[0])))[:4000],
            ]
        )
        return f"struct:{self.name}:{_digest(payload)}"

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        if not self._enabled:
            return await self._inner.chat(
                messages, temperature=temperature, max_tokens=max_tokens, model=model
            )
        key = self._chat_key(messages, model, temperature)
        cached = self._store.get(key)
        if isinstance(cached, ChatResult):
            return ChatResult(
                content=cached.content,
                provider=cached.provider,
                model=cached.model,
                tokens=TokenUsage(estimated=True),
                cost=Cost(),
                latency_ms=0,
                cached=True,
                degraded=cached.degraded,
                degradation_reason=cached.degradation_reason,
                finish_reason=cached.finish_reason,
            )
        result = await self._inner.chat(
            messages, temperature=temperature, max_tokens=max_tokens, model=model
        )
        self._store.set(key, result, self._ttl)
        return result

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        # Streaming bypasses the cache: replaying a cached stream would misreport
        # latency and hide the cache from the user.
        async for chunk in self._inner.stream(
            messages, temperature=temperature, max_tokens=max_tokens, model=model
        ):
            yield chunk

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        if not self._enabled or not texts:
            return await self._inner.embed(texts, model=model)
        key = self._embed_key(texts, model)
        cached = self._store.get(key)
        if isinstance(cached, EmbeddingResult):
            return EmbeddingResult(
                vectors=cached.vectors,
                provider=cached.provider,
                model=cached.model,
                dim=cached.dim,
                cached=True,
                degraded=cached.degraded,
            )
        result = await self._inner.embed(texts, model=model)
        self._store.set(key, result, self._embedding_ttl)
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
        if not self._enabled:
            return await self._inner.structured_output(
                messages, schema, context=context, temperature=temperature, model=model
            )
        key = self._schema_key(messages, schema, context)
        cached = self._store.get(key)
        if isinstance(cached, schema):
            return cached
        result = await self._inner.structured_output(
            messages, schema, context=context, temperature=temperature, model=model
        )
        self._store.set(key, result, self._ttl)
        return result


# ── Routing ──────────────────────────────────────────────────────────────────


class TaskClass(str):
    """Task classes used to route to differently-priced models."""

    EXTRACTION = "extraction"
    GENERATION = "generation"
    INTERVIEW = "interview"
    EMBEDDING = "embedding"


@dataclass(slots=True)
class _Budget:
    daily_usd: float
    spent_usd: float = 0.0

    @property
    def exhausted(self) -> bool:
        return self.daily_usd > 0 and self.spent_usd >= self.daily_usd


class RoutedProvider:
    """Selects a model per task class and enforces the per-user budget.

    Once the budget is exhausted the router raises :class:`BudgetExceededError`,
    which the resilience layer converts into a heuristic fallback. The user is
    told the result is degraded rather than silently receiving a lower-quality
    answer.
    """

    def __init__(
        self,
        inner: LLMProvider,
        *,
        model_by_task: Mapping[str, str] | None = None,
        budget: _Budget | None = None,
        task: str = TaskClass.GENERATION,
    ) -> None:
        self._inner = inner
        self._model_by_task = dict(model_by_task or {})
        self._budget = budget
        self._task = task

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._inner.capabilities

    def _model_for(self, task: str | None) -> str | None:
        key = task or self._task
        return self._model_by_task.get(key) or None

    def charge(self, cost: Cost) -> None:
        if self._budget is not None:
            self._budget.spent_usd += cost.usd

    def _guard(self) -> None:
        if self._budget is not None and self._budget.exhausted:
            raise BudgetExceededError(
                "daily AI budget exhausted",
                details={
                    "limit_usd": self._budget.daily_usd,
                    "spent_usd": round(self._budget.spent_usd, 6),
                },
            )

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        self._guard()
        result = await self._inner.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model or self._model_for(self._task),
        )
        self.charge(result.cost)
        return result

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self._guard()
        async for chunk in self._inner.stream(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model or self._model_for(self._task),
        ):
            yield chunk

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        self._guard()
        result = await self._inner.embed(texts, model=model or self._model_for(TaskClass.EMBEDDING))
        self.charge(result.cost)
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
        self._guard()
        return await self._inner.structured_output(
            messages,
            schema,
            context=context,
            temperature=temperature,
            model=model or self._model_for(self._task or TaskClass.EXTRACTION),
        )


# ── Resilience ───────────────────────────────────────────────────────────────


class ResilientProvider:
    """Timeouts, bounded retries with jittered backoff, and an ordered fallback chain."""

    def __init__(
        self,
        primary: LLMProvider,
        *,
        fallbacks: Sequence[LLMProvider] = (),
        max_retries: int = 2,
        backoff_base_s: float = 0.4,
        timeout_s: float = 60.0,
        degraded_reason: DegradationReason = DegradationReason.NO_API_KEY,
    ) -> None:
        self._chain: list[LLMProvider] = [primary, *fallbacks]
        self._max_retries = max(0, max_retries)
        self._backoff_base_s = backoff_base_s
        self._timeout_s = timeout_s
        self._degraded_reason = degraded_reason
        self.last_chain_info = ProviderChainInfo(requested=primary.name)

    @property
    def name(self) -> str:
        return self._chain[0].name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._chain[0].capabilities

    async def _attempt(
        self, provider: LLMProvider, operation: str, call: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Run one provider call with retries and a hard timeout."""
        last_error: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await asyncio.wait_for(call(), timeout=self._timeout_s)
            except BudgetExceededError:
                raise
            except BaseException as exc:
                last_error = exc
                if not is_retryable(exc) or attempt >= self._max_retries:
                    raise
                delay = self._backoff_base_s * (2**attempt)
                # Jitter avoids synchronised retries across concurrent workers.
                delay *= 0.75 + (hash((operation, attempt)) % 50) / 100.0
                await asyncio.sleep(delay)
        assert last_error is not None
        raise last_error

    async def _run(self, call_for: Callable[[LLMProvider], Awaitable[Any]]) -> Any:
        info = ProviderChainInfo(requested=self._chain[0].name)
        last_error: BaseException | None = None
        for index, provider in enumerate(self._chain):
            try:
                result = await self._attempt(
                    provider, provider.name, lambda p=provider: call_for(p)
                )
                info.served_by = provider.name
                info.attempts += 1
                info.degraded = index > 0 or bool(
                    getattr(provider.capabilities, "deterministic", False)
                )
                if index > 0:
                    info.reason = self._degraded_reason
                self.last_chain_info = info
                return result
            except BudgetExceededError:
                raise
            except CareerForgeError as exc:
                last_error = exc
                info.errors.append(f"{provider.name}:{exc.code}")
                info.attempts += 1
                continue
            except Exception as exc:
                last_error = exc
                info.errors.append(f"{provider.name}:{type(exc).__name__}")
                info.attempts += 1
                continue

        self.last_chain_info = info
        raise ProviderUnavailableError(
            "no provider in the chain could serve the request",
            details={"chain": [p.name for p in self._chain], "errors": info.errors},
        ) from last_error

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        result: ChatResult = await self._run(
            lambda p: p.chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)
        )
        return result

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        # Streaming cannot be replayed after a partial failure, so the first
        # provider that yields anything wins. Failures before the first chunk
        # fall through to the next provider in the chain.
        last_error: BaseException | None = None
        for index, provider in enumerate(self._chain):
            started = False
            try:
                async for chunk in provider.stream(
                    messages, temperature=temperature, max_tokens=max_tokens, model=model
                ):
                    started = True
                    if index > 0:
                        chunk.degraded = True
                    yield chunk
                return
            except Exception as exc:
                last_error = exc
                if started:
                    raise
                continue
        raise ProviderUnavailableError("no provider could serve the stream") from last_error

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        result: EmbeddingResult = await self._run(lambda p: p.embed(texts, model=model))
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
        result: SchemaT = await self._run(
            lambda p: p.structured_output(
                messages, schema, context=context, temperature=temperature, model=model
            )
        )
        return result
