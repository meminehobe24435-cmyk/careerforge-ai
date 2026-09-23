"""Tests for the agent orchestrator.

The executor's failure semantics are the part worth pinning down: a retryable
error must be retried, a step with a fallback must degrade instead of failing the
run, an optional step must not be able to break the primary goal, and a
non-retryable error must fail fast rather than burning budget.
"""

from __future__ import annotations

from typing import Any

import pytest

from careerforge_ai.errors import ProviderError, SchemaValidationError, StepFailedError
from careerforge_ai.orchestrator import (
    ExecutorSettings,
    Step,
    Workflow,
    WorkflowExecutor,
)
from careerforge_ai.prompting.registry import PromptRegistry
from careerforge_ai.providers.decorators import InMemoryCacheStore
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.common import AgentRunStatus, CacheKind
from careerforge_ai.schemas.observability import AgentRunRecord, StepTrace


class _Tracker:
    """Minimal tracker that records what the executor emitted."""

    def __init__(self) -> None:
        self.runs: list[AgentRunRecord] = []
        self.step_events: list[str] = []

    async def start_run(self, record: AgentRunRecord) -> AgentRunRecord:
        self.runs.append(record)
        return record

    async def record_step(self, run: AgentRunRecord, step: StepTrace) -> None:
        self.step_events.append(step.name)
        run.steps.append(step)
        run.recompute_totals()

    async def finish_run(self, run: AgentRunRecord) -> None:
        run.recompute_totals()


def _executor(
    *,
    tracker: _Tracker | None = None,
    cache: InMemoryCacheStore | None = None,
    max_retries: int = 2,
) -> WorkflowExecutor:
    return WorkflowExecutor(
        provider=HeuristicProvider(),
        prompts=PromptRegistry(),
        tracker=tracker,
        cache=cache,
        settings=ExecutorSettings(max_retries=max_retries, backoff_base_s=0.0),
    )


class TestWorkflowValidation:
    def test_rejects_unknown_dependency(self) -> None:
        workflow = Workflow(
            name="bad",
            agent="test",
            steps=(Step(name="a", fn=_noop, depends_on=("missing",)),),
        )
        with pytest.raises(StepFailedError):
            workflow.validate()

    def test_rejects_duplicate_step_names(self) -> None:
        workflow = Workflow(
            name="dup", agent="test", steps=(Step(name="a", fn=_noop), Step(name="a", fn=_noop))
        )
        with pytest.raises(StepFailedError):
            workflow.validate()

    def test_detects_a_cycle(self) -> None:
        workflow = Workflow(
            name="cyclic",
            agent="test",
            steps=(
                Step(name="a", fn=_noop, depends_on=("b",)),
                Step(name="b", fn=_noop, depends_on=("a",)),
            ),
        )
        with pytest.raises(StepFailedError):
            workflow.validate()

    def test_layers_group_independent_steps(self) -> None:
        workflow = Workflow(
            name="layered",
            agent="test",
            steps=(
                Step(name="root", fn=_noop),
                Step(name="left", fn=_noop, depends_on=("root",)),
                Step(name="right", fn=_noop, depends_on=("root",)),
                Step(name="join", fn=_noop, depends_on=("left", "right")),
            ),
        )
        layers = [[step.name for step in layer] for layer in workflow.layers()]
        assert layers[0] == ["root"]
        assert sorted(layers[1]) == ["left", "right"]
        assert layers[2] == ["join"]

    def test_terminal_step_is_the_leaf(self) -> None:
        workflow = Workflow(
            name="chain",
            agent="test",
            steps=(Step(name="a", fn=_noop), Step(name="b", fn=_noop, depends_on=("a",))),
        )
        assert workflow.terminal_step().name == "b"


async def _noop(context: Any, inputs: dict[str, Any]) -> Any:
    return None


class TestExecution:
    async def test_runs_in_dependency_order_and_passes_outputs(self) -> None:
        async def make_value(context: Any, inputs: dict[str, Any]) -> int:
            return 21

        async def double(context: Any, inputs: dict[str, Any]) -> int:
            return int(inputs["seed"]) * 2

        workflow = Workflow(
            name="linear",
            agent="test",
            steps=(
                Step(name="seed", fn=make_value),
                Step(name="double", fn=double, depends_on=("seed",)),
            ),
        )
        outcome = await _executor().run(workflow)
        assert outcome.ok
        assert outcome.get("double") == 42

    async def test_independent_steps_run_concurrently(self) -> None:
        import asyncio

        order: list[str] = []

        async def slow_a(context: Any, inputs: dict[str, Any]) -> str:
            await asyncio.sleep(0.05)
            order.append("a")
            return "a"

        async def slow_b(context: Any, inputs: dict[str, Any]) -> str:
            await asyncio.sleep(0.05)
            order.append("b")
            return "b"

        workflow = Workflow(
            name="parallel",
            agent="test",
            steps=(Step(name="a", fn=slow_a), Step(name="b", fn=slow_b)),
        )
        import time

        started = time.perf_counter()
        outcome = await _executor().run(workflow)
        elapsed = time.perf_counter() - started

        assert outcome.get("a") == "a"
        assert outcome.get("b") == "b"
        # Two 50ms steps in one layer must take ~50ms, not ~100ms.
        assert elapsed < 0.09

    async def test_records_one_trace_row_per_step(self) -> None:
        tracker = _Tracker()
        workflow = Workflow(
            name="traced",
            agent="test",
            steps=(Step(name="a", fn=_noop), Step(name="b", fn=_noop, depends_on=("a",))),
        )
        outcome = await _executor(tracker=tracker).run(workflow, request_id="req_test")
        assert tracker.step_events == ["a", "b"]
        assert [trace.name for trace in outcome.record.steps] == ["a", "b"]
        assert outcome.record.request_id == "req_test"

    async def test_run_status_is_succeeded_when_nothing_degrades(self) -> None:
        workflow = Workflow(name="clean", agent="test", steps=(Step(name="a", fn=_noop),))
        outcome = await _executor().run(workflow)
        assert outcome.status == AgentRunStatus.SUCCEEDED.value
        assert outcome.degraded is False


class TestRetrySemantics:
    async def test_retries_a_transient_failure_then_succeeds(self) -> None:
        attempts = {"count": 0}

        async def flaky(context: Any, inputs: dict[str, Any]) -> str:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ProviderError("upstream hiccup")
            return "finally"

        workflow = Workflow(name="retry", agent="test", steps=(Step(name="flaky", fn=flaky),))
        outcome = await _executor(max_retries=2).run(workflow)
        assert outcome.get("flaky") == "finally"
        assert attempts["count"] == 3
        trace = outcome.record.step("flaky")
        assert trace is not None and trace.attempts == 3

    async def test_does_not_retry_a_non_retryable_error(self) -> None:
        attempts = {"count": 0}

        async def broken(context: Any, inputs: dict[str, Any]) -> str:
            attempts["count"] += 1
            raise SchemaValidationError("output did not match the schema")

        workflow = Workflow(name="norretry", agent="test", steps=(Step(name="broken", fn=broken),))
        outcome = await _executor(max_retries=3).run(workflow)
        assert attempts["count"] == 1
        assert outcome.status == AgentRunStatus.FAILED.value
        assert outcome.error_code == "SCHEMA_VALIDATION_ERROR"

    async def test_times_out_a_hanging_step(self) -> None:
        import asyncio

        async def hangs(context: Any, inputs: dict[str, Any]) -> str:
            await asyncio.sleep(5)
            return "never"

        workflow = Workflow(
            name="timeout", agent="test", steps=(Step(name="hangs", fn=hangs, timeout_s=0.05),)
        )
        outcome = await _executor(max_retries=0).run(workflow)
        trace = outcome.record.step("hangs")
        assert trace is not None
        assert trace.error_code == "STEP_TIMEOUT"


class TestDegradationSemantics:
    async def test_fallback_degrades_the_run_instead_of_failing_it(self) -> None:
        async def boom(context: Any, inputs: dict[str, Any]) -> str:
            raise ProviderError("model down")

        async def cheap_fallback(context: Any, inputs: dict[str, Any], error: BaseException) -> str:
            return f"fallback:{type(error).__name__}"

        workflow = Workflow(
            name="degrade",
            agent="test",
            steps=(Step(name="boom", fn=boom, fallback=cheap_fallback, max_retries=0),),
        )
        outcome = await _executor(max_retries=0).run(workflow)
        assert outcome.ok
        assert outcome.status == AgentRunStatus.DEGRADED.value
        assert outcome.get("boom") == "fallback:ProviderError"
        trace = outcome.record.step("boom")
        assert trace is not None and trace.status == "degraded"

    async def test_optional_step_failure_does_not_fail_the_run(self) -> None:
        async def enrichment(context: Any, inputs: dict[str, Any]) -> str:
            raise SchemaValidationError("enrichment unavailable")

        workflow = Workflow(
            name="optional",
            agent="test",
            steps=(Step(name="enrichment", fn=enrichment, optional=True),),
        )
        outcome = await _executor().run(workflow)
        assert outcome.ok
        assert outcome.get("enrichment") is None
        assert outcome.degraded is True

    async def test_failed_fallback_still_marks_the_step_failed(self) -> None:
        async def boom(context: Any, inputs: dict[str, Any]) -> str:
            raise SchemaValidationError("no")

        async def also_bad(context: Any, inputs: dict[str, Any], error: BaseException) -> str:
            raise ProviderError("fallback also down")

        workflow = Workflow(
            name="badd",
            agent="test",
            steps=(Step(name="boom", fn=boom, fallback=also_bad, max_retries=0),),
        )
        outcome = await _executor(max_retries=0).run(workflow)
        assert outcome.status == AgentRunStatus.FAILED.value
        trace = outcome.record.step("boom")
        assert trace is not None and "fallback failed" in (trace.error_message or "")

    async def test_unexpected_exception_is_reraised_after_tracing(self) -> None:
        tracker = _Tracker()

        async def bug(context: Any, inputs: dict[str, Any]) -> str:
            raise RuntimeError("a genuine bug")

        workflow = Workflow(name="bug", agent="test", steps=(Step(name="bug", fn=bug),))
        with pytest.raises(RuntimeError):
            await _executor(tracker=tracker).run(workflow)
        # The trace must still have been persisted: losing observability because
        # of an unhandled bug would be the worst of both worlds.
        assert len(tracker.runs) == 1
        assert tracker.runs[0].error_code == "RUNTIMEERROR"


class TestCaching:
    async def test_cached_step_does_not_rerun(self) -> None:
        calls = {"count": 0}

        async def expensive(context: Any, inputs: dict[str, Any]) -> dict[str, int]:
            calls["count"] += 1
            return {"value": 7}

        workflow = Workflow(
            name="cached",
            agent="test",
            steps=(Step(name="expensive", fn=expensive, cache_ttl=60),),
        )
        cache = InMemoryCacheStore(kind=CacheKind.TOOL)
        executor = _executor(cache=cache)

        first = await executor.run(workflow)
        second = await executor.run(workflow)

        assert calls["count"] == 1
        assert first.get("expensive") == {"value": 7}
        assert second.get("expensive") == {"value": 7}
        trace = second.record.step("expensive")
        assert trace is not None and trace.cache_hit is True
        assert trace.status == "cached"

    async def test_cache_is_keyed_on_inputs(self) -> None:
        calls = {"count": 0}

        async def echo(context: Any, inputs: dict[str, Any]) -> int:
            calls["count"] += 1
            return int(inputs["seed"])

        async def seed(context: Any, inputs: dict[str, Any]) -> int:
            return 1

        workflow = Workflow(
            name="keyed",
            agent="test",
            steps=(
                Step(name="seed", fn=seed),
                Step(name="echo", fn=echo, depends_on=("seed",), cache_ttl=60),
            ),
        )
        cache = InMemoryCacheStore(kind=CacheKind.TOOL)
        executor = _executor(cache=cache)
        await executor.run(workflow)
        await executor.run(workflow)
        assert calls["count"] == 1


class TestRunContext:
    async def test_context_exposes_injected_services(self) -> None:
        seen: dict[str, Any] = {}

        async def probe(context: Any, inputs: dict[str, Any]) -> str:
            seen["service"] = context.service("retriever")
            seen["maybe_missing"] = context.maybe_service("nope")
            seen["user"] = context.user_id
            return "ok"

        workflow = Workflow(name="services", agent="test", steps=(Step(name="probe", fn=probe),))
        outcome = await _executor().run(workflow, services={"retriever": "fake-retriever"})
        assert outcome.ok
        assert seen["service"] == "fake-retriever"
        assert seen["maybe_missing"] is None

    async def test_missing_service_raises_a_key_error(self) -> None:
        async def probe(context: Any, inputs: dict[str, Any]) -> str:
            return str(context.service("absent"))

        workflow = Workflow(name="missing", agent="test", steps=(Step(name="probe", fn=probe),))
        with pytest.raises(KeyError):
            await _executor().run(workflow)
