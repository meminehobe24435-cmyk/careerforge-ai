"""Handler registry for the heuristic provider.

A handler is a deterministic function that produces a useful instance of one
schema. When no handler exists for a requested schema, the provider falls back to
the generic synthesiser, which returns a *valid but empty* object — an honest
answer, rather than invented content in a product about verifiable evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel

__all__ = ["HEURISTIC_HANDLERS", "HeuristicHandler", "handles"]

#: ``schema class name`` → handler. Keyed by name so handlers can live in
#: separate modules without importing each other's schemas.
HeuristicHandler = Callable[[str, Mapping[str, Any]], BaseModel]

HEURISTIC_HANDLERS: dict[str, HeuristicHandler] = {}


def handles(schema: type[BaseModel]) -> Callable[[HeuristicHandler], HeuristicHandler]:
    """Register a handler for ``schema``.

    Registration is by class *name* rather than by class object so that a handler
    module can be imported (and its schema resolved) without a circular import.
    """

    def decorator(func: HeuristicHandler) -> HeuristicHandler:
        HEURISTIC_HANDLERS[schema.__name__] = func
        return func

    return decorator
