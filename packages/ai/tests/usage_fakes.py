"""Providers written to report usage in one specific way — the three shapes PHASE 13 must handle.

Extracted from ``test_usage_envelope.py`` when that module crossed the file-length gate, and along the
seam that was already there: these are fakes, and the assertions live in the suite.

The shapes, and why each one exists:

* ``reported`` — a vendor that answers with ``prompt_tokens``/``completion_tokens`` and a cached-token
  count. The case a paid deployment is in, and the case a cost page has to be right about.
* ``estimated`` — no numbers from the vendor, so a local character count stands in. It must be
  labelled an estimate; reporting it as usage would invent a measurement.
* ``silent`` — **no usage object at all.** The interesting one. The envelope must say
  ``unavailable`` with ``None`` counts, never ``0``: "zero tokens" and "we were not told" are
  different facts, and confusing them is the defect PHASE 12 recorded (``docs/QUALITY.md`` §7.1).
* ``partial`` — prompt tokens only, no completion count, no cache count. Real vendors do this, and
  the envelope has to preserve the gaps rather than filling them with zeros.

``_Legacy`` is not a failure mode but a provider that predates the envelope: it answers
``structured_output`` and nothing else, which is what a third-party or in-house provider looks like.
The fallback has to work for it, and to report the absence honestly rather than a zeroed envelope.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from pydantic import BaseModel

from careerforge_ai.orchestrator import ExecutorSettings, RunContext, WorkflowExecutor
from careerforge_ai.prompting.registry import PromptRegistry, PromptTemplate
from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    StructuredContext,
    StructuredResult,
)
from careerforge_ai.schemas.observability import Cost, LLMUsage, TokenUsage

__all__ = [
    "Answer",
    "ScriptedUsageProvider",
    "prompt_registry",
    "recording_executor",
    "run_context",
]


class Answer(BaseModel):
    """The simplest schema a structured call can produce."""

    reply: str = ""


class ScriptedUsageProvider:
    """A provider whose usage behaviour is the whole point of the test.

    ``mode`` is one of ``reported``, ``estimated``, ``silent`` (no usage object at all) or
    ``partial`` (prompt tokens only, no completion count and no cache count).
    """

    def __init__(self, mode: str = "reported", *, name: str = "scripted") -> None:
        self.mode = mode
        self._name = name
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self._name,
            supports_streaming=True,
            supports_embeddings=True,
            supports_native_json_schema=True,
            deterministic=False,
            reports_cached_tokens=self.mode == "reported",
            supports_usage_envelope=True,
        )

    def _tokens(self) -> TokenUsage | None:
        if self.mode == "silent":
            return None
        if self.mode == "partial":
            return TokenUsage(prompt_tokens=80, total_tokens=80)
        if self.mode == "estimated":
            return TokenUsage(
                prompt_tokens=80, completion_tokens=20, total_tokens=100, estimated=True
            )
        return TokenUsage(
            prompt_tokens=100, completion_tokens=25, total_tokens=125, cached_tokens=60
        )

    def envelope(self) -> LLMUsage:
        tokens = self._tokens()
        if tokens is None:
            return LLMUsage.unavailable(provider=self._name, model="scripted-model")
        return LLMUsage.from_token_usage(
            tokens,
            Cost(usd=0.002, cny=0.0144),
            provider=self._name,
            model="scripted-model",
            cached_tokens_reported=self.mode == "reported",
        )

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        self.calls += 1
        tokens = self._tokens() or TokenUsage()
        return ChatResult(
            content="ok",
            provider=self._name,
            model=model or "scripted-model",
            tokens=tokens,
            cost=Cost(usd=0.002, cny=0.0144),
            latency_ms=7,
            usage=self.envelope(),
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.calls += 1
        yield StreamChunk(delta="ok", provider=self._name, model="scripted-model")
        silent = self.mode == "silent"
        yield StreamChunk(
            delta="",
            done=True,
            provider=self._name,
            model="scripted-model",
            tokens=self._tokens() or TokenUsage(),
            cost=Cost(usd=0.002, cny=0.0144),
            usage=None if silent else self.envelope(),
            usage_reported=not silent,
        )

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[[0.0] for _ in texts],
            provider=self._name,
            model="scripted-embed",
            dim=1,
            usage=self.envelope(),
        )

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> SchemaT:
        result = await self.structured_output_envelope(
            messages, schema, context=context, temperature=temperature, model=model
        )
        return result.value

    async def structured_output_envelope(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> StructuredResult[SchemaT]:
        self.calls += 1
        return StructuredResult(value=schema.model_validate({"reply": "ok"}), usage=self.envelope())


class LegacyProvider:
    """A provider written before the envelope existed: only ``structured_output``.

    Kept as a real class rather than a mock because this is exactly what a third-party or
    in-house provider looks like, and the fallback has to work for it: ``unavailable``, never a
    zero-filled envelope.
    """

    @property
    def name(self) -> str:
        return "legacy"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name="legacy",
            supports_streaming=False,
            supports_embeddings=False,
            supports_native_json_schema=False,
        )

    async def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResult:
        return ChatResult(content="ok", provider="legacy", model="legacy-model")

    async def stream(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(done=True, provider="legacy", model="legacy-model")

    async def embed(self, texts: Sequence[str], **kwargs: Any) -> EmbeddingResult:
        return EmbeddingResult(vectors=[], provider="legacy", model="legacy-model", dim=1)

    async def structured_output(
        self,
        messages: Sequence[ChatMessage],
        schema: type[SchemaT],
        *,
        context: StructuredContext | None = None,
        temperature: float = 0.0,
        model: str | None = None,
    ) -> SchemaT:
        return schema.model_validate({"reply": "ok"})


def prompt_registry() -> PromptRegistry:
    """A registry holding the one prompt these tests render.

    A tiny real registry rather than a mock: ``RunContext.chat``/``structured`` go through
    :meth:`PromptRegistry.render`, and the point of these tests is the path the product takes, not a
    path invented for the test.
    """
    registry = PromptRegistry()
    registry.register(
        PromptTemplate(name="probe", version=1, body="system\n---\nreport the usage envelope")
    )
    return registry


def run_context(provider: Any, **metadata: Any) -> RunContext:
    return RunContext(
        user_id=None,
        request_id="req-1",
        provider=provider,
        prompts=prompt_registry(),
        metadata=dict(metadata),
    )


def recording_executor(provider: Any) -> tuple[WorkflowExecutor, list[Any]]:
    """An executor plus the step traces it produced."""
    traces: list[Any] = []

    class Tracker:
        async def start_run(self, record: Any) -> Any:
            return record

        async def record_step(self, run: Any, step: Any) -> None:
            traces.append(step)
            run.steps.append(step)
            run.recompute_totals()

        async def finish_run(self, run: Any) -> None:
            run.recompute_totals()

    return (
        WorkflowExecutor(
            provider=provider,
            prompts=prompt_registry(),
            tracker=Tracker(),
            settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
        ),
        traces,
    )


# 鈹€鈹€ the three call shapes agree 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
