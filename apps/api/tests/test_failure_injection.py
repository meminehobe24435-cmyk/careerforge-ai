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
from tests.conftest import EnvelopeCheck, UserFactory
from tests.failure_helpers import (
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

    response = await post(client, account, "/ai/validate/claim", {"claim": CLAIM})
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
    response = await post(client, account, "/ai/validate/claim", {"claim": CLAIM})
    data = envelope(response)["data"]
    assert any("检索" in warning for warning in data["meta"]["warnings"])

    steps = await steps_of(client, account, str(data["meta"]["run_id"]))
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

    Where the statement lives is asserted explicitly (PHASE 13). The response carries it as a
    *warning* — evidence that could not be searched — and not in ``reasons``: this verdict is
    reachable without retrieval (the rules blocked the claim first), so putting "the search failed"
    in a reason would claim the verdict depended on a search that never happened. An earlier version
    of this test looked for those words in ``reasons`` and could never find them.
    """
    account = await make_user(display_name="Broken retriever")
    app.state.retriever = _ExplodingRetriever()

    response = await post(client, account, "/ai/validate/claim", {"claim": CLAIM})
    assert response.status_code == 200, response.text
    body = envelope(response)["data"]
    # The verdict still exists, and it is not a silent pass: the reasons say what was found missing
    # and the warnings say the evidence could not be searched, which is what lets a reader discount
    # the verdict.
    assert body["status"] in {"unsupported", "partially_supported"}
    assert body["status"] != "supported", "a claim judged without retrieval must not be supported"
    assert body["reasons"], "a verdict without reasons is indistinguishable from a bug"
    warnings = " ".join(str(item) for item in body["meta"]["warnings"])
    assert "检索" in warnings, warnings


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
