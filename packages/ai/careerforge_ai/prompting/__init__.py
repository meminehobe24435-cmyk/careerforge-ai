"""Versioned prompt registry (see :mod:`careerforge_ai.prompting.registry`)."""

from __future__ import annotations

from careerforge_ai.prompting.registry import (
    PROMPT_NAMES,
    PromptRegistry,
    PromptTemplate,
    RenderedPrompt,
    find_prompt_values,
    load_prompt_registry,
)

__all__ = [
    "PROMPT_NAMES",
    "PromptRegistry",
    "PromptTemplate",
    "RenderedPrompt",
    "find_prompt_values",
    "load_prompt_registry",
]
