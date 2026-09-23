"""Generic schema synthesiser.

The last resort when no handler exists for a requested schema: walk the model's
fields and build the minimal valid instance. The result is schema-valid and
intentionally empty.

This is a deliberate product decision, not laziness. In a system whose entire
premise is that unverifiable claims are worthless, a fallback that invented
plausible-looking content would undermine the thing being built.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

__all__ = ["synthesize_model"]

#: Guards against a self-referential schema producing infinite recursion.
_MAX_DEPTH = 6


def _synthesize_value(annotation: Any, seed: str, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        return None

    origin = getattr(annotation, "__origin__", None)
    args = getattr(annotation, "__args__", ())

    # Optional[X] / Union[X, None] — the annotation may be a typing special form
    # whose origin renders as ``typing.Union`` on older Pythons.
    if origin is not None and str(origin).endswith("Union"):
        non_none = [arg for arg in args if arg is not type(None)]
        return _synthesize_value(non_none[0], seed, depth + 1) if non_none else None

    if origin in (list, tuple, set, frozenset):
        return []
    if origin is dict:
        return {}

    if isinstance(annotation, type):
        if issubclass(annotation, StrEnum):
            members = list(annotation)
            return members[0] if members else None
        if issubclass(annotation, BaseModel):
            return synthesize_model(annotation, seed, depth + 1)
        if annotation is str:
            return ""
        if annotation is bool:
            return False
        if annotation is int:
            return 0
        if annotation is float:
            return 0.0
        if annotation is bytes:
            return b""
    return None


def _fill_required(field: FieldInfo, seed: str, depth: int) -> Any:
    annotation = field.annotation
    if annotation is None:
        return None
    return _synthesize_value(annotation, seed, depth + 1)


def synthesize_model(schema: type[BaseModel], seed: str, depth: int = 0) -> BaseModel:
    """Construct the minimal valid instance of ``schema``."""
    payload: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if not field.is_required():
            continue
        payload[name] = _fill_required(field, seed, depth)
    return schema.model_validate(payload)
