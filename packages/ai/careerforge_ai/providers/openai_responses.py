"""Reading the OpenAI chat-completions wire format.

Split out of :mod:`careerforge_ai.providers.openai_compat` when PHASE 13's usage envelope pushed that
module past the file-length gate, and along the seam that was already there: this module knows what a
vendor's response *looks like* (choices, deltas, the ``usage`` object in its two dialects), while the
provider module knows how to talk to an endpoint, wrap it in a decorator chain and represent the
result as domain value objects.

The one thing worth stating about the usage helpers: they never invent a number. When a vendor omits
``prompt_tokens`` the estimate is computed locally and marked estimated; when it omits
``prompt_tokens_details``/``prompt_cache_hit_tokens`` the cached count comes back as ``None`` rather
than ``0``, because "not reported" and "nothing was cached" are different facts (PHASE 13).
"""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any

from careerforge_ai.providers.base import ChatMessage
from careerforge_ai.providers.tokens import estimate_messages_tokens, estimate_tokens
from careerforge_ai.schemas.observability import TokenUsage

__all__ = [
    "first_choice_content",
    "first_choice_finish",
    "first_delta",
    "loads_json_object",
    "reports_cached_tokens",
    "usage_from",
]


def first_choice_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    # Some vendors return content parts as a list.
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return ""


def first_choice_finish(data: dict[str, Any]) -> str | None:
    choices = data.get("choices") or []
    if not choices:
        return None
    finish = choices[0].get("finish_reason")
    return finish if isinstance(finish, str) else None


def first_delta(chunk: dict[str, Any]) -> str:
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def _cached_count(usage: dict[str, Any]) -> int | None:
    """How many prompt tokens the vendor served from its own cache, or ``None``.

    Two dialects, both real: OpenAI nests it under ``prompt_tokens_details`` while DeepSeek
    reports ``prompt_cache_hit_tokens`` at the top level. A vendor that reports neither returns
    ``None`` — not ``0`` — so the envelope can say "not reported" instead of claiming that
    nothing was cached.
    """
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        cached = details.get("cached_tokens")
        if isinstance(cached, int):
            return max(0, cached)
    for key in ("prompt_cache_hit_tokens", "cache_read_input_tokens", "cached_tokens"):
        cached = usage.get(key)
        if isinstance(cached, int):
            return max(0, cached)
    return None


def reports_cached_tokens(data: dict[str, Any]) -> bool:
    """Whether the vendor's response carried a cached-prompt token count at all."""
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return False
    return _cached_count(usage) is not None


def usage_from(data: dict[str, Any], messages: Sequence[ChatMessage], content: str) -> TokenUsage:
    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total = usage.get("total_tokens")
    cached = _cached_count(usage) or 0
    if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=int(total)
            if isinstance(total, int)
            else prompt_tokens + completion_tokens,
            cached_tokens=cached,
            estimated=False,
        )
    estimated_prompt = estimate_messages_tokens([message.content for message in messages])
    estimated_completion = estimate_tokens(content)
    return TokenUsage(
        prompt_tokens=estimated_prompt,
        completion_tokens=estimated_completion,
        total_tokens=estimated_prompt + estimated_completion,
        cached_tokens=cached,
        estimated=True,
    )


def loads_json_object(content: str) -> dict[str, Any]:
    """Extract a JSON object from a model response.

    Handles the common deviations (fenced blocks, leading prose) without
    accepting anything that is not a JSON object.
    """
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        text = text.removeprefix("json").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("response contained no JSON object")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("response JSON was not an object")
    return parsed
