"""Orchestrator primitives: steps, workflows and the run context.

This is a hand-written orchestrator rather than a framework wrapper (ADR-007).
The whole design fits in one idea: **a step is a pure async function with a
declared name, declared dependencies, and declared failure semantics.** Because
each step is an ordinary function, it can be unit-tested in isolation, and
because each step is a named node, it maps one-to-one onto a trace row in the
AI Runs page. Nothing is hidden in framework internals.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import logging
from typing import Any, TypeVar
from uuid import UUID

from pydantic import BaseModel

from careerforge_ai.errors import StepFailedError
from careerforge_ai.observability.pricing import cost_for
from careerforge_ai.prompting.registry import PromptRegistry
from careerforge_ai.providers.base import ChatMessage, ChatRole, LLMProvider, ProviderChainInfo
from careerforge_ai.schemas.common import DegradationReason
from careerforge_ai.schemas.observability import Cost, TokenUsage

__all__ = [
    "RunContext",
    "Step",
    "StepFallback",
    "StepFn",
    "Workflow",
    "WorkflowOutput",
    "digest_of",
]

logger = logging.getLogger("careerforge.orchestrator")

SchemaT = TypeVar("SchemaT", bound=BaseModel)

StepFn = Callable[["RunContext", Mapping[str, Any]], Awaitable[Any]]
StepFallback = Callable[["RunContext", Mapping[str, Any], BaseException], Awaitable[Any]]


def digest_of(payload: Any, *, length: int = 16) -> str:
    """Stable digest of an arbitrary value, used to identify inputs and outputs."""
    try:
        text = json.dumps(payload, sort_keys=True, default=str)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        text = repr(payload)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


@dataclass(slots=True)
class Step:
    """One node of a workflow.

    Attributes:
        name: unique node name inside the workflow; becomes the trace row name.
        fn: the work. Receives the run context and the outputs of its
            dependencies, keyed by step name.
        depends_on: step names that must complete first.
        timeout_s: per-step timeout. Falls back to the run default.
        max_retries: retries for transient failures only. Falls back to default.
        cache_ttl: when set, the step result is cached for this many seconds.
        fallback: invoked when the step fails after retries. Its result is used
            and the step (and run) is marked ``degraded``.
        optional: when true and there is no fallback, a failure is recorded but
            the run continues. Use for enrichment that must not block the goal.
        agent: agent id this step belongs to, for cost attribution.
    """

    name: str
    fn: StepFn
    depends_on: tuple[str, ...] = ()
    timeout_s: float | None = None
    max_retries: int | None = None
    cache_ttl: int | None = None
    fallback: StepFallback | None = None
    optional: bool = False
    agent: str | None = None
    description: str = ""

    def digest_inputs(self, inputs: Mapping[str, Any]) -> str:
        return digest_of(dict(sorted(inputs.items())))


@dataclass(slots=True)
class WorkflowOutput:
    """Everything a workflow produced, plus its trace."""

    record: Any  # AgentRunRecord — typed loosely to avoid a circular import
    outputs: dict[str, Any]
    status: str
    degraded: bool = False
    degradation_reason: DegradationReason = DegradationReason.NONE
    error_code: str | None = None
    error_message: str | None = None
    #: The run context's metadata, including any ``warnings`` steps recorded.
    #: Surfaced so a caller can report a caveat instead of an unqualified success.
    metadata: dict[str, Any] = field(default_factory=dict)

    def get(self, step_name: str, default: Any = None) -> Any:
        return self.outputs.get(step_name, default)

    def output_of(self, step: Step) -> Any:
        return self.outputs.get(step.name)

    @property
    def ok(self) -> bool:
        return self.status in {"succeeded", "degraded"}


@dataclass(slots=True)
class Workflow:
    """A named DAG of steps with a single terminal output.

    The terminal output is simply the step that nothing else depends on; if a
    workflow has several leaves, the first declared one is used and the rest are
    still recorded in the trace.
    """

    name: str
    agent: str
    steps: tuple[Step, ...]
    trigger: str = "api"
    description: str = ""

    def step(self, name: str) -> Step:
        for step in self.steps:
            if step.name == name:
                return step
        raise KeyError(f"workflow {self.name} has no step named {name!r}")

    @property
    def step_names(self) -> tuple[str, ...]:
        return tuple(step.name for step in self.steps)

    def terminal_step(self) -> Step:
        depended_on = {dependency for step in self.steps for dependency in step.depends_on}
        leaves = [step for step in self.steps if step.name not in depended_on]
        if not leaves:
            raise StepFailedError(self.name, "workflow has no terminal step (cycle?)")
        return leaves[-1]

    def validate(self) -> None:
        """Fail fast on a malformed graph — at import time, not at request time."""
        names = self.step_names
        if len(set(names)) != len(names):
            raise StepFailedError(self.name, "duplicate step names")
        known = set(names)
        for step in self.steps:
            unknown = [dependency for dependency in step.depends_on if dependency not in known]
            if unknown:
                raise StepFailedError(
                    self.name, f"step '{step.name}' depends on unknown steps: {unknown}"
                )
        # Kahn's algorithm: leftover nodes mean a cycle.
        indegree = {step.name: len(step.depends_on) for step in self.steps}
        queue = [name for name, degree in indegree.items() if degree == 0]
        visited = 0
        while queue:
            current = queue.pop()
            visited += 1
            for step in self.steps:
                if current in step.depends_on:
                    indegree[step.name] -= 1
                    if indegree[step.name] == 0:
                        queue.append(step.name)
        if visited != len(self.steps):
            raise StepFailedError(self.name, "workflow contains a cycle")

    def layers(self) -> list[list[Step]]:
        """Group steps into dependency layers that may run concurrently."""
        remaining = list(self.steps)
        completed: set[str] = set()
        result: list[list[Step]] = []
        while remaining:
            ready = [step for step in remaining if set(step.depends_on) <= completed]
            if not ready:
                raise StepFailedError(self.name, "workflow contains a cycle")
            result.append(ready)
            for step in ready:
                completed.add(step.name)
                remaining.remove(step)
        return result


@dataclass
class RunContext:
    """Everything a step needs, injected rather than imported.

    Steps never reach for a global: they receive the provider, the prompt
    registry and the ports through this object. That is what makes the AI core
    testable without a database or a network (ADR-022).
    """

    user_id: UUID | None
    request_id: str
    provider: LLMProvider
    prompts: PromptRegistry
    tracker: Any | None = None
    cache: Any | None = None
    services: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    #: Populated by the executor around each step so LLM helpers can attribute
    #: usage to the right trace row without threading counters through calls.
    current_step: str = ""
    _tokens: TokenUsage = field(default_factory=TokenUsage)
    _cost: Cost = field(default_factory=Cost)
    _chain: ProviderChainInfo | None = None

    # ── service access ───────────────────────────────────────────────────────

    def service(self, key: str) -> Any:
        value = self.services.get(key)
        if value is None:
            raise KeyError(f"service '{key}' was not provided to this run")
        return value

    def maybe_service(self, key: str) -> Any | None:
        return self.services.get(key)

    # ── usage accounting ─────────────────────────────────────────────────────

    def reset_usage(self) -> None:
        self._tokens = TokenUsage()
        self._cost = Cost()

    def add_usage(self, tokens: TokenUsage, cost: Cost) -> None:
        self._tokens = self._tokens.merged(tokens)
        self._cost = self._cost + cost
        if isinstance(self.cache, Any) and self._chain is not None:
            self.metadata["provider_chain"] = self._chain

    @property
    def usage(self) -> tuple[TokenUsage, Cost]:
        return self._tokens, self._cost

    @property
    def degraded(self) -> bool:
        chain = self._chain
        return bool(chain and chain.degraded)

    @property
    def degradation_reason(self) -> DegradationReason:
        chain = self._chain
        if chain and chain.degraded:
            return chain.reason
        return DegradationReason.NONE

    def note_provider_chain(self, chain: ProviderChainInfo) -> None:
        self._chain = chain

    # ── LLM helpers ──────────────────────────────────────────────────────────

    async def structured(
        self,
        prompt_name: str,
        schema: type[SchemaT],
        *,
        prompt_version: int | None = None,
        context: Mapping[str, Any] | None = None,
        **variables: Any,
    ) -> SchemaT:
        """Render a registered prompt and get schema-validated output.

        This is the *only* sanctioned way for a step to talk to a model. It keeps
        three guarantees in one place: prompts come from the registry (never
        inline strings), output is schema-validated by the provider, and usage is
        charged to the current step's trace.
        """
        rendered = self.prompts.render(prompt_name, version=prompt_version, **variables)
        messages: Sequence[ChatMessage] = rendered.messages()
        result = await self.provider.structured_output(
            messages, schema, context=dict(context or {})
        )

        chain = getattr(self.provider, "last_chain_info", None)
        chain_info: ProviderChainInfo | None = (
            chain if isinstance(chain, ProviderChainInfo) else None
        )
        if chain_info is not None:
            self.note_provider_chain(chain_info)

        # Structured calls report usage through the chain; when the underlying
        # provider does not (cached hits, heuristic), estimation already
        # happened there, so nothing further is added here.
        self.metadata.setdefault("prompt_refs", []).append(rendered.ref)
        return result

    async def chat(
        self,
        prompt_name: str,
        *,
        prompt_version: int | None = None,
        temperature: float = 0.2,
        **variables: Any,
    ) -> str:
        rendered = self.prompts.render(prompt_name, version=prompt_version, **variables)
        result = await self.provider.chat(rendered.messages(), temperature=temperature)
        self.add_usage(result.tokens, result.cost)
        chain = getattr(self.provider, "last_chain_info", None)
        if isinstance(chain, ProviderChainInfo):
            self.note_provider_chain(chain)
        return result.content

    @staticmethod
    def system(content: str) -> ChatMessage:
        return ChatMessage(role=ChatRole.SYSTEM, content=content)

    @staticmethod
    def user(content: str) -> ChatMessage:
        return ChatMessage(role=ChatRole.USER, content=content)

    # ── convenience ──────────────────────────────────────────────────────────

    def require(self, mapping: Mapping[str, Any], key: str) -> Any:
        """Fetch a required dependency output with a clear error when absent."""
        if key not in mapping:
            raise KeyError(f"step '{self.current_step}' requires output of '{key}'")
        return mapping[key]


def usage_for(provider_name: str, model: str | None, tokens: TokenUsage) -> Cost:
    """Cost helper exposed for steps that call providers directly."""
    return cost_for(provider_name, model, tokens)
