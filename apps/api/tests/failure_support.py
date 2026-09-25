"""Fakes for the negative-path suites: a provider that misbehaves, and one that works.

Three suites need to drive a *real* request through a provider that is scripted rather than
configured:

* ``test_failure_injection.py`` — the provider fails in one named way per test;
* ``test_observability_regression.py`` — a run of each documented status is needed, and the
  deployment's own chain cannot produce ``succeeded`` at all (its primary is the deterministic
  heuristic provider, which the resilience layer marks ``degraded`` by construction);
* ``test_cost_accounting.py`` — a provider that reports usage, so the "what a provider reported
  reached the database" path can be checked.

Kept in one module because three copies of "the provider timed out" would drift into three
meanings of it. Not named ``test_*`` so pytest does not collect it, the same convention as
``observability_support.py`` and ``application_support.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import select

from careerforge_ai.agents import JobAgent
from careerforge_ai.errors import (
    BudgetExceededError,
    ProviderRateLimitedError,
    ProviderTimeoutError,
    SchemaValidationError,
)
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    LLMProvider,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    StructuredContext,
)
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.providers.resilience import ResilientProvider
from careerforge_ai.schemas.common import DegradationReason
from careerforge_ai.schemas.observability import Cost, TokenUsage
from careerforge_api.models.observability import AgentRun
from careerforge_api.services.ai_service import DatabaseRunTracker
from careerforge_api.services.metering import RunRecorder

__all__ = [
    "BUDGET",
    "CRASH",
    "FABRICATED_ROLE",
    "GARBAGE_JSON",
    "HANG",
    "JD_TEXT",
    "MALFORMED_JSON",
    "MATCH_PAYLOAD",
    "RATE_LIMITED",
    "ScriptedProvider",
    "TIMEOUT",
    "WRONG_SHAPE",
    "install_chain",
    "run_job_through_the_tracker",
]

# ── how a scripted provider fails ────────────────────────────────────────────

#: An upstream that never answers within the chain's timeout (a real hang, not a raise).
HANG = "hang"
#: ``ProviderTimeoutError`` — what ``openai_compat`` raises for a read timeout.
TIMEOUT = "timeout"
#: ``ProviderRateLimitedError`` — what ``openai_compat`` raises for an HTTP 429.
RATE_LIMITED = "rate_limited"
#: Truncated JSON that cannot satisfy the declared schema (ADR-007's repair case).
MALFORMED_JSON = "malformed_json"
#: A bug inside the provider layer: not a ``CareerForgeError``, so the chain flattens it.
CRASH = "crash"
#: A model answer of the wrong shape: the call succeeds and the *next* step crashes on it.
WRONG_SHAPE = "wrong_shape"
#: The spend ceiling: ``RoutedProvider`` raises this once the budget is exhausted.
BUDGET = "budget"

#: The answer the malformed provider *intended* to send. If this string ever reaches a response,
#: a fabricated model answer has been presented as a real one and the test that watches for it
#: failed on purpose.
FABRICATED_ROLE = "FABRICATED-ROLE-XYZ"
#: Truncated on purpose: one unclosed object, which no JSON parser can turn into a schema.
GARBAGE_JSON = f'{{"role": "{FABRICATED_ROLE}", "company": "Fabricated Ltd"'


class ScriptedProvider:
    """A provider that reports usage when it works, and fails as told when it does not.

    ``capabilities.deterministic`` is ``False``, which is the whole reason this class exists
    beside the heuristic provider: ``ResilientProvider`` marks a *deterministic* primary as
    ``degraded`` even when it answered, so nothing in the shipped chain can produce a
    ``succeeded`` run. A non-deterministic primary that answers can.

    The successful ``structured_output`` delegates to the real :class:`HeuristicProvider` rather
    than returning a hand-built object: the answers a test asserts on are then the product's own,
    produced from the request's text.
    """

    def __init__(
        self,
        failure: str | None = None,
        *,
        name: str = "scripted",
        hang_s: float = 5.0,
        prompt_tokens: int = 120,
        completion_tokens: int = 30,
        cost_usd: float = 0.0012,
        cost_cny: float = 0.0086,
    ) -> None:
        self.failure = failure
        self.hang_s = hang_s
        self.tokens = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        )
        self.cost = Cost(usd=cost_usd, cny=cost_cny)
        self._name = name
        #: How many times the provider was asked. Proves whether the retry policy ran.
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self._name,
            supports_streaming=False,
            supports_embeddings=False,
            supports_native_json_schema=True,
            requires_api_key=True,
            deterministic=False,
        )

    def _raise(self) -> None:
        if self.failure == TIMEOUT:
            raise ProviderTimeoutError("upstream did not answer within the read timeout")
        if self.failure == RATE_LIMITED:
            raise ProviderRateLimitedError("upstream returned HTTP 429", retry_after_seconds=30)
        if self.failure == MALFORMED_JSON:
            raise SchemaValidationError(
                "model output did not satisfy the declared schema",
                details={"raw": GARBAGE_JSON, "schema": "ExtractedJD"},
            )
        if self.failure == CRASH:
            raise ValueError("bug inside the provider layer")
        if self.failure == BUDGET:
            raise BudgetExceededError(
                "daily AI budget exhausted", details={"limit_usd": 1.0, "spent_usd": 1.0}
            )
        assert self.failure in (None, WRONG_SHAPE), f"unknown scripted failure: {self.failure!r}"

    async def _fail_or_hang(self) -> None:
        """Hang first (so the *chain's* timeout fires), then raise if the script says so."""
        self.calls += 1
        if self.failure == HANG:
            await asyncio.sleep(self.hang_s)
        self._raise()

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        await self._fail_or_hang()
        return ChatResult(
            content="ok",
            provider=self.name,
            model="scripted-model",
            tokens=self.tokens,
            cost=self.cost,
            latency_ms=12,
        )

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        await self._fail_or_hang()
        yield StreamChunk(delta="ok", done=True, provider=self.name, model="scripted-model")

    async def embed(self, texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult:
        await self._fail_or_hang()
        return EmbeddingResult(
            vectors=[[0.0, 0.1] for _ in texts],
            provider=self.name,
            model="scripted-embed",
            dim=2,
            tokens=TokenUsage(prompt_tokens=10, total_tokens=10),
            cost=Cost(usd=0.00001, cny=0.00007),
            latency_ms=5,
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
        await self._fail_or_hang()
        if self.failure == WRONG_SHAPE:
            return _WrongShape()  # type: ignore[return-value]
        # The successful path is the product's own: the same heuristic extractor the zero-key
        # deployment runs, so the answer a test reads is derived from the request's text.
        return await HeuristicProvider().structured_output(
            messages, schema, context=context, temperature=temperature, model=model
        )


class _WrongShape:
    """What a provider returns when it ignored the schema it was handed.

    Every field the JD workflow asks for is present and of the wrong type, so the failure happens
    one step later — inside ``normalise``, on ``item.name`` — rather than at the provider
    boundary. That is the shape of a real "the model answered something else" incident.
    """

    role = "not a schema"
    company = "not a schema"
    required_skills = [object()]
    preferred_skills = [object()]
    bonus_skills = []


def install_chain(
    app: FastAPI,
    *,
    primary: LLMProvider,
    fallbacks: Sequence[LLMProvider] = (),
    timeout_s: float = 2.0,
    max_retries: int = 1,
    degraded_reason: DegradationReason = DegradationReason.PROVIDER_ERROR,
) -> ResilientProvider:
    """Replace the chain the app built with one a test controls.

    ``TimeoutError``/``ProviderError`` are retryable and ``is_retryable`` decides what happens
    next, so retries are left at one (the shipped default) with a zero backoff: the retry policy
    is exercised without a test spending seconds asleep. ``max_retries=0`` is used where the point
    is that a *non*-retryable failure is not retried.
    """
    chain = ResilientProvider(
        primary,
        fallbacks=tuple(fallbacks),
        max_retries=max_retries,
        backoff_base_s=0.0,
        timeout_s=timeout_s,
        degraded_reason=degraded_reason,
    )
    app.state.provider = chain
    return chain


# ── running work outside a request ───────────────────────────────────────────


async def run_job_through_the_tracker(
    app: FastAPI,
    account: Any,
    provider: LLMProvider,
    *,
    max_retries: int = 0,
) -> tuple[AgentRun, BaseException | None]:
    """Run the real JobAgent through the real executor and tracker, then **commit**.

    The HTTP path cannot show a failed run at all — an error response rolls the request's
    transaction back, taking the run row with it (see
    ``test_a_failed_request_leaves_no_trace_behind``) — so the executor's own contract is measured
    here, where the session decides when to commit. ``account`` is any object with an ``id``.

    Returns the persisted row and whatever escaped the executor (``None`` for the failures the
    executor converts into a ``CareerForgeError``-shaped outcome).
    """
    install_chain(app, primary=provider, fallbacks=[], max_retries=max_retries)
    raised: BaseException | None = None
    run_id: UUID | None = None
    async with app.state.session_factory() as db:
        recorder = RunRecorder(db, user_id=UUID(str(account.id)))
        executor = WorkflowExecutor(
            provider=app.state.provider,
            prompts=load_prompt_registry(app.state.settings.resolved_prompts_dir),
            tracker=DatabaseRunTracker(db, recorder=recorder),
            settings=ExecutorSettings(max_retries=max_retries, backoff_base_s=0.0),
        )
        try:
            outcome = await JobAgent().run(executor, text=JD_TEXT)
            run_id = outcome.record.id
        except BaseException as exc:  # the raise itself is part of what is measured
            raised = exc
        await recorder.flush()
        await db.commit()
        if run_id is None:
            # The re-raised bug took the record with it; the run this call made is the newest.
            run_id = await db.scalar(
                select(AgentRun.id).order_by(AgentRun.started_at.desc()).limit(1)
            )

    row = await db_row(app, run_id)
    return row, raised


async def db_row(app: FastAPI, run_id: UUID | None) -> AgentRun:
    async with app.state.session_factory() as db:
        row = await db.get(AgentRun, run_id)
    assert row is not None, "the executor did not persist the run it just performed"
    return row


# ── fixtures the suites share ────────────────────────────────────────────────
#: A realistic JD. The role, company and skills in it are what a correct answer must contain, so
#: an answer that does not mention them came from somewhere else — which is how the malformed
#: output test detects a fabricated answer.
JD_TEXT = """某科技
嵌入式软件工程师
工作地点：深圳

岗位职责：
1. 负责嵌入式软件的设计、开发与调试；

任职要求：
1. 本科及以上学历，3 年嵌入式开发经验；
2. 熟悉 STM32、FreeRTOS，掌握 C 语言；
3. 熟悉 CAN、SPI 通信协议。

加分项：了解 AUTOSAR。
"""

#: The minimum a ``POST /ai/match`` request needs. Both halves are supplied by the caller because
#: the tables those ids would point at do not exist yet (``docs/API.md`` §2.12).
MATCH_PAYLOAD: dict[str, Any] = {
    "job": {
        "company": "某科技",
        "role": "嵌入式软件工程师",
        "years_experience_min": 1.0,
        "required_skills": [
            {
                "canonical_id": "stm32",
                "raw_text": "STM32",
                "requirement": "required",
                "jd_evidence": "熟悉 STM32",
            },
            {
                "canonical_id": "can",
                "raw_text": "CAN",
                "requirement": "required",
                "jd_evidence": "熟悉 CAN",
            },
        ],
    },
    "profile": {
        "slug": "alex",
        "headline": "Embedded Engineer",
        "years_experience": 1.0,
        "skills": [
            {
                "skill": {
                    "canonical_id": "stm32",
                    "display_name": "STM32",
                    "category": "embedded",
                },
                "level": "strong",
                "evidence_count": 3,
            }
        ],
        "projects": [
            {
                "name": "Balance Robot",
                "summary": "基于 STM32 的两轮自平衡小车",
                "tech_stack": ["STM32", "FreeRTOS"],
            }
        ],
    },
}
