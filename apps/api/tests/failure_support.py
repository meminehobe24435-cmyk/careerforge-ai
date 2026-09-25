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

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import select

from careerforge_ai.agents import JobAgent
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.base import (
    LLMProvider,
)
from careerforge_ai.providers.resilience import ResilientProvider
from careerforge_ai.schemas.common import DegradationReason
from careerforge_api.models.observability import AgentRun
from careerforge_api.services.ai_service import DatabaseRunTracker
from careerforge_api.services.failure_journal import FailureJournal
from careerforge_api.services.metering import RunRecorder

__all__ = [
    "BUDGET",
    "CRASH",
    "DeclaredOutageProvider",
    "FABRICATED_ROLE",
    "GARBAGE_JSON",
    "HANG",
    "JD_TEXT",
    "LEAKY",
    "MALFORMED_JSON",
    "MATCH_PAYLOAD",
    "RATE_LIMITED",
    "ScriptedProvider",
    "TIMEOUT",
    "WRONG_SHAPE",
    "install_chain",
    "journal_of",
    "run_job_through_the_tracker",
]


# The document and secret fixtures live in ``tests/leak_fixtures.py`` and the scripted providers in
# ``tests/scripted_providers.py``; both are re-exported below so a suite has one import to write. They
# are not *defined* here, because a fixture with two homes ends up with two meanings.

from tests.scripted_providers import (
    BUDGET,
    CRASH,
    FABRICATED_ROLE,
    GARBAGE_JSON,
    HANG,
    LEAKY,
    MALFORMED_JSON,
    RATE_LIMITED,
    TIMEOUT,
    WRONG_SHAPE,
    DeclaredOutageProvider,
    ScriptedProvider,
)


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

    The HTTP path is what ``test_failure_injection.py`` uses to prove a failed request leaves a row
    (the request transaction is rolled back and the failure journal writes the trace afterwards);
    this helper drives the executor directly, where the *caller* owns the session, so a suite can
    assert on the run the workflow itself produced.

    A failed run is journaled rather than written to this session (``failure_journal.py``), so the
    journal is flushed here — exactly what the middleware does in production, one frame after the
    transaction settles. ``account`` is any object with an ``id``.

    Returns the persisted row and whatever escaped the executor (``None`` for the failures the
    executor converts into a ``CareerForgeError``-shaped outcome).
    """
    install_chain(app, primary=provider, fallbacks=[], max_retries=max_retries)
    raised: BaseException | None = None
    run_id: UUID | None = None
    journal = journal_of(app)
    async with app.state.session_factory() as db:
        recorder = RunRecorder(db, user_id=UUID(str(account.id)))
        executor = WorkflowExecutor(
            provider=app.state.provider,
            prompts=load_prompt_registry(app.state.settings.resolved_prompts_dir),
            tracker=DatabaseRunTracker(db, recorder=recorder, journal=journal),
            settings=ExecutorSettings(max_retries=max_retries, backoff_base_s=0.0),
        )
        try:
            outcome = await JobAgent().run(executor, text=JD_TEXT)
            run_id = outcome.record.id
        except BaseException as exc:  # the raise itself is part of what is measured
            raised = exc
        await recorder.flush()
        await db.commit()

    # The same flush the middleware performs, for the same reason: a failed run's row lives
    # outside this session's transaction.
    await journal.flush()

    if run_id is None:
        # The re-raised bug took the record with it; the run this call made is the newest.
        async with app.state.session_factory() as db:
            run_id = await db.scalar(
                select(AgentRun.id).order_by(AgentRun.started_at.desc()).limit(1)
            )

    row = await db_row(app, run_id)
    return row, raised


def journal_of(app: FastAPI) -> FailureJournal:
    """The app's failure journal, bound to its session factory (as the lifespan does)."""
    journal = getattr(app.state, "failure_journal", None)
    if journal is None:  # pragma: no cover - create_app always installs one
        journal = FailureJournal()
        app.state.failure_journal = journal
    if getattr(journal, "_session_factory", None) is None:
        journal.bind(app.state.session_factory)
    return journal


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
