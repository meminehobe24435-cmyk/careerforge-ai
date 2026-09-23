"""Provider decorators: caching, routing and resilience.

Composition order matters and is deliberate (ADR-009)::

    Resilient(Routed(Cached(primary)), fallbacks=[..., HeuristicProvider()])

* **Caching** sits closest to the provider so a cache hit avoids routing and
  resilience work entirely.
* **Routing** picks a model per task class and enforces the budget guardrail.
* **Resilience** wraps the whole chain, so the outermost layer carries the
  guarantee that something always comes back.

This module is a barrel: the implementations live in :mod:`caching`,
:mod:`routing` and :mod:`resilience` so that no single file has to hold all three
concerns.
"""

from __future__ import annotations

from careerforge_ai.providers.caching import (
    CachedProvider,
    CacheStore,
    InMemoryCacheStore,
)
from careerforge_ai.providers.resilience import ResilientProvider
from careerforge_ai.providers.routing import Budget, RoutedProvider, TaskClass

__all__ = [
    "Budget",
    "CacheStore",
    "CachedProvider",
    "InMemoryCacheStore",
    "ResilientProvider",
    "RoutedProvider",
    "TaskClass",
]
