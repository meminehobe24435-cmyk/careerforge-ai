"""Observability regression: the invariants an operator relies on, over rows real calls wrote.

Nothing here asserts that a number is *large* — the deployment's zero-key path honestly spends
nothing. What is asserted is that the numbers cannot be **wrong**: a status the code cannot
produce, a negative count, a step chain whose clock runs backwards, a cache hit the run denies.
Each of those would make the AI Runs and Cost pages read as authoritative while lying.

Where an invariant does not hold today, the test pins the behaviour that was measured and says so
in its docstring, so the gap is executable rather than a footnote.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient

from careerforge_ai.providers.heuristic import HeuristicProvider
from tests.conftest import EnvelopeCheck, Session, UserFactory
from tests.failure_support import (
    JD_TEXT,
    MATCH_PAYLOAD,
    TIMEOUT,
    ScriptedProvider,
    install_chain,
    run_job_through_the_tracker,
)
from tests.observability_support import fetch_runs

#: The statuses ``models/observability.py`` allows. Anything else would be rejected by the
#: ``status_valid`` CHECK constraint, so a response outside this set means the payload and the
#: table disagree.
RUN_STATUSES = {"running", "succeeded", "failed", "degraded", "cancelled"}

#: The usage statuses the API may report, mirroring ``models/observability.py``'s
#: ``usage_status_valid`` constraint and ``careerforge_ai.schemas.common.UsageStatus``.
#: ``legacy`` is the one the API adds: rows written before PHASE 13 hold ``0`` from a writer that
#: had no status to record, so they are labelled rather than re-interpreted.
USAGE_STATUSES = {"reported", "estimated", "cached", "unavailable", "legacy"}


def _instant(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


async def _detail(client: AsyncClient, account: Session, run_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/v1/ai-runs/{run_id}", headers=account.headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ── the three statuses a run can carry ───────────────────────────────────────


async def test_a_successful_run_is_recorded_as_succeeded(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """A provider that answers gives ``succeeded`` — not ``degraded``.

    This needs a *non-deterministic* primary: the shipped chain's primary is the heuristic
    provider, which ``ResilientProvider`` marks degraded by construction, so the zero-key
    deployment can never produce this status at all (every run it performs is ``degraded``). The
    test therefore installs a provider that answers and is not deterministic.
    """
    account = await make_user(display_name="Succeeded")
    install_chain(app, primary=ScriptedProvider(), fallbacks=[HeuristicProvider()])

    response = await client.post(
        "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers
    )
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]
    assert data["meta"]["degraded"] is False

    run = await _detail(client, account, str(data["meta"]["run_id"]))
    assert run["status"] == "succeeded"
    assert run["status"] in RUN_STATUSES
    assert run["error"] is None
    assert all(step["status"] == "ok" for step in run["steps"]), run["steps"]
    assert run["latencyMs"] is not None and run["latencyMs"] >= 0


async def test_a_degraded_run_is_recorded_as_degraded(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """The status has to distinguish "answered by a fallback" from "answered normally".

    GAP, asserted on purpose: the *per-step* status is sticky. ``RunContext.degraded`` reads the
    provider chain, which is set by the last structured call and never cleared, so ``normalise`` and
    ``assess`` — pure functions that make no model call at all — are also written as ``degraded``.
    The run-level status is right; the step chain cannot be read as "these steps were served by a
    fallback", and on the shipped zero-key chain every model-touching step *and everything after
    it* is degraded, which is why the UI shows a degrade warning for steps that cannot degrade.
    """
    account = await make_user(display_name="Degraded")
    install_chain(app, primary=ScriptedProvider(TIMEOUT), fallbacks=[HeuristicProvider()])

    response = await client.post(
        "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers
    )
    assert response.status_code == 200, response.text
    data = envelope(response)["data"]

    run = await _detail(client, account, str(data["meta"]["run_id"]))
    assert run["status"] == "degraded"
    assert run["error"] is None, "a degraded run is not an error, and must not be recorded as one"
    degraded_steps = [step["name"] for step in run["steps"] if step["status"] == "degraded"]
    assert degraded_steps[0] == "extract", degraded_steps
    assert degraded_steps == ["extract", "normalise", "assess"], (
        "the step status is no longer run-sticky; this gap is closed"
    )
    assert run["steps"][0]["status"] == "ok", "the step before any model call was dragged along"


async def test_a_hard_failure_is_recorded_as_failed(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """With nothing left to degrade to, the run is ``failed`` and the error code is kept.

    Driven through the executor and the tracker directly, because that is where the record is
    built. Since PHASE 13 the *HTTP* path leaves this row too — the tracker hands a failed run to
    the failure journal and the middleware writes it after the request transaction has rolled back
    (``test_failure_injection.py::test_a_failed_request_still_leaves_a_trace_behind``).

    The provider here reported **nothing** — it raised before answering — so the counts are ``NULL``
    with ``usageStatus="unavailable"``, not ``0``. ``0`` would be a claim that the call used no
    tokens, which is a measurement nobody took.
    """
    account = await make_user(display_name="Failed")
    row, raised = await run_job_through_the_tracker(app, account, ScriptedProvider(TIMEOUT))

    assert raised is None
    assert row.status == "failed"
    assert row.status in RUN_STATUSES
    assert row.error and "PROVIDER_UNAVAILABLE" in row.error
    assert row.error_code == "PROVIDER_UNAVAILABLE"
    assert row.total_tokens is None and row.cost_usd is None
    assert row.usage_status == "unavailable"
    step = next(item for item in row.steps if item["name"] == "extract")
    assert step["status"] == "failed"
    assert step["error_code"] == "PROVIDER_UNAVAILABLE"


# ── no number may be negative ────────────────────────────────────────────────


async def test_no_run_or_call_reports_a_negative_number(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """Tokens, costs and latencies are non-negative everywhere they are exposed.

    A negative count would mean the accounting had gone wrong somewhere upstream, and a dashboard
    that prints one is worse than a dashboard that prints nothing. The scan covers every run in
    the window — including the ones other suites wrote — plus each run's individual model calls.

    ``null`` is allowed and is checked for meaning too (PHASE 13): it means the provider did not
    report the value, and the ``usageStatus`` beside it has to say so. A number and a status of
    ``unavailable`` together would be a payload that contradicts itself.
    """
    account = await make_user(display_name="Non negative")
    await client.post("/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers)
    await client.post("/api/v1/ai/match", json=MATCH_PAYLOAD, headers=account.headers)

    def non_negative(value: Any, what: str) -> None:
        assert value is None or value >= 0, f"{what} is negative: {value!r}"

    listing = await fetch_runs(client, account, limit="200")
    assert listing["items"], "no run to check"
    for run in listing["items"]:
        assert run["status"] in RUN_STATUSES, run
        assert run["usageStatus"] in USAGE_STATUSES, run
        non_negative(run["totalTokens"], "run.totalTokens")
        non_negative(run["promptTokens"], "run.promptTokens")
        non_negative(run["completionTokens"], "run.completionTokens")
        non_negative(run["costUsd"], "run.costUsd")
        non_negative(run["costCny"], "run.costCny")
        non_negative(run["latencyMs"], "run.latencyMs")
        assert run["stepCount"] >= 0
        if run["usageStatus"] == "unavailable" and run["totalTokens"] is None:
            assert run["costUsd"] is None, "a run with unknown tokens claims a known cost"

    for run in listing["items"][:12]:
        detail = await _detail(client, account, run["id"])
        for step in detail["steps"]:
            assert step["usageStatus"] in USAGE_STATUSES, step
            non_negative(step["tokens"], "step.tokens")
            non_negative(step["costUsd"], "step.costUsd")
            assert step["latencyMs"] >= 0
            assert step["attempts"] >= 1
        for call in detail["calls"]:
            assert call["usageStatus"] in USAGE_STATUSES, call
            non_negative(call["totalTokens"], "call.totalTokens")
            non_negative(call["costUsd"], "call.costUsd")
            non_negative(call["costCny"], "call.costCny")
            non_negative(call["latencyMs"], "call.latencyMs")

    costs = envelope(await client.get("/api/v1/ai-costs?range=all", headers=account.headers))[
        "data"
    ]
    assert costs["totals"]["runs"] >= 0 and costs["totals"]["tokens"] >= 0
    assert costs["totals"]["costUsd"] >= 0 and costs["totals"]["costCny"] >= 0
    assert costs["totals"]["modelCalls"] >= 0
    assert costs["unaccountedRuns"] >= 0
    for day in costs["days"]:
        assert day["tokens"] >= 0 and day["costUsd"] >= 0 and day["costCny"] >= 0
        assert day["runs"] >= 0

    stats = envelope(await client.get("/api/v1/cache/stats", headers=account.headers))["data"]
    assert stats["persistedHits"] >= 0
    for kind in stats["byKind"]:
        assert kind["entries"] >= 0 and kind["hits"] >= 0 and kind["bytes"] >= 0
    assert stats["process"]["processHits"] >= 0 and stats["process"]["processMisses"] >= 0


async def test_a_run_with_no_reported_usage_says_so_instead_of_printing_zero(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """The zero-key heuristic path is the honest case, and the payload has to carry it.

    It computes locally and spends nothing, so it has no usage to report — which is different from
    reporting zero. Measured on the shipped chain: ``usageStatus`` is ``unavailable``, the counts
    are ``null``, and the cost payload says the totals are a **floor** rather than a complete
    figure. A cost page that printed ``0`` here would be describing a measurement nobody took, and
    that is the defect PHASE 12 recorded (``docs/QUALITY.md`` §7.1).
    """
    account = await make_user(display_name="Unavailable usage")
    response = await client.post(
        "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers
    )
    assert response.status_code == 200, response.text
    run_id = str(envelope(response)["data"]["meta"]["run_id"])

    run = await _detail(client, account, run_id)
    assert run["provider"] == "heuristic", "this test pins the shipped zero-key deployment"
    assert run["usageStatus"] == "unavailable"
    assert run["totalTokens"] is None and run["promptTokens"] is None
    assert run["costUsd"] is None and run["costCny"] is None

    step = next(item for item in run["steps"] if item["name"] == "extract")
    assert step["usageStatus"] == "unavailable"
    assert step["tokens"] is None
    call = next(item for item in run["calls"] if item["operation"] == "structured")
    assert call["usageStatus"] == "unavailable"
    assert call["totalTokens"] is None and call["costUsd"] is None

    costs = envelope(await client.get("/api/v1/ai-costs?range=all", headers=account.headers))[
        "data"
    ]
    assert costs["unaccountedRuns"] >= 1
    assert any("下限" in note for note in costs["notes"]), (
        "the totals are a floor and the payload does not say so"
    )


async def test_usage_reported_by_a_provider_reaches_the_run_through_the_structured_path(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """A provider that *does* report usage has it recorded, on the path every agent uses.

    This is the other half of the fix and the one a paid deployment sees: ``structured_output``
    used to drop the provider's usage object, so ``totalTokens`` was structurally 0 no matter what
    the vendor reported. Now the numbers, their status and the per-call row all agree.
    """
    account = await make_user(display_name="Reported usage")
    install_chain(app, primary=ScriptedProvider(), fallbacks=[HeuristicProvider()])

    response = await client.post(
        "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers
    )
    assert response.status_code == 200, response.text
    run = await _detail(client, account, str(envelope(response)["data"]["meta"]["run_id"]))

    assert run["usageStatus"] == "reported"
    assert run["totalTokens"] == 150, "the usage the provider reported did not reach the run"
    assert run["costUsd"] > 0 and run["costCny"] > 0

    step = next(item for item in run["steps"] if item["name"] == "extract")
    assert step["usageStatus"] == "reported"
    assert step["tokens"] == 150

    calls = [item for item in run["calls"] if item["operation"] == "structured"]
    assert calls, "the structured call was not metered at all"
    for call in calls:
        assert call["usageStatus"] == "reported"
        assert call["totalTokens"] == 150
        assert call["provider"] == "scripted"
        assert call["model"] == "scripted-model", (
            "the structured row used to leave the model empty because the envelope was dropped"
        )
        assert call["requestId"], "the call cannot be joined to the request that caused it"


# ── the trace's clock ────────────────────────────────────────────────────────


async def test_step_timestamps_do_not_go_backwards(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """Within a run, the steps' clocks are ordered — and no step starts before its run.

    Checked on workflows whose steps are strictly sequential (the JD and match graphs), because a
    layer of concurrent steps is allowed to *finish* out of order (the emission order is their
    completion order), and asserting a stronger invariant than the design promises would be a
    flaky test rather than a stricter one.
    """
    account = await make_user(display_name="Clocks")
    for path, payload in (("/ai/analyze/jd", {"text": JD_TEXT}), ("/ai/match", MATCH_PAYLOAD)):
        response = await client.post(f"/api/v1{path}", json=payload, headers=account.headers)
        assert response.status_code == 200, response.text
        run = await _detail(client, account, str(response.json()["data"]["meta"]["run_id"]))

        started = [(_instant(step["startedAt"]), step["name"]) for step in run["steps"]]
        assert started, f"{path} recorded no steps"
        assert all(value is not None for value, _ in started), started
        ordered = [value for value, _ in started if value is not None]
        assert ordered == sorted(ordered), f"step clocks went backwards: {started}"
        first = _instant(run["startedAt"])
        assert first is not None
        assert ordered[0] >= first, "a step claims to have started before its run did"

        for step in run["steps"]:
            assert step["latencyMs"] >= 0


async def test_a_run_finishes_when_it_started(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """GAP, asserted on purpose: ``finished_at`` is a copy of ``started_at``.

    ``WorkflowExecutor.run`` assigns ``record.finished_at = record.started_at``, so the stored
    finish time records nothing and every run's real duration lives only in ``latency_ms``. The
    documented invariant (``finished_at >= started_at``) therefore holds trivially, and anything
    that computes a duration from the two timestamps gets zero.
    """
    account = await make_user(display_name="Finish time")
    response = await client.post(
        "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers
    )
    run = await _detail(client, account, str(response.json()["data"]["meta"]["run_id"]))
    started, finished = _instant(run["startedAt"]), _instant(run["finishedAt"])
    assert started is not None and finished is not None
    assert finished >= started, "the documented ordering invariant"
    assert finished == started, "finished_at is no longer a copy of started_at; gap closed"
    assert run["latencyMs"] and run["latencyMs"] > 0, (
        "the duration is only in latencyMs, so it must be measured"
    )


# ── the cache may not be denied by the row that used it ──────────────────────


async def test_a_cache_hit_inside_a_run_is_visible_on_the_run_row(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """The run reports the cache hit the cache layer counted — the gap is closed.

    PHASE 12 measured the opposite and wrote it down: ``metering.py`` says the run's flag "is raised
    to true as soon as either kind fired", while the *structured* path — the only path any agent
    uses — recorded ``cache_hit=False`` unconditionally, so the two pages could not be reconciled.

    Recording the envelope is what fixed it: a cache hit comes back with
    ``usageStatus="cached"``, the recorder counts it, and ``RunRecorder._mark_run_cached`` raises the
    flag. The assertions below are the *fixed* behaviour, and the cache-stats check that guards them
    still decides whether the test proves anything.
    """
    account = await make_user(display_name="Cache consistency")

    def llm_hits(stats: dict[str, Any]) -> int:
        return int(next(item for item in stats["byKind"] if item["kind"] == "llm")["hits"])

    before = envelope(await client.get("/api/v1/cache/stats", headers=account.headers))["data"]
    for _ in range(2):
        response = await client.post(
            "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers
        )
        assert response.status_code == 200, response.text
    after = envelope(await client.get("/api/v1/cache/stats", headers=account.headers))["data"]

    assert llm_hits(after) == llm_hits(before) + 1, (
        "the second identical request was not served from the cache, so this test proves nothing"
    )

    run = await _detail(client, account, str(response.json()["data"]["meta"]["run_id"]))
    assert run["cacheHit"] is True, "the run still denies a cache hit the cache layer counted"
    # GAP, asserted on purpose: the *response* still cannot see it. ``meta.cache_hit`` is built from
    # the executor's step cache (``_meta(cache_hit=...)`` is not even passed by the AI routes), and
    # the provider's hit is only known once the recorder flushes — after the response is assembled.
    # The row is right and the payload beside it is not; reported here rather than papered over.
    assert response.json()["data"]["meta"]["cache_hit"] is False
    # GAP, asserted on purpose: the *per-step* flags stay false. They come from the executor's
    # own step cache, and a provider cache hit is a different mechanism — recording it per step
    # would need the recorder to know which step was in flight when the provider answered, which it
    # does not. So the run level is right (raised as soon as either kind fired) and the step level
    # only ever reflects the step cache.
    assert run["cacheHit"] is True
    assert not any(step["cacheHit"] for step in run["steps"])
    # … and with the cache layer's own count.
    assert llm_hits(after) > 0

    # A cache hit is a fact, not a measurement: the row says ``cached`` with zero counts, rather
    # than reporting the original call's tokens onto the hit (which would bill them twice) or
    # claiming the usage is unknown (which it is not).
    call = next(item for item in run["calls"] if item["operation"] == "structured")
    assert call["usageStatus"] == "cached"
    assert call["totalTokens"] == 0
    assert call["costUsd"] == 0.0


# ── correlation ──────────────────────────────────────────────────────────────


async def test_a_run_cannot_be_joined_to_the_request_that_caused_it(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """GAP, asserted on purpose: ``agent_runs.request_id`` is always null for AI endpoints.

    ``models/observability.py`` promises the column "correlates with the ``X-Request-Id`` response
    header", and the envelope does carry one — but ``analyze_job`` accepts ``request_id`` from a
    dependency and never passes it on, so the row a support engineer finds in ``agent_runs`` cannot
    be tied to the log line for the request that produced it.
    """
    account = await make_user(display_name="Correlation")
    response = await client.post(
        "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers
    )
    payload = envelope(response)
    assert payload["requestId"] == response.headers["x-request-id"]

    run = await _detail(client, account, str(payload["data"]["meta"]["run_id"]))
    assert run["requestId"] is None, "the run now carries its request id; gap closed"
    assert run["userId"] is None, "the run is still not attributed to the caller either"


async def test_a_run_is_readable_by_any_authenticated_account(
    client: AsyncClient, make_user: UserFactory, envelope: EnvelopeCheck
) -> None:
    """GAP, asserted on purpose: the AI Runs read path has no ownership check.

    ``docs/API.md`` §1.2 requires another user's resource to answer ``404``. Measured: the route
    passes no ``user_id`` to ``ObservabilityService.list_runs`` (whose filter is skipped when it is
    absent) and ``get_run`` never checks ownership, so a run created by one account appears in
    another account's listing and is readable by id. Both rows here also carry ``user_id = NULL``,
    because the AI endpoints never attribute a run to the caller — so the exposure is not even
    confined to rows that were mis-attributed.
    """
    owner = await make_user(display_name="Owner")
    stranger = await make_user(display_name="Stranger")
    response = await client.post(
        "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=owner.headers
    )
    run_id = str(envelope(response)["data"]["meta"]["run_id"])

    listing = await fetch_runs(client, stranger, limit="200")
    assert run_id in {item["id"] for item in listing["items"]}, (
        "another account's run is no longer listed; gap closed"
    )
    detail = await client.get(f"/api/v1/ai-runs/{run_id}", headers=stranger.headers)
    assert detail.status_code == 200, "another account's run is no longer readable; gap closed"
    assert detail.json()["data"]["userId"] is None


async def test_a_run_created_seconds_ago_is_inside_a_one_hour_window(
    client: AsyncClient, make_user: UserFactory
) -> None:
    """``sinceHours=1`` must include a run that happened moments ago, in any timezone.

    This was an ``xfail`` until PHASE 12: the route built its window from
    ``datetime.now(tz=None)`` (local naive) while the column stores naive UTC, so on a UTC+8 host a
    run created seconds earlier fell *outside* a one-hour window. The fix is one call —
    ``utcnow()`` — and this test is now a plain assertion that fails on any host if the two clocks
    diverge again.
    """
    account = await make_user(display_name="Window")
    response = await client.post(
        "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers
    )
    assert response.status_code == 200, response.text

    unfiltered = await fetch_runs(client, account, limit="1")
    assert unfiltered["total"] >= 1
    windowed = await fetch_runs(client, account, sinceHours="1", limit="1")
    assert windowed["total"] >= 1, (
        "a run that happened seconds ago is outside a one-hour window: the filter compares "
        "local-naive time against a UTC column"
    )
