"""Token estimation.

Providers report real usage when they can. When they cannot — the heuristic
provider, or a cached response being replayed — we estimate. Estimates are
always flagged (``TokenUsage.estimated = True``) so a cost dashboard never
presents a guess as a measurement.
"""

from __future__ import annotations

import re

__all__ = ["count_cjk_chars", "estimate_messages_tokens", "estimate_tokens"]

#: CJK ideographs, kana and Hangul are close to one token per character for the
#: tokenizers used by the providers this project targets.
_CJK_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")

#: Rough characters-per-token for latin script prose and source code.
_LATIN_CHARS_PER_TOKEN = 4.0

#: Per-message chat scaffolding overhead charged by chat-completion APIs.
_MESSAGE_OVERHEAD = 4


def count_cjk_chars(text: str) -> int:
    return len(_CJK_PATTERN.findall(text))


def estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text``.

    Deliberately simple and stable: an estimate that is consistent between runs
    is more useful for cost dashboards and cache keys than a marginally more
    accurate one that is expensive to compute.
    """
    if not text:
        return 0
    cjk = count_cjk_chars(text)
    latin_chars = len(text) - cjk
    latin_tokens = latin_chars / _LATIN_CHARS_PER_TOKEN
    return max(1, int(cjk + latin_tokens + 0.5))


def estimate_messages_tokens(texts: list[str]) -> int:
    """Estimate the prompt cost of a message list, including per-message overhead."""
    return sum(estimate_tokens(text) + _MESSAGE_OVERHEAD for text in texts)
