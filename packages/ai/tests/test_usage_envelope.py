"""The usage envelope: ``chat``, ``stream`` and ``structured_output`` report the same shape.

The defect this file pins down was measured, not hypothetical. ``RunContext.structured`` returned
the parsed schema and dropped the provider's usage object, and ``MeteredProvider.structured_output``
passed ``tokens=None, cost=None`` because there was nothing else it could do — so
``agent_runs.total_tokens`` was structurally ``0`` for every agent in the product (all of them use
the structured path), and a **paid** deployment's cost page read ``$0.00`` for work it had paid for
(``docs/QUALITY.md`` §7.1, ROADMAP PHASE 12 #13).

The fakes that produce each reporting shape live in ``usage_fakes.py``; what is asserted here is what
the product does with them:

* a provider that reports usage → ``reported``, with the numbers;
* a provider that reports nothing → ``unavailable``, with ``None`` counts. **Not ``0``.** "Zero
  tokens" and "we were not told" are different facts and this project is built on not confusing
  them;
* a provider that reports *some* fields → the ones it reported are kept, and ``cached_tokens`` says
  whether the vendor reported a cache count at all, since most do not.

The last two classes check the arithmetic that makes one run-level number out of several calls, and
that a cached hit and a fallback both keep the envelope honest.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from pydantic import BaseModel
import pytest
from tests.usage_fakes import (
    Answer,
    LegacyProvider,
    ScriptedUsageProvider,
    prompt_registry,
    recording_executor,
    run_context,
)

from careerforge_ai.orchestrator import RunContext, Step, Workflow
from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    structured_output_envelope,
    supports_usage_envelope,
)
from careerforge_ai.providers.caching import CachedProvider, InMemoryCacheStore
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.providers.resilience import ResilientProvider
from careerforge_ai.schemas.common import CacheKind, UsageStatus
from careerforge_ai.schemas.observability import LLMUsage, TokenUsage

_Scripted = ScriptedUsageProvider
_context = run_context
_recording_executor = recording_executor
_prompts = prompt_registry


class TestTheSameShapeForAllThreeCalls:
    async def test_a_provider_that_reports_usage_reports_it_everywhere(self) -> None:
        provider = _Scripted("reported")
        context = _context(provider)

        await context.chat("probe")  # type: ignore[arg-type]
        chat_usage = context.usage_envelope
        assert chat_usage is not None
        assert chat_usage.usage_status is UsageStatus.REPORTED
        assert chat_usage.input_tokens == 100 and chat_usage.output_tokens == 25
        assert chat_usage.total_tokens == 125 and chat_usage.cached_tokens == 60
        assert chat_usage.estimated_cost_usd == pytest.approx(0.002)
        assert chat_usage.estimated_cost_cny == pytest.approx(0.0144)

        context.reset_usage()
        async for _ in context.stream("probe"):  # type: ignore[arg-type]
            pass
        assert context.usage_envelope is not None
        assert context.usage_envelope == chat_usage

    async def test_a_provider_that_reports_nothing_says_unavailable_not_zero(self) -> None:
        """The distinction the whole project is built on, applied to cost."""
        provider = _Scripted("silent")

        class _One(BaseModel):
            reply: str = ""

        result = await structured_output_envelope(provider, [], _One)
        assert result.usage.usage_status is UsageStatus.UNAVAILABLE
        assert result.usage.input_tokens is None
        assert result.usage.output_tokens is None
        assert result.usage.total_tokens is None
        assert result.usage.estimated_cost_usd is None
        # The projection is what reaches the database, and it is SQL NULL 鈥?not 0.
        assert result.usage.projection()["total_tokens"] is None
        assert result.usage.projection()["cost_usd"] is None
        assert result.usage.projection()["usage_status"] == "unavailable"

    async def test_a_provider_that_reports_some_fields_keeps_exactly_those(self) -> None:
        """A partial envelope is not padded: a missing completion count stays ``0`` because the
        provider *said* zero, while the vendor's silence about cached tokens is recorded as
        silence rather than as a cache miss."""
        provider = _Scripted("partial")

        class _One(BaseModel):
            reply: str = ""

        result = await structured_output_envelope(provider, [], _One)
        assert result.usage.usage_status is UsageStatus.REPORTED
        assert result.usage.input_tokens == 80
        assert result.usage.output_tokens == 0
        assert result.usage.cached_tokens_reported is False
        assert result.usage.cached_tokens == 0

    async def test_estimated_usage_is_labelled_as_an_estimate(self) -> None:
        provider = _Scripted("estimated")

        class _One(BaseModel):
            reply: str = ""

        result = await structured_output_envelope(provider, [], _One)
        assert result.usage.usage_status is UsageStatus.ESTIMATED
        assert result.usage.is_estimated is True
        # The local count is kept beside the verdict, never inside it.
        assert result.usage.estimated_input_tokens == 80


class TestLegacyProvidersFallBackHonestly:
    def test_a_provider_without_the_envelope_is_detected(self) -> None:
        assert supports_usage_envelope(_Scripted()) is True
        assert supports_usage_envelope(LegacyProvider()) is False
        # A decorator that cannot answer must not be mistaken for one that can.
        assert (
            supports_usage_envelope(CachedProvider(LegacyProvider(), store=InMemoryCacheStore()))
            is True
        )

    async def test_a_provider_without_the_envelope_yields_unavailable(self) -> None:
        class _One(BaseModel):
            reply: str = ""

        result = await structured_output_envelope(LegacyProvider(), [], _One)
        assert result.value.reply == "ok"
        assert result.usage.usage_status is UsageStatus.UNAVAILABLE
        assert result.usage.total_tokens is None

    async def test_the_heuristic_provider_declares_unavailable_and_keeps_its_own_count(
        self,
    ) -> None:
        """It computes locally and spends nothing, so it *has* no usage to report.

        What it does have is the size of the material it was handed, measured with the same
        estimator the token counter uses 鈥?kept in its own field so it can never be summed into a
        cost.
        """

        class _One(BaseModel):
            reply: str = ""

        result = await structured_output_envelope(
            HeuristicProvider(),
            [],
            _One,
            context={"source_text": "STM32 and FreeRTOS motor control firmware"},
        )
        assert result.usage.usage_status is UsageStatus.UNAVAILABLE
        assert result.usage.total_tokens is None
        assert result.usage.estimated_cost_usd is None
        assert result.usage.estimated_input_tokens is not None
        assert result.usage.estimated_input_tokens > 0


class TestRunContextAggregates:
    async def test_structured_usage_reaches_the_step_trace(self) -> None:
        """The end of the chain the defect lived on: a step's trace row, not a unit."""
        provider = _Scripted("reported")
        executor, traces = _recording_executor(provider)

        async def step(context: RunContext, inputs: dict[str, Any]) -> str:
            result = await context.structured("probe", Answer)
            return result.reply

        workflow = Workflow(name="w", agent="a", steps=(Step(name="one", fn=step),))
        outcome = await executor.run(workflow)

        assert outcome.record.tokens.total_tokens == 125
        assert outcome.record.cost.usd == pytest.approx(0.002)
        assert outcome.record.usage is not None
        assert outcome.record.usage.usage_status is UsageStatus.REPORTED
        assert outcome.record.usage.total_tokens == 125
        assert traces[0].usage is not None and traces[0].usage.total_tokens == 125

    async def test_two_calls_in_one_run_are_summed_and_the_status_is_the_weaker_one(self) -> None:
        """A total that mixes a reported call with an unaccounted one is not fully reported.

        The counters that *are* known are kept — they are real, paid-for measurements — but the
        status stops the total from being read as the whole figure, and the projection stores them
        with ``unavailable`` rather than discarding them as ``NULL``. That is the difference between
        "at least 125 tokens" and "125 tokens".
        """
        reported = _Scripted("reported")
        silent = _Scripted("silent", name="silent")
        context = _context(reported)

        await context.structured("probe", Answer)
        assert context.usage_envelope is not None
        assert context.usage_envelope.total_tokens == 125
        assert context.usage_envelope.usage_status is UsageStatus.REPORTED

        context.add_envelope(silent.envelope())
        merged = context.usage_envelope
        assert merged is not None
        assert merged.usage_status is UsageStatus.UNAVAILABLE
        assert merged.total_tokens == 125, "the known part was discarded"
        assert merged.projection()["usage_status"] == "unavailable"
        assert merged.projection()["total_tokens"] == 125

        # A run where *nobody* reported anything stores NULL, not a zero.
        bare = _context(silent)
        bare.add_envelope(silent.envelope())
        assert bare.usage_envelope is not None
        assert bare.usage_envelope.projection()["total_tokens"] is None

        # And two reported calls really do add up.
        second = LLMUsage.from_token_usage(
            TokenUsage(prompt_tokens=100, completion_tokens=25, total_tokens=125), provider="p"
        )
        assert second.merge(second).total_tokens == 250
        assert second.merge(second).usage_status is UsageStatus.REPORTED
        # One estimated half makes the total estimated rather than reported.
        estimated = LLMUsage.from_token_usage(
            TokenUsage(prompt_tokens=10, total_tokens=10, estimated=True), provider="p"
        )
        assert second.merge(estimated).usage_status is UsageStatus.ESTIMATED

    async def test_a_step_that_makes_no_model_call_has_no_usage_at_all(self) -> None:
        """``None`` is a statement, and it is not the same statement as ``unavailable``."""
        executor, traces = _recording_executor(HeuristicProvider())

        async def pure(context: RunContext, inputs: dict[str, Any]) -> str:
            return "no model call here"

        workflow = Workflow(name="w", agent="a", steps=(Step(name="pure", fn=pure),))
        await executor.run(workflow)

        assert traces[0].usage is None
        assert traces[0].usage_or_unavailable().usage_status is UsageStatus.UNAVAILABLE


class TestCacheHits:
    async def test_a_cache_hit_is_reported_as_cached_rather_than_as_zero(self) -> None:
        """Nothing was billed, and that is a fact 鈥?different from an unknown."""
        inner = _Scripted("reported")
        store = InMemoryCacheStore(kind=CacheKind.LLM)
        provider = CachedProvider(inner, store=store)
        context = _context(provider)

        class _One(BaseModel):
            reply: str = ""

        first = await structured_output_envelope(provider, [], _One)
        assert first.usage.usage_status is UsageStatus.REPORTED
        second = await structured_output_envelope(provider, [], _One)
        assert inner.calls == 1, (
            "the second call was not served from the cache, so this proves nothing"
        )
        assert second.usage.usage_status is UsageStatus.CACHED
        # The original call's tokens are not attributed to the hit: that would bill them twice.
        assert second.usage.total_tokens is None
        assert second.usage.cost_usd == 0.0
        assert context.usage_envelope is None  # nothing was added yet

    async def test_a_cache_hit_on_the_chat_path_is_cached_too(self) -> None:
        provider = CachedProvider(
            _Scripted("reported"), store=InMemoryCacheStore(kind=CacheKind.LLM)
        )
        first = await provider.chat([])
        second = await provider.chat([])
        assert first.envelope().usage_status is UsageStatus.REPORTED
        assert second.cached is True
        assert second.envelope().usage_status is UsageStatus.CACHED


class TestTheChainPreservesTheEnvelope:
    async def test_a_resilient_chain_forwards_the_serving_providers_envelope(self) -> None:
        chain = ResilientProvider(_Scripted("reported"), fallbacks=[], max_retries=0)

        class _One(BaseModel):
            reply: str = ""

        result = await structured_output_envelope(chain, [], _One)
        assert result.usage.usage_status is UsageStatus.REPORTED
        assert result.usage.total_tokens == 125

    async def test_a_fallback_provider_contributes_its_own_numbers(self) -> None:
        class _Broken:
            @property
            def name(self) -> str:
                return "broken"

            @property
            def capabilities(self) -> ProviderCapabilities:
                return ProviderCapabilities(
                    name="broken",
                    supports_streaming=False,
                    supports_embeddings=False,
                    supports_native_json_schema=True,
                )

            async def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> ChatResult:
                raise RuntimeError("down")

            async def stream(
                self, messages: Sequence[ChatMessage], **kwargs: Any
            ) -> AsyncIterator[StreamChunk]:
                raise RuntimeError("down")

            async def embed(self, texts: Sequence[str], **kwargs: Any) -> EmbeddingResult:
                raise RuntimeError("down")

            async def structured_output(
                self, messages: Sequence[ChatMessage], schema: type[SchemaT], **kwargs: Any
            ) -> SchemaT:
                raise RuntimeError("down")

        chain = ResilientProvider(
            _Broken(),
            fallbacks=[_Scripted("silent", name="second")],
            max_retries=0,
            backoff_base_s=0.0,
        )

        class _One(BaseModel):
            reply: str = ""

        result = await structured_output_envelope(chain, [], _One)
        # The fallback answered and reported nothing: the envelope names the fallback and says
        # unavailable. It does not inherit the primary's (nonexistent) numbers.
        assert result.usage.provider == "second"
        assert result.usage.usage_status is UsageStatus.UNAVAILABLE
        assert chain.last_chain_info.degraded is True
