"""Failure injection: what the product does when the model, the retriever or a step misbehaves.

Every test drives the *real* agent, executor, tracker and metering layer; the only fake is the
provider the app was handed. The assertions are about product behaviour — the status the caller
gets, the trace that was written, the answer a user would read — because "no exception was raised"
is not a promise anyone can act on.

Where a claim in the code does not hold, the test asserts the behaviour that was **measured** and
says so in its docstring. A documented gap is worth more than a false green.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from httpx import AsyncClient
import pytest
from sqlalchemy import func, select

from careerforge_ai.errors import RetrievalError
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_api.models.observability import AgentRun
from tests.conftest import EnvelopeCheck, Session, UserFactory
from tests.failure_support import (
    BUDGET,
    CRASH,
    FABRICATED_ROLE,
    HANG,
    JD_TEXT,
    MALFORMED_JSON,
    MATCH_PAYLOAD,
    RATE_LIMITED,
    TIMEOUT,
    WRONG_SHAPE,
    ScriptedProvider,
    install_chain,
    run_job_through_the_tracker,
)

#: The claim the gate is driven with. Real material, so a verdict about it means something.
CLAIM = "使用 STM32 与 FreeRTOS 开发电机控制固件"


# ── helpers ──────────────────────────────────────────────────────────────────


async def _post(client: AsyncClient, account: Session, path: str, payload: dict[str, Any]) -> Any:
    return await client.post(f"/api/v1{path}", json=payload, headers=account.headers)


async def _run_row(app: FastAPI, run_id: str) -> AgentRun:
    """The row behind ``meta.run_id``, read from ``agent_runs`` rather than guessed from JSON."""
    async with app.state.session_factory() as db:
        row = await db.get(AgentRun, UUID(run_id))
    assert row is not None, "the run the response named was never written to agent_runs"
    return row


async def _run_count(app: FastAPI) -> int:
    async with app.state.session_factory() as db:
        return int(await db.scalar(select(func.count()).select_from(AgentRun)) or 0)


async def _steps(client: AsyncClient, account: Session, run_id: str) -> dict[str, dict[str, Any]]:
    response = await client.get(f"/api/v1/ai-runs/{run_id}", headers=account.headers)
    assert response.status_code == 200, response.text
    return {step["name"]: step for step in response.json()["data"]["steps"]}


async def _job_run_committed(
    app: FastAPI, account: Session, provider: Any, *, max_retries: int = 0
) -> tuple[AgentRun, BaseException | None]:
    return await run_job_through_the_tracker(app, account, provider, max_retries=max_retries)


# ── the model misbehaves ─────────────────────────────────────────────────────


@pytest.mark.parametrize("failure", [TIMEOUT, RATE_LIMITED])
async def test_a_transient_upstream_failure_degrades_instead_of_returning_500(
    failure: str,
    client: AsyncClient,
    make_user: UserFactory,
    app: FastAPI,
    envelope: EnvelopeCheck,
) -> None:
    """A read timeout or an HTTP 429 must not reach the caller as a server error.

    Both are retryable, so the chain retries once and then falls through to the heuristic tail
    (ADR-009). What is asserted: the caller gets a usable answer, the answer says it is degraded,
    the *trace* agrees with the response, and the retry really happened.
    """
    account = await make_user(display_name=f"Degraded {failure}")
    provider = ScriptedProvider(failure)
    install_chain(app, primary=provider, fallbacks=[HeuristicProvider()])

    response = await _post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 200, f"a degraded run answered {response.status_code}"
    data = envelope(response)["data"]

    assert data["meta"]["degraded"] is True, "a fallback answer was presented as a normal one"
    assert data["meta"]["degraded_reason"], "a degraded answer with no stated reason"
    assert data["analysis"]["degraded"] is True, "the analysis does not carry the degrade"
    assert data["analysis"]["role"], "the fallback answer carries no role at all"
    assert provider.calls == 2, "a transient failure was not retried exactly once"

    run = await _run_row(app, str(data["meta"]["run_id"]))
    assert run.status == "degraded"
    steps = await _steps(client, account, str(data["meta"]["run_id"]))
    assert steps["extract"]["status"] == "degraded"
    assert steps["clean"]["status"] == "ok", "a deterministic step was degraded by a model failure"


async def test_a_provider_that_hangs_times_out_on_the_chain_clock(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """A provider that *awaits* forever rather than raising must still be cut off.

    ``ResilientProvider`` wraps every attempt in ``asyncio.wait_for``, and that is the only thing
    between a hung upstream and a request that never returns. The chain timeout is set far below
    the provider's sleep, so a pass cannot be the sleep finishing first.

    GAP, asserted on purpose: the hang is *not* retried, although the explicit
    ``ProviderTimeoutError`` above is. ``asyncio.wait_for`` raises the builtin ``TimeoutError``,
    which ``is_retryable`` rejects (it only retries ``CareerForgeError`` codes and ``httpx``
    errors), so the two ways of discovering the same condition behave differently.
    """
    account = await make_user(display_name="Hung")
    provider = ScriptedProvider(HANG, hang_s=30.0)
    install_chain(app, primary=provider, fallbacks=[HeuristicProvider()], timeout_s=0.2)

    response = await _post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]
    assert data["meta"]["degraded"] is True
    assert provider.calls == 1, "the hang was retried after all; this gap is closed"

    run = await _run_row(app, str(data["meta"]["run_id"]))
    assert run.status == "degraded"
    assert run.latency_ms is not None and run.latency_ms >= 0


async def test_malformed_structured_output_is_never_presented_as_a_model_answer(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """A schema violation degrades; the garbage it was parsed from never reaches the caller.

    The failing provider's raw output is a distinctive truncated object (``GARBAGE_JSON``, with a
    fabricated role in it). If any of that text appears anywhere in the response, garbage has been
    laundered into a product answer — the one failure mode the validator layer exists to prevent.
    """
    account = await make_user(display_name="Malformed")
    provider = ScriptedProvider(MALFORMED_JSON)
    install_chain(app, primary=provider, fallbacks=[HeuristicProvider()])

    response = await _post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]

    serialised = json.dumps(data, ensure_ascii=False)
    assert FABRICATED_ROLE not in serialised, "the malformed output was served as an answer"
    assert "Fabricated Ltd" not in serialised
    assert data["meta"]["degraded"] is True
    assert provider.calls == 1, (
        "a schema violation is not transient; retrying it spends tokens on the same bad output"
    )

    run = await _run_row(app, str(data["meta"]["run_id"]))
    assert run.status == "degraded"


# ── the retriever is unavailable ─────────────────────────────────────────────


class _ExplodingRetriever:
    """A retrieval backend that is reachable but broken, as a dead vector store would be."""

    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, query: str, **kwargs: Any) -> Any:
        self.calls += 1
        raise RetrievalError("vector backend is unreachable")


async def test_an_unwired_retriever_is_reported_and_the_gate_still_answers(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """The shipped deployment has no retriever, and every surface says so.

    ``app.state.retriever`` is never set by ``create_app``/``lifespan``, so the claim gate runs on
    the material in the request alone. What matters is that the answer is still produced *and* that
    the absence is stated: an empty evidence set that looks like a genuine miss is the worst of the
    three possible outcomes.
    """
    account = await make_user(display_name="No retriever")
    assert getattr(app.state, "retriever", None) is None, (
        "this test pins the shipped configuration, which wires no retriever at all"
    )

    response = await _post(client, account, "/ai/validate/claim", {"claim": CLAIM})
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]
    assert data["sources"] == []
    assert any("检索" in warning for warning in data["meta"]["warnings"]), (
        f"the response does not state that retrieval did not happen: {data['meta']['warnings']}"
    )

    health = envelope(await client.get("/api/v1/system/health"))["data"]
    assert health["status"] == "degraded", "an API whose retrieval arm is unwired is not healthy"
    vector = health["checks"]["vector"]
    assert vector["status"] == "degraded"
    assert vector["reason"] and vector["detail"]

    capabilities = envelope(await client.get("/api/v1/ai/capabilities", headers=account.headers))[
        "data"
    ]
    assert capabilities["retrieval_available"] is False
    assert any("检索" in item for item in capabilities["limitations"])


async def test_the_step_chain_marks_a_retrieval_that_never_happened_as_ok(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """GAP, asserted on purpose: the trace and the response disagree about the retrieval.

    ``retrieve_phase`` returns ``{"degraded": True, "reason": "no retriever configured"}`` and the
    agent turns that into a warning — but the *executor* derives a step's status from the provider
    chain alone (``RunContext.degraded``), so the step is written as ``ok``. An operator reading the
    step chain cannot tell "retrieved nothing" from "did not retrieve", which is exactly the
    distinction the warning exists to make.
    """
    account = await make_user(display_name="Retrieval trace")
    response = await _post(client, account, "/ai/validate/claim", {"claim": CLAIM})
    data = envelope(response)["data"]
    assert any("检索" in warning for warning in data["meta"]["warnings"])

    steps = await _steps(client, account, str(data["meta"]["run_id"]))
    assert steps["retrieve"]["status"] == "ok"  # measured; the response says otherwise
    assert not steps["retrieve"]["errorCode"] and not steps["retrieve"]["errorMessage"]


async def test_a_broken_retrieval_backend_degrades_instead_of_returning_500(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """A retriever that raises must degrade the gate, not crash it.

    This test previously asserted the opposite — a 500 — because that is what the code did: the
    optional step recorded ``None`` into the dependency slot, and the decision phase raised
    ``AttributeError`` on the missing mapping. A verification product whose retrieval layer is
    unavailable must answer with the rules it still has and say that retrieval was unavailable;
    it is the one failure it cannot afford to crash on. PHASE 12 fixed ``retrieve_phase`` (it now
    catches and reports) and the three ``None``-unsafe reads in the gate.
    """
    account = await make_user(display_name="Broken retriever")
    app.state.retriever = _ExplodingRetriever()

    response = await _post(client, account, "/ai/validate/claim", {"claim": CLAIM})
    assert response.status_code == 200, response.text
    body = envelope(response)["data"]
    # The verdict still exists, and it is not a silent pass: the reason list says the evidence
    # could not be searched, which is what a reader needs to discount the verdict.
    assert body["status"] in {"unsupported", "partially_supported"}
    assert body["status"] != "supported", "a claim judged without retrieval must not be supported"
    reasons = " ".join(str(reason.get("message", "")) for reason in body.get("reasons", []))
    assert "检索" in reasons or "证据" in reasons, reasons


async def test_a_failed_step_does_not_take_down_what_succeeded(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """``/ai/match`` still returns the score when its only model step failed.

    The match workflow is deterministic except for ``narrate``, which is ``optional``: the number
    and its derivation are arithmetic and the prose is an addition. The run must say ``degraded``,
    the response must still carry the score, and the failure must be visible per step in AI Runs.
    """
    account = await make_user(display_name="Partial")
    provider = ScriptedProvider(TIMEOUT)
    # No fallback at all: the model step genuinely fails rather than degrading to another provider.
    install_chain(app, primary=provider, fallbacks=[], max_retries=0)

    response = await _post(client, account, "/ai/match", MATCH_PAYLOAD)
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]
    assert data["score"] > 0, "the deterministic score was lost with the model step"
    assert data["why"]["formula"], "the derivation is the explanation a failed model cannot change"
    assert data["narrative"] == "", "a narrative appeared although the narrator failed"
    assert data["meta"]["degraded"] is True

    run = await _run_row(app, str(data["meta"]["run_id"]))
    assert run.status == "degraded"

    steps = await _steps(client, account, str(data["meta"]["run_id"]))
    assert steps["prepare"]["status"] == "ok" and steps["score"]["status"] == "ok"
    assert steps["narrate"]["status"] == "degraded"
    assert steps["narrate"]["errorCode"] == "PROVIDER_UNAVAILABLE", steps["narrate"]
    assert steps["narrate"]["errorMessage"]


async def test_a_degraded_run_names_a_reason_that_explains_it(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """GAP, asserted on purpose: a run degraded by a *step* reports ``degraded_reason: "none"``.

    The run-level reason comes from the provider chain (``RunContext.degradation_reason``), and a
    step that failed before any model call was recorded leaves it at ``NONE``. The step trace does
    carry ``SCHEMA_REPAIR_FAILED``, and the warnings say "结果已降级（原因：none）" — so the payload
    contradicts itself exactly where a reader needs it most.
    """
    account = await make_user(display_name="Reason")
    install_chain(app, primary=ScriptedProvider(TIMEOUT), fallbacks=[], max_retries=0)

    response = await _post(client, account, "/ai/match", MATCH_PAYLOAD)
    data = envelope(response)["data"]
    assert data["meta"]["degraded"] is True
    assert data["meta"]["degraded_reason"] == "none"  # measured; the run *is* degraded
    assert any("none" in warning for warning in data["meta"]["warnings"])


# ── nothing can serve the request at all ─────────────────────────────────────


async def test_a_total_provider_outage_is_recorded_as_a_failed_run(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """GAP, asserted on purpose: a provider outage is reported to the caller as a 400.

    With no provider left in the chain the executor records ``failed`` / ``PROVIDER_UNAVAILABLE``
    correctly — and then the route, finding no analysis, raises ``VALIDATION_ERROR``
    ("岗位描述解析失败，请检查文本内容"), which blames the candidate's text for an upstream outage.
    ``AI_PROVIDER_UNAVAILABLE`` (503) is defined in ``core/errors.py`` and raised nowhere.
    """
    account = await make_user(display_name="Outage")
    install_chain(app, primary=ScriptedProvider(TIMEOUT), fallbacks=[], max_retries=0)

    response = await _post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 400, response.text
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "VALIDATION_ERROR"

    row, raised = await _job_run_committed(app, account, ScriptedProvider(TIMEOUT))
    assert raised is None, "a CareerForgeError must not escape the executor"
    assert row.status == "failed"
    assert row.error and "PROVIDER_UNAVAILABLE" in row.error
    step = next(item for item in row.steps if item["name"] == "extract")
    assert step["status"] == "failed"
    assert step["error_code"] == "PROVIDER_UNAVAILABLE"


async def test_an_exhausted_budget_is_not_converted_into_a_degradation(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """GAP, asserted on purpose: the spend ceiling fails the run instead of degrading it.

    ``routing.py`` states that "the resilience layer converts [``BudgetExceededError``] into a
    heuristic fallback", and ``errors.py`` pairs the decision with ``AI_BUDGET_EXCEEDED`` (429).
    Measured: ``ResilientProvider`` re-raises the budget error without consulting the fallbacks, so
    with a heuristic tail available the run still fails — and the caller sees the same 400 as a
    malformed request, which is indistinguishable from a typo in their own text.
    """
    account = await make_user(display_name="Budget")
    provider = ScriptedProvider(BUDGET)
    install_chain(app, primary=provider, fallbacks=[HeuristicProvider()])

    response = await _post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 400, response.text
    assert envelope(response, success=False)["error"]["code"] == "VALIDATION_ERROR"
    assert provider.calls == 1, "a budget decision was retried"

    row, _ = await _job_run_committed(app, account, ScriptedProvider(BUDGET))
    assert row.status == "failed"
    assert row.error and "BUDGET_EXCEEDED" in row.error


async def test_an_unexpected_crash_inside_the_provider_is_reported_as_an_outage(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """GAP, asserted on purpose: a bug in the provider layer is flattened into "outage".

    ``ProviderChainInfo.errors`` records ``scripted:ValueError``, but the exception the chain raises
    is ``ProviderUnavailableError`` — so nothing downstream (the run, the step trace, the API's
    error code) can tell a programming error from an unreachable upstream. The only trace of the
    real cause is the free text of the error message.
    """
    account = await make_user(display_name="Crash")
    row, raised = await _job_run_committed(app, account, ScriptedProvider(CRASH))
    assert raised is None, "a ValueError from inside the chain reached the caller"
    assert row.status == "failed"
    assert row.error and "PROVIDER_UNAVAILABLE" in row.error
    assert "ValueError" in row.error, "the chain's error list is the only record of the real cause"
    step = next(item for item in row.steps if item["name"] == "extract")
    assert step["error_code"] == "PROVIDER_UNAVAILABLE"


async def test_a_step_that_crashes_is_recorded_before_the_error_is_re_raised(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """A non-``CareerForgeError`` is re-raised — after the trace is persisted.

    The provider here answers with an object of the wrong shape, so the failure lands one step
    later (``normalise``) rather than at the model boundary. The executor must re-raise the bug
    (a bug is not an upstream failure) *and* leave a run that says which step died and why, which
    is the only thing that makes such a failure diagnosable after the fact.
    """
    account = await make_user(display_name="Wrong shape")
    row, raised = await _job_run_committed(app, account, ScriptedProvider(WRONG_SHAPE))
    assert isinstance(raised, AttributeError), f"the bug was swallowed: {raised!r}"
    assert row.status == "failed"

    steps = {step["name"]: step for step in row.steps}
    assert steps["clean"]["status"] == "ok"
    assert steps["extract"]["status"] == "ok", "the model call itself did answer"
    assert steps["normalise"]["status"] == "failed"
    assert steps["normalise"]["error_code"] == "ATTRIBUTEERROR"
    assert steps["normalise"]["error_message"]
    assert "assess" not in steps, "the trace claims a step ran after the run had already aborted"


async def test_a_failed_request_leaves_no_trace_behind(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """GAP, asserted on purpose: an error response rolls the run row back with the transaction.

    ``docs/ARCHITECTURE.md`` §9 and the executor's own comment promise that observability is never
    lost to a failure. Measured: ``get_db`` rolls back on any exception, and the tracker writes
    inside that same transaction — so a 400 or a 500 from an AI endpoint leaves ``agent_runs`` and
    ``llm_calls`` exactly as they were. Nothing about the outage is discoverable afterwards.
    """
    account = await make_user(display_name="Rollback")
    before = await _run_count(app)
    install_chain(app, primary=ScriptedProvider(TIMEOUT), fallbacks=[], max_retries=0)

    response = await _post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 400
    assert envelope(response, success=False)["error"]["code"] == "VALIDATION_ERROR"
    assert await _run_count(app) == before, (
        "a run row survived the error response; if that is now true, this gap is closed"
    )
