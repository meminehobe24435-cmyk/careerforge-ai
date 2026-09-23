"""Model price table and cost arithmetic.

The numbers below are **default reference prices**, not measured facts: vendors
change them. They live in one place, carry a version, and every cost figure the
product reports is derived from this table so the provenance is unambiguous.
Override them with the ``*_PRICE_*`` environment variables, or extend
:data:`PRICE_TABLE` for a new provider.

Costs are computed as ``tokens / 1e6 × price_per_million``. Embedding-only models
reuse the input column.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from careerforge_ai.schemas.observability import Cost, TokenUsage

__all__ = [
    "PRICE_TABLE",
    "PRICE_TABLE_VERSION",
    "USD_TO_CNY",
    "ModelPrice",
    "cost_for",
    "price_for",
]

PRICE_TABLE_VERSION = "pricing@1.0.0"

#: Conversion used to report a CNY figure alongside USD. Configurable because a
#: fixed rate in code would silently rot.
USD_TO_CNY = 7.20

_TOKENS_PER_UNIT = 1_000_000.0


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Price per one million tokens, in USD."""

    input_per_million: float = 0.0
    output_per_million: float = 0.0
    cached_input_per_million: float | None = None
    notes: str = ""

    def cost_for(self, usage: TokenUsage) -> Cost:
        """Cost of a single call. A cached response costs nothing by definition."""
        if usage.total_tokens == 0:
            return Cost(price_table_version=PRICE_TABLE_VERSION)
        usd = (
            usage.prompt_tokens / _TOKENS_PER_UNIT * self.input_per_million
            + usage.completion_tokens / _TOKENS_PER_UNIT * self.output_per_million
        )
        return Cost(
            usd=round(usd, 8),
            cny=round(usd * USD_TO_CNY, 6),
            currency="USD",
            price_table_version=PRICE_TABLE_VERSION,
        )

    def saved_by_cache(self, usage: TokenUsage) -> Cost:
        """What a cache hit avoided spending."""
        return self.cost_for(usage)


#: ``(provider, model) → price``. Lookup is exact first, then by provider prefix.
PRICE_TABLE: Mapping[tuple[str, str], ModelPrice] = {
    # DeepSeek — reference prices as published for the chat model.
    ("deepseek", "deepseek-chat"): ModelPrice(0.27, 1.10, 0.07, "DeepSeek chat reference price"),
    ("deepseek", "deepseek-reasoner"): ModelPrice(
        0.55, 2.19, 0.14, "DeepSeek reasoner reference price"
    ),
    # OpenAI.
    ("openai", "gpt-4o-mini"): ModelPrice(0.15, 0.60, 0.075, "OpenAI GPT-4o mini reference price"),
    ("openai", "gpt-4o"): ModelPrice(2.50, 10.00, 1.25, "OpenAI GPT-4o reference price"),
    ("openai", "text-embedding-3-small"): ModelPrice(
        0.02, 0.0, None, "Embedding: input column only"
    ),
    ("openai", "text-embedding-3-large"): ModelPrice(
        0.13, 0.0, None, "Embedding: input column only"
    ),
    # Local inference is free at the margin (electricity, not tokens).
    ("ollama", "*"): ModelPrice(0.0, 0.0, None, "Local inference — no per-token cost"),
    # The heuristic provider occupies no tokens at all.
    ("heuristic", "*"): ModelPrice(0.0, 0.0, None, "Deterministic rules — no model call"),
}

_DEFAULT_PRICE = ModelPrice(
    0.0, 0.0, None, "Unknown model — cost reported as zero rather than guessed"
)


def price_for(provider: str, model: str | None) -> ModelPrice:
    """Look up a price, preferring an exact match, then a provider wildcard."""
    provider_key = (provider or "").strip().lower()
    model_key = (model or "").strip()

    exact = PRICE_TABLE.get((provider_key, model_key))
    if exact is not None:
        return exact

    wildcard = PRICE_TABLE.get((provider_key, "*"))
    if wildcard is not None:
        return wildcard

    # Prefix match handles versioned model names such as ``gpt-4o-mini-2024-07-18``.
    for (candidate_provider, candidate_model), price in PRICE_TABLE.items():
        if candidate_provider != provider_key or candidate_model == "*":
            continue
        if model_key.startswith(candidate_model):
            return price

    return _DEFAULT_PRICE


def cost_for(provider: str, model: str | None, usage: TokenUsage) -> Cost:
    return price_for(provider, model).cost_for(usage)
