"""Result caching for providers.

Sits closest to the provider in the decorator stack so that a cache hit avoids
routing and resilience work entirely. Cache keys include the provider, the model
and the full prompt, so a prompt or model change can never be served a stale
answer — the failure mode that makes naive LLM caches dangerous.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
import hashlib
import time
from typing import Any, Protocol

from pydantic import BaseModel

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
from careerforge_ai.schemas.common import CacheKind
from careerforge_ai.schemas.observability import CacheStats, Cost, TokenUsage

__all__ = ["CacheStore", "InMemoryCacheStore", "CachedProvider"]


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

    Streaming deliberately bypasses the cache: replaying a cached stream would
    misreport latency and hide the cache from the user, which defeats the point
    of the hit-rate dashboard.
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
                repr(schema.model_json_schema()),
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
            # Token usage on a hit is reported as estimated-zero: the call cost
            # nothing, and claiming the original usage would corrupt the ledger.
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
