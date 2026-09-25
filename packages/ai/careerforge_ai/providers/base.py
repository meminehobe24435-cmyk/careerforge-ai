"""Provider contracts and value objects.

The provider port is the seam that keeps the product usable in every
environment: DeepSeek and OpenAI when keys exist, a local Ollama for privacy
mode, and a fully deterministic heuristic provider so the system still works
with **no key, no network and no model** (ADR-009).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from careerforge_ai.schemas.common import DegradationReason
from careerforge_ai.schemas.observability import Cost, LLMUsage, TokenUsage

__all__ = [
    "ChatMessage",
    "ChatResult",
    "ChatRole",
    "EmbeddingResult",
    "LLMProvider",
    "ProviderCapabilities",
    "ProviderChainInfo",
    "SchemaT",
    "StreamChunk",
    "StructuredContext",
    "StructuredResult",
    "messages_to_text",
    "structured_output_envelope",
    "supports_usage_envelope",
]

SchemaT = TypeVar("SchemaT", bound=BaseModel)

#: Extra data a port may hand to a provider for structured generation. The
#: heuristic provider uses it to produce genuinely useful (not merely valid)
#: output; network providers ignore it.
StructuredContext = Mapping[str, Any]


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(slots=True, frozen=True)
class ChatMessage:
    role: ChatRole
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role.value, "content": self.content}


@dataclass(slots=True)
class ChatResult:
    """Outcome of a chat completion."""

    content: str
    provider: str
    model: str
    tokens: TokenUsage = field(default_factory=TokenUsage)
    cost: Cost = field(default_factory=Cost)
    latency_ms: int = 0
    cached: bool = False
    degraded: bool = False
    degradation_reason: DegradationReason = DegradationReason.NONE
    finish_reason: str | None = None
    raw_meta: dict[str, Any] = field(default_factory=dict)
    #: The usage envelope for this call. Providers that support the envelope fill it in;
    #: :func:`chat_usage` derives one from ``tokens``/``cost`` for those that do not.
    usage: LLMUsage | None = None
    request_id: str | None = None

    def envelope(self) -> LLMUsage:
        """This call's usage, as fact / estimate / unknown."""
        if self.usage is not None:
            return self.usage.with_request(self.request_id, self.model)
        if self.cached:
            return LLMUsage.cached(
                provider=self.provider, model=self.model, request_id=self.request_id
            )
        return LLMUsage.from_token_usage(
            self.tokens,
            self.cost,
            provider=self.provider,
            model=self.model,
            request_id=self.request_id,
        )


@dataclass(slots=True)
class StreamChunk:
    """One streamed fragment. ``done`` marks the terminal chunk."""

    delta: str = ""
    done: bool = False
    provider: str = ""
    model: str = ""
    tokens: TokenUsage = field(default_factory=TokenUsage)
    cost: Cost = field(default_factory=Cost)
    degraded: bool = False
    error_code: str | None = None
    #: ``None`` means the provider said nothing about usage on this stream. The terminal chunk
    #: carries the envelope when the provider has one; a stream that never sets it is reported
    #: as ``unavailable`` rather than as zero tokens (PHASE 13).
    usage: LLMUsage | None = None
    #: ``True`` when the provider actually reported usage for this stream. Needed because a
    #: defaulted ``TokenUsage`` and a reported ``0`` are indistinguishable from the counters
    #: alone, and the difference is the whole point of the envelope.
    usage_reported: bool = False
    request_id: str | None = None
    latency_ms: int = 0

    def envelope(self) -> LLMUsage:
        """This chunk's usage, as fact / estimate / unknown.

        A defaulted ``TokenUsage`` cannot be told apart from a provider that reported zeros, so
        a chunk that carries neither an envelope nor ``usage_reported`` is read as
        ``unavailable``. "The stream happened and we were not told what it cost" is the honest
        reading of a terminal chunk nobody filled in.
        """
        if self.usage is not None:
            return self.usage.with_request(self.request_id, self.model)
        if not self.usage_reported:
            return LLMUsage.unavailable(
                provider=self.provider or None,
                model=self.model or None,
                request_id=self.request_id,
            )
        return LLMUsage.from_token_usage(
            self.tokens,
            self.cost,
            provider=self.provider or None,
            model=self.model or None,
            request_id=self.request_id,
        )


@dataclass(slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    provider: str
    model: str
    dim: int
    tokens: TokenUsage = field(default_factory=TokenUsage)
    cost: Cost = field(default_factory=Cost)
    latency_ms: int = 0
    cached: bool = False
    degraded: bool = False
    #: The same envelope the completion paths carry, so an embedding's usage is reported in
    #: one shape. An embedding also sets ``usage.status`` to ``cached`` when served from the cache.
    usage: LLMUsage | None = None

    def envelope(self) -> LLMUsage:
        if self.usage is not None:
            return self.usage
        if self.cached:
            return LLMUsage.cached(provider=self.provider, model=self.model)
        return LLMUsage.from_token_usage(
            self.tokens, self.cost, provider=self.provider, model=self.model
        )


@dataclass(slots=True, frozen=True)
class ProviderCapabilities:
    """What a provider can actually do — used for honest degradation decisions."""

    name: str
    supports_streaming: bool
    supports_embeddings: bool
    supports_native_json_schema: bool
    requires_api_key: bool = True
    deterministic: bool = False
    notes: str = ""
    #: Whether the provider's responses carry a cached-prompt token count. ``False`` means
    #: "not reported", not "nothing was cached": OpenAI and DeepSeek report it, Ollama and the
    #: heuristic provider do not, and the cost page says so instead of printing a 0 that reads
    #: as a measurement (PHASE 13).
    reports_cached_tokens: bool = False
    #: Whether the provider can answer :meth:`LLMProvider.structured_output_envelope`. ``False``
    #: is not an error: the envelope falls back to ``usage_status="unavailable"``, which is the
    #: honest report for a provider that does not tell us what it spent.
    supports_usage_envelope: bool = False


@dataclass(slots=True)
class StructuredResult[ValueT]:
    """A structured generation and the usage envelope for the call that produced it.

    The counterpart of :class:`ChatResult` for the structured path. It exists because the
    parsed schema alone cannot carry usage, and dropping the provider's usage object was a
    measured defect rather than a design choice: every agent in the product uses this path,
    so every run recorded zero tokens (``docs/QUALITY.md`` §7.1 / ROADMAP PHASE 12 #13).
    """

    value: ValueT
    usage: LLMUsage = field(default_factory=LLMUsage)

    @property
    def provider(self) -> str | None:
        return self.usage.provider

    @property
    def model(self) -> str | None:
        return self.usage.model


@dataclass(slots=True)
class ProviderChainInfo:
    """Diagnostics about which provider actually served a call.

    Populated by the resilience decorator and surfaced on API responses as
    ``meta.degraded`` so a fallback is always visible to the user rather than
    silently changing the quality of an answer.
    """

    requested: str = ""
    served_by: str = ""
    degraded: bool = False
    reason: DegradationReason = DegradationReason.NONE
    attempts: int = 0
    errors: list[str] = field(default_factory=list)


@runtime_checkable
class LLMProvider(Protocol):
    """The only interface the AI core knows about a language model.

    :meth:`structured_output` returns the parsed schema and nothing else, because that is the
    contract every existing provider and caller was written against. A provider that can also
    tell us what the call cost implements :class:`LLMWithUsage` as well, and
    :meth:`RunContext.structured <careerforge_ai.orchestrator.RunContext.structured>` picks the
    usage up when it is there. The alternative considered and rejected was changing
    ``structured_output``'s return type to a wrapper: that would have broken every provider,
    every decorator and every direct call site at once, for a benefit only observability reads.
    """

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult: ...

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]: ...

    async def embed(
        self,
        texts: Sequence[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult: ...

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> SchemaT: ...


@runtime_checkable
class LLMWithUsage(Protocol):
    """A provider that can report usage for a structured call (PHASE 13)."""

    async def structured_output_envelope(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> StructuredResult[SchemaT]: ...


def supports_usage_envelope(provider: object) -> bool:
    """Whether ``provider`` can answer :meth:`LLMWithUsage.structured_output_envelope`.

    Checked with ``getattr`` rather than ``isinstance`` against the protocol: a decorator in this
    stack delegates unknown attributes to its inner provider, and ``isinstance`` would call that
    ``__getattr__`` while probing — reading a capability as a side effect of asking about it. The
    attribute itself is still the contract; only the way it is asked about changed.
    """
    return callable(getattr(provider, "structured_output_envelope", None))


async def structured_output_envelope[EnvelopeT: BaseModel](
    provider: object,
    messages: Sequence[ChatMessage],
    schema: type[EnvelopeT],
    *,
    context: StructuredContext | None = None,
    temperature: float = 0.0,
    model: str | None = None,
) -> StructuredResult[EnvelopeT]:
    """Call the structured path and always come back with an envelope.

    A provider that cannot report usage yields ``usage_status="unavailable"`` — never a
    zero-filled envelope, because ``0`` is a statement about the money and this call has not
    made one. Wrappers and tests can rely on this returning a result for anything the type
    checker accepts as an :class:`LLMProvider`.
    """
    if supports_usage_envelope(provider):
        result: StructuredResult[EnvelopeT] = await provider.structured_output_envelope(  # type: ignore[attr-defined]
            messages, schema, context=context, temperature=temperature, model=model
        )
        return result
    value = await provider.structured_output(  # type: ignore[attr-defined]
        messages, schema, context=context, temperature=temperature, model=model
    )
    name = str(getattr(provider, "name", "") or "") or None
    return StructuredResult(
        value=value,
        usage=LLMUsage.unavailable(provider=name, model=model),
    )


def messages_to_text(messages: Sequence[ChatMessage], *, limit: int = 8000) -> str:
    """Flatten a conversation into plain text.

    Used by providers that need the raw payload (the heuristic provider, token
    estimation, digesting) rather than a chat structure.
    """
    parts = [f"{message.role.value}: {message.content}" for message in messages]
    joined = "\n".join(parts)
    return joined[:limit]
