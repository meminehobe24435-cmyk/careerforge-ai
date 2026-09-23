"""Pluggable LLM providers.

Import surface for the rest of the codebase: build a chain with
:func:`build_provider` and depend only on the :class:`LLMProvider` protocol.
Nothing outside this package may import a vendor SDK or know a model name.
"""

from __future__ import annotations

from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    ChatRole,
    EmbeddingResult,
    LLMProvider,
    ProviderCapabilities,
    ProviderChainInfo,
    StreamChunk,
    StructuredContext,
    messages_to_text,
)
from careerforge_ai.providers.decorators import (
    Budget,
    CachedProvider,
    CacheStore,
    InMemoryCacheStore,
    ResilientProvider,
    RoutedProvider,
    TaskClass,
)
from careerforge_ai.providers.factory import build_provider, build_single_provider
from careerforge_ai.providers.heuristic import (
    HEURISTIC_HANDLERS,
    HeuristicProvider,
    heuristic_embedding,
)
from careerforge_ai.providers.openai_compat import OllamaProvider, OpenAICompatProvider
from careerforge_ai.providers.tokens import estimate_messages_tokens, estimate_tokens

__all__ = [
    "HEURISTIC_HANDLERS",
    "Budget",
    "CacheStore",
    "CachedProvider",
    "ChatMessage",
    "ChatResult",
    "ChatRole",
    "EmbeddingResult",
    "HeuristicProvider",
    "InMemoryCacheStore",
    "LLMProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "ProviderCapabilities",
    "ProviderChainInfo",
    "ResilientProvider",
    "RoutedProvider",
    "StreamChunk",
    "StructuredContext",
    "TaskClass",
    "build_provider",
    "build_single_provider",
    "estimate_messages_tokens",
    "estimate_tokens",
    "heuristic_embedding",
    "messages_to_text",
]
