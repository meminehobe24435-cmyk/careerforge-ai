"""Provider factory: build the composed provider chain from settings.

Composition (ADR-009)::

    Resilient(
        Routed(Cached(primary)),
        fallbacks=[Routed(Cached(fallback)), HeuristicProvider()],
    )

The heuristic provider is *always* the tail of the chain. That is the structural
guarantee behind "this product works with zero API keys": no configuration can
remove the last resort, and anything served by it is flagged ``degraded``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import assert_never

from careerforge_ai.config import ProviderName, Settings
from careerforge_ai.providers.base import LLMProvider
from careerforge_ai.providers.decorators import (
    CachedProvider,
    CacheStore,
    InMemoryCacheStore,
    ResilientProvider,
    RoutedProvider,
    TaskClass,
)
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.providers.openai_compat import OllamaProvider, OpenAICompatProvider
from careerforge_ai.schemas.common import CacheKind, DegradationReason

__all__ = ["build_provider", "build_single_provider", "default_model_routing"]


def default_model_routing(settings: Settings) -> dict[str, str]:
    """Task class → model name. Empty values fall back to the provider default."""
    return {
        TaskClass.EXTRACTION: settings.route_extraction_model or "",
        TaskClass.GENERATION: settings.route_generation_model or "",
        TaskClass.INTERVIEW: settings.route_interview_model or "",
        TaskClass.EMBEDDING: settings.embedding_model,
    }


def build_single_provider(name: ProviderName, settings: Settings) -> LLMProvider | None:
    """Instantiate one provider, or ``None`` when it is not configured."""
    if name == "heuristic":
        return HeuristicProvider()

    if name == "deepseek":
        if not settings.deepseek_api_key:
            return None
        return OpenAICompatProvider(
            name="deepseek",
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            timeout_s=settings.ai_request_timeout_seconds,
            supports_native_json_schema=True,
        )

    if name == "openai":
        if not settings.openai_api_key:
            return None
        return OpenAICompatProvider(
            name="openai",
            base_url=settings.openai_base_url,
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            timeout_s=settings.ai_request_timeout_seconds,
            supports_native_json_schema=True,
        )

    if name == "ollama":
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dim,
            timeout_s=max(settings.ai_request_timeout_seconds, 120.0),
        )

    # Every provider name is handled above. ``assert_never`` states that to the type
    # checker: adding a fifth provider now fails the build here rather than at runtime,
    # where an unhandled name would look like "this provider is not configured".
    assert_never(name)


def build_provider(
    settings: Settings | None = None,
    *,
    cache_store: CacheStore | None = None,
    routing: Mapping[str, str] | None = None,
    budget: object | None = None,
    cache_enabled: bool = True,
) -> ResilientProvider:
    """Build the composed provider chain described in the module docstring."""
    from careerforge_ai.config import get_settings as _get_settings

    resolved = settings or _get_settings()
    store = cache_store or InMemoryCacheStore(kind=CacheKind.LLM)
    model_routing = dict(routing or default_model_routing(resolved))

    chain_names = resolved.active_provider_chain()
    primaries: list[LLMProvider] = []
    for name in chain_names:
        instance = build_single_provider(name, resolved)
        if instance is None:
            continue
        wrapped: LLMProvider = CachedProvider(
            instance,
            store=store,
            ttl_seconds=resolved.cache_ttl_llm_seconds,
            embedding_ttl_seconds=resolved.cache_ttl_embedding_seconds,
            enabled=cache_enabled,
        )
        if name != "heuristic":
            wrapped = RoutedProvider(
                wrapped,
                model_by_task={key: value for key, value in model_routing.items() if value},
                budget=budget,  # type: ignore[arg-type]
            )
        primaries.append(wrapped)

    if not primaries:  # pragma: no cover - defensive: heuristic is always buildable
        primaries.append(CachedProvider(HeuristicProvider(), store=store, enabled=False))

    primary, *fallbacks = primaries
    reason = (
        DegradationReason.NO_API_KEY
        if primary.name == "heuristic"
        else DegradationReason.PROVIDER_ERROR
    )
    return ResilientProvider(
        primary,
        fallbacks=fallbacks,
        max_retries=resolved.ai_max_retries,
        timeout_s=resolved.ai_request_timeout_seconds,
        degraded_reason=reason,
    )
