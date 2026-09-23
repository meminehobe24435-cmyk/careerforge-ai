"""Workflow execution: concurrency, retries, degradation, caching and traces.

Execution semantics, all of them deliberate:

* Steps run **layer by layer**; every step whose dependencies are satisfied in
  the same layer runs concurrently.
* Only **transient** failures are retried (:func:`careerforge_ai.errors.is_retryable`);
  a schema violation or a bad-input error fails immediately.
* A step that declares a ``fallback`` never fails the run: it degrades instead,
  and the run is marked ``degraded`` with a reason the UI must display.
* An ``optional`` step without a fallback is skipped on failure, so enrichment
  can never take down the primary goal.
* Any other failure aborts the run and records the error on the trace.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import time
from typing import Any
from uuid import UUID, uuid4

from careerforge_ai.errors import (
    CareerForgeError,
    StepTimeoutError,
    is_retryable,
)
from careerforge_ai.orchestrator.core import (
    RunContext,
    Step,
    Workflow,
    WorkflowOutput,
    digest_of,
)
from careerforge_ai.prompting.registry import PromptRegistry
from careerforge_ai.providers.base import LLMProvider
from careerforge_ai.schemas.common import AgentRunStatus, DegradationReason
from careerforge_ai.schemas.observability import AgentRunRecord, StepTrace

__all__ = ["ExecutorSettings", "WorkflowExecutor"]

#: Default per-step timeout when neither the step nor the executor sets one.
DEFAULT_STEP_TIMEOUT_S = 60.0
#: Default retry budget for transient failures.
DEFAULT_MAX_RETRIES = 2


class ExecutorSettings:
    """Executor-level defaults, injectable so tests can run without waiting."""

    __slots__ = ("backoff_base_s", "backoff_jitter", "max_retries", "step_timeout_s")

    def __init__(
        self,
        *,
        step_timeout_s: float = DEFAULT_STEP_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_s: float = 0.25,
        backoff_jitter: bool = True,
    ) -> None:
        self.step_timeout_s = step_timeout_s
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s
        self.backoff_jitter = backoff_jitter


class WorkflowExecutor:
    """Runs :class:`Workflow` objects and emits an :class:`AgentRunRecord` for each."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompts: PromptRegistry,
        tracker: Any | None = None,
        cache: Any | None = None,
        settings: ExecutorSettings | None = None,
    ) -> None:
        self._provider = provider
        self._prompts = prompts
        self._tracker = tracker
        self._cache = cache
        self._settings = settings or ExecutorSettings()

    # ── public API ───────────────────────────────────────────────────────────

    async def run(
        self,
        workflow: Workflow,
        *,
        user_id: UUID | None = None,
        request_id: str | None = None,
        trigger: str = "api",
        services: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        parent_run_id: UUID | None = None,
    ) -> WorkflowOutput:
        """Execute ``workflow`` and return its outputs together with the trace."""
        workflow.validate()

        record = AgentRunRecord(
            id=uuid4(),
            user_id=user_id,
            workflow=workflow.name,
            agent=workflow.agent,
            status=AgentRunStatus.RUNNING,
            trigger=trigger or workflow.trigger,
            provider=self._provider.name,
            model=getattr(self._provider, "model", None),
            request_id=request_id,
            parent_run_id=parent_run_id,
        )

        context = RunContext(
            user_id=user_id,
            request_id=request_id or "run_local",
            provider=self._provider,
            prompts=self._prompts,
            tracker=self._tracker,
            cache=self._cache,
            services=dict(services or {}),
            metadata=dict(metadata or {}),
        )

        if self._tracker is not None:
            record = await self._tracker.start_run(record)

        started = time.perf_counter()
        outputs: dict[str, Any] = {}
        degraded = False
        status = AgentRunStatus.SUCCEEDED
        error_code: str | None = None
        error_message: str | None = None
        failure: BaseException | None = None

        try:
            for layer in workflow.layers():
                results = await asyncio.gather(
                    *(self._run_step(step, context, outputs, record) for step in layer)
                )
                for step, outcome in zip(layer, results, strict=True):
                    if outcome.degraded:
                        degraded = True
                    outputs[step.name] = outcome.value
        except _StepError as exc:
            failure = exc.cause
            error_code = _error_code(exc.cause)
            error_message = str(exc.cause)[:1000]
            status = AgentRunStatus.FAILED
            degraded = degraded or exc.degraded
        except Exception as exc:
            failure = exc
            error_code = _error_code(exc)
            error_message = str(exc)[:1000]
            status = AgentRunStatus.FAILED

        if status is AgentRunStatus.SUCCEEDED and degraded:
            status = AgentRunStatus.DEGRADED

        record.status = status
        record.degraded = degraded
        record.degradation_reason = context.degradation_reason
        record.error_code = error_code
        record.error_message = error_message
        record.finished_at = record.started_at
        record.latency_ms = int((time.perf_counter() - started) * 1000)
        record.input_ref = dict(context.metadata.get("input_ref", {}))
        record.output_ref = dict(context.metadata.get("output_ref", {}))
        record.prompt_version = _first_prompt_ref(context)

        if self._tracker is not None:
            await self._tracker.finish_run(record)

        if failure is not None and not isinstance(failure, CareerForgeError):
            # Re-raise unexpected failures after the trace has been persisted, so
            # observability is never lost because of an unhandled bug.
            raise failure

        return WorkflowOutput(
            record=record,
            outputs=outputs,
            status=status.value,
            degraded=degraded,
            degradation_reason=record.degradation_reason,
            error_code=error_code,
            error_message=error_message,
            metadata=dict(context.metadata),
        )

    # ── internals ────────────────────────────────────────────────────────────

    async def _run_step(
        self,
        step: Step,
        context: RunContext,
        outputs: Mapping[str, Any],
        record: AgentRunRecord,
    ) -> _StepOutcome:
        inputs = {name: outputs.get(name) for name in step.depends_on}
        timeout_s = step.timeout_s or self._settings.step_timeout_s
        max_retries = self._settings.max_retries if step.max_retries is None else step.max_retries
        cache_key = self._cache_key(step, inputs) if step.cache_ttl else None

        context.current_step = step.name
        context.reset_usage()
        trace = StepTrace(
            name=step.name,
            provider=self._provider.name,
            input_digest=step.digest_inputs(inputs),
        )
        step_started = time.perf_counter()

        # Cache hit short-circuits all work, including the model call.
        if cache_key is not None and self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                trace.status = "cached"
                trace.cache_hit = True
                trace.latency_ms = int((time.perf_counter() - step_started) * 1000)
                trace.output_digest = digest_of(cached)
                await self._emit(record, trace)
                return _StepOutcome(value=cached, degraded=False)

        last_error: BaseException | None = None
        for attempt in range(1, max_retries + 2):
            try:
                value = await asyncio.wait_for(step.fn(context, inputs), timeout=timeout_s)
                tokens, cost = context.usage
                trace.tokens = tokens
                trace.cost = cost
                trace.attempts = attempt
                trace.status = "ok"
                trace.latency_ms = int((time.perf_counter() - step_started) * 1000)
                trace.output_digest = digest_of(value)
                if context.degraded:
                    trace.status = "degraded"
                    trace.degradation_reason = context.degradation_reason
                if cache_key is not None and self._cache is not None:
                    self._cache.set(cache_key, value, step.cache_ttl or 0)
                await self._emit(record, trace)
                return _StepOutcome(value=value, degraded=trace.status == "degraded")
            except TimeoutError:
                last_error = StepTimeoutError(step.name, timeout_s)
                if not is_retryable(last_error) or attempt > max_retries:
                    break
            except BaseException as exc:
                last_error = exc
                if not is_retryable(exc) or attempt > max_retries:
                    break
                if self._settings.backoff_jitter:
                    await asyncio.sleep(self._settings.backoff_base_s * attempt)

        assert last_error is not None
        tokens, cost = context.usage
        trace.tokens = tokens
        trace.cost = cost
        trace.latency_ms = int((time.perf_counter() - step_started) * 1000)
        trace.error_code = _error_code(last_error)
        trace.error_message = str(last_error)[:500]

        # Fallback: prefer a declared degradation over a failed run.
        if step.fallback is not None:
            try:
                value = await asyncio.wait_for(
                    step.fallback(context, inputs, last_error), timeout=timeout_s
                )
                trace.status = "degraded"
                trace.degradation_reason = (
                    context.degradation_reason
                    if context.degradation_reason is not DegradationReason.NONE
                    else DegradationReason.SCHEMA_REPAIR_FAILED
                )
                trace.output_digest = digest_of(value)
                await self._emit(record, trace)
                return _StepOutcome(value=value, degraded=True)
            except Exception as fallback_error:
                trace.error_message = f"fallback failed: {fallback_error}"[:500]

        # Optional steps degrade the run rather than failing it.
        if step.optional:
            trace.status = "degraded"
            trace.degradation_reason = DegradationReason.SCHEMA_REPAIR_FAILED
            await self._emit(record, trace)
            return _StepOutcome(value=None, degraded=True)

        trace.status = "failed"
        await self._emit(record, trace)
        raise _StepError(last_error, degraded=context.degraded)

    async def _emit(self, record: AgentRunRecord, trace: StepTrace) -> None:
        if self._tracker is not None:
            await self._tracker.record_step(record, trace)
        else:
            record.steps.append(trace)
            record.recompute_totals()

    @staticmethod
    def _cache_key(step: Step, inputs: Mapping[str, Any]) -> str:
        return f"step:{step.name}:{digest_of(inputs, length=32)}"


class _StepOutcome:
    __slots__ = ("degraded", "value")

    def __init__(self, *, value: Any, degraded: bool) -> None:
        self.value = value
        self.degraded = degraded


class _StepError(Exception):
    """Internal signal carrying the original cause out of the step runner."""

    def __init__(self, cause: BaseException, *, degraded: bool = False) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.degraded = degraded


def _error_code(error: BaseException) -> str:
    if isinstance(error, CareerForgeError):
        return error.code
    return type(error).__name__.upper()


def _first_prompt_ref(context: RunContext) -> str | None:
    refs = context.metadata.get("prompt_refs")
    if isinstance(refs, list) and refs:
        return str(refs[0])
    return None
