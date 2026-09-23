"""Token estimation for chat payloads.

Single-text estimation lives in :mod:`careerforge_ai.parsing.tokenize` so that
retrieval and scoring share one definition. This module adds the per-message
overhead that chat-completion APIs charge, which is the only part that is
specific to the provider protocol.

Estimates are always flagged (``TokenUsage.estimated = True``) so a cost
dashboard never presents a guess as a measurement.
"""

from __future__ import annotations

from careerforge_ai.parsing.tokenize import count_cjk_chars, estimate_tokens

__all__ = ["count_cjk_chars", "estimate_messages_tokens", "estimate_tokens"]

#: Per-message chat scaffolding overhead charged by chat-completion APIs.
_MESSAGE_OVERHEAD = 4


def estimate_messages_tokens(texts: list[str]) -> int:
    """Estimate the prompt cost of a message list, including per-message overhead."""
    return sum(estimate_tokens(text) + _MESSAGE_OVERHEAD for text in texts)
