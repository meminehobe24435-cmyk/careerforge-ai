"""Persistence layer: engine/session, type compatibility, declarative base, models.

The layering is deliberate (``docs/ARCHITECTURE.md`` §1.2): models know nothing
about the HTTP layer, repositories know nothing about SQL beyond their own queries,
and services compose repositories.
"""

from __future__ import annotations

__all__: list[str] = []
