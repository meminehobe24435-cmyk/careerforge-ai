"""Observability: token accounting, cost arithmetic and run tracking.

This package exists because "how much did that AI feature cost, and where did the
time go" is a product question, not a debugging afterthought. Every workflow in
this codebase emits traces through these primitives, which is what makes the
AI Runs and Cost dashboards real.
"""

from __future__ import annotations

from careerforge_ai.observability.pricing import (
    PRICE_TABLE,
    PRICE_TABLE_VERSION,
    USD_TO_CNY,
    ModelPrice,
    cost_for,
    price_for,
)
from careerforge_ai.observability.tracker import InMemoryTracker, RunTracker, UsageLedger

__all__ = [
    "PRICE_TABLE",
    "PRICE_TABLE_VERSION",
    "USD_TO_CNY",
    "InMemoryTracker",
    "ModelPrice",
    "RunTracker",
    "UsageLedger",
    "cost_for",
    "price_for",
]
