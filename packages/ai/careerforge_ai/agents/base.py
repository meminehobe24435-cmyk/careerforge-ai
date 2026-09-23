"""Agent building blocks.

An "agent" in this codebase is not a chat loop. It is a named workflow plus the
prompt context that workflow needs — nothing more. That definition keeps three
properties that matter: an agent can be unit-tested with fake ports, its cost is
attributable because every step lands in a trace, and a reader can see the whole
control flow in one screen.

Every agent receives its dependencies through :class:`RunContext` rather than
importing them, and every model call goes through :meth:`RunContext.structured`,
which is what keeps prompts in the registry and output schema-validated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Protocol

from careerforge_ai.orchestrator import Workflow, WorkflowExecutor, WorkflowOutput
from careerforge_ai.schemas.common import DegradationReason

__all__ = [
    "Agent",
    "AgentOutcome",
    "strip_markup",
    "normalise_whitespace",
    "render_bullets",
    "truncate_for_prompt",
    "PROMPT_CHAR_BUDGET",
]

#: Characters of candidate material to place in a prompt. Retrieval Top-K is the
#: primary context control; this is the backstop that stops one enormous document
#: from silently costing ten times the tokens of a normal request.
PROMPT_CHAR_BUDGET = 6000

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_ENTITY_RE = re.compile(r"&(nbsp|amp|lt|gt|quot|#39|#\d+);")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+$", re.MULTILINE)

_ENTITIES = {
    "nbsp": " ",
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "#39": "'",
}


@dataclass(slots=True)
class AgentOutcome:
    """What an agent call returns: the value, the trace, and its honesty flags."""

    value: Any
    record: Any = None
    degraded: bool = False
    degradation_reason: DegradationReason = DegradationReason.NONE
    warnings: list[str] = field(default_factory=list)
    #: Secondary products of the run that a caller may want without unpacking the
    #: trace — a gap matrix alongside a learning plan, for instance.
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.record is None or self.record.status in {"succeeded", "degraded"}

    def step_output(self, name: str) -> Any:
        if self.record is None:
            return None
        return next((step for step in self.record.steps if step.name == name), None)


class Agent(Protocol):
    """Minimal contract every agent satisfies."""

    name: str

    def workflow(self) -> Workflow: ...

    async def run(self, executor: WorkflowExecutor, **inputs: Any) -> AgentOutcome: ...


# ── deterministic text preparation ───────────────────────────────────────────


def strip_markup(text: str) -> str:
    """Remove HTML/script/style content and decode the common entities.

    Job descriptions arrive as pasted web pages often enough that handling this
    deterministically — rather than hoping the model ignores the markup — is
    worth a dozen lines. Script and style bodies are removed *with* their
    contents, since their text is not part of the posting.
    """
    if not text:
        return ""
    text = _SCRIPT_STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub("\n", text)
    return _ENTITY_RE.sub(lambda match: _ENTITIES.get(match.group(1), " "), text)


def normalise_whitespace(text: str) -> str:
    """Collapse runs of blank lines and strip trailing spaces.

    Line structure is preserved because section detection depends on it; only the
    pathological spacing that pasted content carries is removed.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_SPACE_RE.sub("", text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def render_bullets(items: list[str] | tuple[str, ...], *, prefix: str = "- ") -> str:
    """Render a list for a prompt, or a placeholder when it is empty.

    The placeholder matters: an empty section in a prompt reads as "no constraints",
    whereas the model should be told explicitly that there is nothing here.
    """
    cleaned = [item.strip() for item in items if item and item.strip()]
    if not cleaned:
        return "（无）"
    return "\n".join(f"{prefix}{item}" for item in cleaned)


def truncate_for_prompt(text: str, *, budget: int = PROMPT_CHAR_BUDGET) -> tuple[str, bool]:
    """Clip prompt context to a character budget.

    Returns ``(text, truncated)`` so the caller can surface the truncation rather
    than silently answering a question with half the material.
    """
    if len(text) <= budget:
        return text, False
    head = int(budget * 0.7)
    tail = budget - head
    return f"{text[:head]}\n…（内容过长，中间部分已省略）…\n{text[-tail:]}", True


def merge_workflow_warnings(output: WorkflowOutput) -> list[str]:
    """Collect per-step degradation notes so an agent can report them upward."""
    warnings: list[str] = []
    if output.degraded:
        warnings.append(f"结果已降级（原因：{output.degradation_reason.value}）")
    for step in output.record.steps if output.record is not None else ():
        if step.status == "degraded":
            warnings.append(f"步骤 {step.name} 降级：{step.error_message or '未提供详情'}")
    return warnings
