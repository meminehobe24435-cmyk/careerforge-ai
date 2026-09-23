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
from careerforge_ai.schemas.observability import Cost, TokenUsage

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
    "messages_to_text",
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
    """The only interface the AI core knows about a language model."""

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


def messages_to_text(messages: Sequence[ChatMessage], *, limit: int = 8000) -> str:
    """Flatten a conversation into plain text.

    Used by providers that need the raw payload (the heuristic provider, token
    estimation, digesting) rather than a chat structure.
    """
    parts = [f"{message.role.value}: {message.content}" for message in messages]
    joined = "\n".join(parts)
    return joined[:limit]
