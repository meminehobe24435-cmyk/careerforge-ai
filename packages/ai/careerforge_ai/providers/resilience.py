"""Resilience: timeouts, bounded retries and an ordered fallback chain.

This is the outermost decorator, so it carries the guarantee that matters most in
a demo: *something always comes back*. The tail of the chain is always the
heuristic provider, which means no configuration can turn a missing API key into
a broken page (ADR-009).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Any

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
from careerforge_ai.schemas.common import DegradationReason

__all__ = ["ResilientProvider"]


class ResilientProvider:
    """Tries providers in order until one succeeds, with retries in between."""

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

    @property
    def chain_names(self) -> list[str]:
        return [provider.name for provider in self._chain]

    async def _attempt(
        self, provider: LLMProvider, operation: str, call: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Run one provider call with retries and a hard timeout."""
        last_error: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await asyncio.wait_for(call(), timeout=self._timeout_s)
            except BudgetExceededError:
                # A budget decision is not a transient failure; do not retry it.
                raise
            except BaseException as exc:
                last_error = exc
                if not is_retryable(exc) or attempt >= self._max_retries:
                    raise
                delay = self._backoff_base_s * (2**attempt)
                # Jitter avoids synchronised retries across concurrent workers.
                delay *= 0.75 + (hash((operation, attempt)) % 50) / 100.0
                await asyncio.sleep(delay)
        assert last_error is not None  # unreachable: the loop either returns or raises
        raise last_error

    async def _run(self, call_for: Callable[[LLMProvider], Awaitable[Any]]) -> Any:
        info = ProviderChainInfo(requested=self._chain[0].name)
        last_error: BaseException | None = None

        for index, provider in enumerate(self._chain):
            try:
                result = await self._attempt(
                    provider, provider.name, lambda p=provider: call_for(p)
                )
                info.attempts += 1
                info.served_by = provider.name
                info.degraded = index > 0 or bool(provider.capabilities.deterministic)
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
            except Exception as exc:
                last_error = exc
                info.errors.append(f"{provider.name}:{type(exc).__name__}")
                info.attempts += 1

        self.last_chain_info = info
        raise ProviderUnavailableError(
            "no provider in the chain could serve the request",
            details={"chain": self.chain_names, "errors": info.errors},
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
        """Stream from the first provider that yields anything.

        A stream cannot be replayed after a partial failure — the client has
        already rendered the tokens — so failures before the first chunk fall
        through to the next provider, and failures after it propagate.
        """
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
                self.last_chain_info = ProviderChainInfo(
                    requested=self._chain[0].name,
                    served_by=provider.name,
                    degraded=index > 0,
                    reason=self._degraded_reason if index > 0 else DegradationReason.NONE,
                    attempts=index + 1,
                )
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
