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

from fastapi import FastAPI
from httpx import AsyncClient
import pytest

from careerforge_ai.errors import RetrievalError
from careerforge_ai.providers.heuristic import HeuristicProvider
from tests.claim_support import evidence_ready as _evidence_ready
from tests.conftest import EnvelopeCheck, UserFactory
from tests.failure_helpers import (
    newest_runs,
    post,
    run_row,
    steps_of,
)
from tests.failure_support import (
    FABRICATED_ROLE,
    HANG,
    JD_TEXT,
    MALFORMED_JSON,
    MATCH_PAYLOAD,
    RATE_LIMITED,
    TIMEOUT,
    ScriptedProvider,
    install_chain,
)

#: The claim the gate is driven with. Real material, so a verdict about it means something.
CLAIM = "使用 STM32 与 FreeRTOS 开发电机控制固件"


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

    response = await post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 200, f"a degraded run answered {response.status_code}"
    data = envelope(response)["data"]

    assert data["meta"]["degraded"] is True, "a fallback answer was presented as a normal one"
    assert data["meta"]["degraded_reason"], "a degraded answer with no stated reason"
    assert data["analysis"]["degraded"] is True, "the analysis does not carry the degrade"
    assert data["analysis"]["role"], "the fallback answer carries no role at all"
    assert provider.calls == 2, "a transient failure was not retried exactly once"

    run = await run_row(app, str(data["meta"]["run_id"]))
    assert run.status == "degraded"
    steps = await steps_of(client, account, str(data["meta"]["run_id"]))
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

    response = await post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]
    assert data["meta"]["degraded"] is True
    assert provider.calls == 1, "the hang was retried after all; this gap is closed"

    run = await run_row(app, str(data["meta"]["run_id"]))
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

    response = await post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]

    serialised = json.dumps(data, ensure_ascii=False)
    assert FABRICATED_ROLE not in serialised, "the malformed output was served as an answer"
    assert "Fabricated Ltd" not in serialised
    assert data["meta"]["degraded"] is True
    assert provider.calls == 1, (
        "a schema violation is not transient; retrying it spends tokens on the same bad output"
    )

    run = await run_row(app, str(data["meta"]["run_id"]))
    assert run.status == "degraded"


# ── the retriever is unavailable ─────────────────────────────────────────────


class _ExplodingRetriever:
    """A retrieval backend that is reachable but broken, as a dead vector store would be."""

    def __init__(self) -> None:
        self.calls = 0

    async def retrieve(self, query: str, **kwargs: Any) -> Any:
        self.calls += 1
        raise RetrievalError("vector backend is unreachable")


async def test_the_gate_builds_its_own_retriever_when_the_process_has_none(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """The shipped deployment configures no process retriever, and the gate retrieves anyway.

    ``app.state.retriever`` is still never set by ``create_app``/``lifespan`` — that part of the
    old test remains true — but since PHASE 14 the claim gate does not depend on it: the canonical
    ``POST /evidence/validate`` builds a hybrid retriever over the caller's own ``evidence`` rows
    per request (``services/retrieval_service.py``). What used to be asserted here was the
    *defect*: the stateless ``/ai/validate/claim`` read that unset property, retrieved nothing and
    reported ``sources: []`` with a "no retriever configured" warning for a claim the account's
    evidence supported. That endpoint is gone; this test now pins the behaviour that replaced it.
    """
    account = await make_user(display_name="No process retriever")
    assert getattr(app.state, "retriever", None) is None, (
        "this test pins the shipped configuration, which wires no process-level retriever"
    )

    response = await post(client, account, "/evidence/validate", {"text": CLAIM})
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]
    claim = data["claim"]
    assert claim["sources"] == [], "this account has no evidence, so there is nothing to cite"
    assert claim["status"] in {"unsupported", "contradicted"}, claim
    assert claim["reasons"], "a refusal must explain itself"
    assert not any("no retriever configured" in warning for warning in data["warnings"]), (
        f"the gate reported a missing retriever, which is what PHASE 14 fixed: {data['warnings']}"
    )

    health = envelope(await client.get("/api/v1/system/health"))["data"]
    assert health["status"] == "degraded", "an API whose vector arm is not durable is not healthy"
    vector = health["checks"]["vector"]
    assert vector["status"] == "degraded"
    assert vector["reason"] and vector["detail"]

    capabilities = envelope(await client.get("/api/v1/ai/capabilities", headers=account.headers))[
        "data"
    ]
    assert capabilities["retrieval_available"] is False
    assert any("检索" in item for item in capabilities["limitations"])
    # The limitation must not claim the gate is blind to the evidence base: it retrieves from it
    # on every request, and that sentence would be a false statement inside a payload whose whole
    # purpose is to state what does not work.
    assert not any("不会去检索证据库" in item for item in capabilities["limitations"])


async def test_a_broken_retrieval_backend_degrades_instead_of_returning_500(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck, monkeypatch
) -> None:
    """A retriever that raises must degrade the gate, not crash it — and must say so.

    This test previously asserted the opposite — a 500 — because that is what the code did: the
    optional step recorded ``None`` into the dependency slot, and the decision phase raised
    ``AttributeError`` on the missing mapping. A verification product whose retrieval layer is
    unavailable must answer with the rules it still has and say that retrieval was unavailable;
    it is the one failure it cannot afford to crash on. PHASE 12 fixed ``retrieve_phase`` (it now
    catches and reports) and the three ``None``-unsafe reads in the gate.

    PHASE 14 moved it onto the canonical endpoint. The failure is injected where the gate actually
    gets its retriever (``services/retrieval_service.build_retriever``, called per request by
    ``ResumeService.validate``) rather than by setting ``app.state.retriever``, which nothing
    reads any more.

    Where the statement lives is asserted explicitly. The response carries it as a *warning* —
    evidence that could not be searched — and not in ``reasons``: this verdict is reachable
    without retrieval (the rules blocked the claim first), so putting "the search failed" in a
    reason would claim the verdict depended on a search that never happened.
    """
    account = await make_user(display_name="Broken retriever")
    await _evidence_ready(client, envelope, account)

    from careerforge_api.services import resume_service

    broken = _ExplodingRetriever()

    async def exploding_retriever(*args: Any, **kwargs: Any) -> _ExplodingRetriever:
        return broken

    monkeypatch.setattr(resume_service, "build_retriever", exploding_retriever)

    response = await post(client, account, "/evidence/validate", {"text": CLAIM})
    assert response.status_code == 200, response.text
    body = envelope(response)["data"]
    assert broken.calls > 0, "the gate never asked the broken retriever, so nothing was proven"
    # The verdict still exists, and it is not a silent pass: the reasons say what was found missing
    # and the warnings say the evidence could not be searched, which is what lets a reader discount
    # the verdict.
    assert body["degraded"] is True
    assert body["claim"]["status"] in {"unsupported", "partially_supported"}
    assert body["claim"]["status"] != "supported", (
        "a claim judged without retrieval must not be supported"
    )
    assert body["claim"]["reasons"], "a verdict without reasons is indistinguishable from a bug"
    warnings = " ".join(str(item) for item in body["warnings"])
    assert "检索" in warnings, warnings

    # The trace agrees with the response, and it is reachable from the run table: a degraded
    # verdict leaves an ``agent_runs`` row even when the caller only reads the HTTP body.
    run = await newest_runs(app, limit=1)
    assert run and run[0].workflow == "claim_validate", [item.workflow for item in run]
    assert run[0].status == "degraded", run[0].status
    steps = await steps_of(client, account, str(run[0].id))
    # GAP, asserted on purpose: ``retrieve_phase`` reported the degradation but the *executor*
    # derives a step's status from the provider chain alone, so the step is written ``ok``. An
    # operator reading the step chain cannot tell "retrieved nothing" from "did not retrieve",
    # which is exactly the distinction the warning exists to make.
    assert steps["retrieve"]["status"] == "ok"  # measured; the response says otherwise
    assert not steps["retrieve"]["errorCode"] and not steps["retrieve"]["errorMessage"]


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

    response = await post(client, account, "/ai/match", MATCH_PAYLOAD)
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]
    assert data["score"] > 0, "the deterministic score was lost with the model step"
    assert data["why"]["formula"], "the derivation is the explanation a failed model cannot change"
    assert data["narrative"] == "", "a narrative appeared although the narrator failed"
    assert data["meta"]["degraded"] is True

    run = await run_row(app, str(data["meta"]["run_id"]))
    assert run.status == "degraded"

    steps = await steps_of(client, account, str(data["meta"]["run_id"]))
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

    response = await post(client, account, "/ai/match", MATCH_PAYLOAD)
    data = envelope(response)["data"]
    assert data["meta"]["degraded"] is True
    assert data["meta"]["degraded_reason"] == "none"  # measured; the run *is* degraded
    assert any("none" in warning for warning in data["meta"]["warnings"])
