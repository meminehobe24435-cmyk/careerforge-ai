"""What a failed request leaves behind — the trace, and what it is allowed to contain.

The cases here start where ``test_failure_injection.py`` ends: a dependency has already failed and
there is nothing left to degrade to. The question is no longer "does the caller get a usable answer"
but "what does the product *record*, and is that record safe".

Two PHASE 12 defects live in this file, and both were measured rather than reasoned about:

* **a failed request left no run row at all.** ``get_db`` rolls the request's transaction back on any
  exception and the tracker wrote inside it, so a 400 or a 500 erased the trace — contradicting
  ``executor.py``'s comment that "observability is never lost". The fix is the failure journal
  (``services/failure_journal.py``), and ``test_disabling_the_journal_brings_the_lost_trace_back`` is
  what proves these tests can fail.
* **an unreported usage was written as zero.** With the structured path fixed, a run's counts are now
  ``NULL`` with an explicit ``usageStatus`` when nobody reported them, so "we were not told" and
  "the provider said zero" stop looking identical.

The third theme is the one the brief insisted on: the stored error must never carry an API key, a
bearer token or a whole résumé. The sanitiser's own unit suite is ``test_error_report.py``; what these
tests add is that the sanitiser is *in the path* — the assertions are on the row, after the request.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient
import pytest

from careerforge_ai.providers.heuristic import HeuristicProvider
from tests.conftest import EnvelopeCheck, UserFactory
from tests.failure_helpers import (
    job_run_committed,
    newest_run_ids,
    newest_runs,
    post,
    run_count,
    run_row,
)
from tests.failure_support import (
    BUDGET,
    CRASH,
    JD_TEXT,
    LEAKY,
    TIMEOUT,
    WRONG_SHAPE,
    DeclaredOutageProvider,
    ScriptedProvider,
    install_chain,
    journal_of,
)
from tests.leak_fixtures import (
    DOCUMENT_TEXT,
    FAKE_API_KEY,
    FAKE_BEARER,
    LEAKY_ERROR,
    RESUME_EMAIL,
    RESUME_PHONE,
)

#: The statuses ``models/observability.py`` allows, mirroring the ``status_valid`` CHECK constraint.
RUN_STATUSES = {"running", "succeeded", "failed", "degraded"}


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

    response = await post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 400, response.text
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "VALIDATION_ERROR"

    row, raised = await job_run_committed(app, account, ScriptedProvider(TIMEOUT))
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

    response = await post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 400, response.text
    assert envelope(response, success=False)["error"]["code"] == "VALIDATION_ERROR"
    assert provider.calls == 1, "a budget decision was retried"

    row, _ = await job_run_committed(app, account, ScriptedProvider(BUDGET))
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
    row, raised = await job_run_committed(app, account, ScriptedProvider(CRASH))
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
    row, raised = await job_run_committed(app, account, ScriptedProvider(WRONG_SHAPE))
    assert isinstance(raised, AttributeError), f"the bug was swallowed: {raised!r}"
    assert row.status == "failed"

    steps = {step["name"]: step for step in row.steps}
    assert steps["clean"]["status"] == "ok"
    assert steps["extract"]["status"] == "ok", "the model call itself did answer"
    assert steps["normalise"]["status"] == "failed"
    assert steps["normalise"]["error_code"] == "ATTRIBUTEERROR"
    assert steps["normalise"]["error_message"]
    assert "assess" not in steps, "the trace claims a step ran after the run had already aborted"


async def test_a_failed_request_still_leaves_a_trace_behind(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """A 400 from an AI endpoint now leaves a row: status ``failed``, the step that died, its code.

    PHASE 12 measured the opposite and recorded the contradiction: ``get_db`` rolls the request's
    transaction back on any exception and the tracker wrote inside that same transaction, so an
    outage left ``agent_runs`` exactly as it was and nothing about it was discoverable afterwards —
    while ``executor.py``'s comment promised that "observability is never lost".

    The fix is the failure journal (``services/failure_journal.py``): a run that ends ``failed`` is
    handed to the journal and written through its own short-lived session **after** the request
    transaction has settled. The assertions below are the fixed behaviour, and the two tests after
    this one are what prove they can fail — one by disabling the flush, one by reverting the
    tracker's journal branch to the PHASE 12 shape (quoted in the PHASE 13 report).
    """
    account = await make_user(display_name="Rollback")
    before = await run_count(app)
    install_chain(app, primary=ScriptedProvider(TIMEOUT), fallbacks=[], max_retries=0)

    response = await post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 400
    assert envelope(response, success=False)["error"]["code"] == "VALIDATION_ERROR"

    assert await run_count(app) == before + 1, (
        "a failed request left no trace: the run row went down with the transaction"
    )
    run_ids = await newest_run_ids(app)
    run = await run_row(app, str(run_ids[0]))
    assert run.status == "failed"
    assert run.error_code == "PROVIDER_UNAVAILABLE"
    assert run.error and "PROVIDER_UNAVAILABLE" in run.error
    assert run.finished_at is not None, "the run has no finish time, so its latency is unknown"
    assert run.latency_ms is not None and run.latency_ms >= 0

    steps = {step["name"]: step for step in run.steps}
    assert steps["clean"]["status"] == "ok", "the steps that completed were not kept"
    assert steps["extract"]["status"] == "failed"
    assert steps["extract"]["error_code"] == "PROVIDER_UNAVAILABLE"

    # The row's counts are NULL with an explicit status: the provider never answered, so nobody
    # measured its usage. A 0 here would be a claim that the call used no tokens.
    assert run.total_tokens is None and run.cost_usd is None
    assert run.usage_status == "unavailable"

    # …and it is readable through the API, which is where an operator would look for it.
    detail = await client.get(f"/api/v1/ai-runs/{run.id}", headers=account.headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()["data"]
    assert payload["status"] == "failed"
    assert payload["errorCode"] == "PROVIDER_UNAVAILABLE"
    assert payload["totalTokens"] is None
    assert payload["usageStatus"] == "unavailable"


async def test_a_failed_run_never_stores_a_key_a_token_or_a_document(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """A failed run's stored text is sanitised — and the sanitiser is what makes that true.

    The provider here fails with a message that contains a fake API key in the vendor's shape, a
    bearer token and a whole résumé. Two facts come out of running it, and both are worth recording:

    1. **The resilience layer flattens a provider's message.** What reaches the row is the chain's own
       classification — ``[PROVIDER_UNAVAILABLE] no provider in the chain could serve the request
       {'chain': ['scripted'], 'errors': ['scripted:PROVIDER_ERROR']}`` — so *this* particular
       provider cannot leak through this particular path. That is a useful accident, not a guarantee:
       it holds for provider errors and not for the other ways an exception reaches the executor.
    2. **The sanitiser is the guarantee, and it is tested where it can be reached.** The unit suite
       (``test_error_report.py``) drives it with the same leaky text and asserts every piece of it is
       gone, which is why the sanitising is applied at the *last* step before storage rather than at
       each raise site.

    So the assertion here is the invariant rather than a demonstration of the leak: whatever is in the
    row, none of the secret material is.
    """
    account = await make_user(display_name="Leaky provider")
    before = await run_count(app)
    row, raised = await job_run_committed(app, account, ScriptedProvider(LEAKY))
    assert raised is None
    assert await run_count(app) == before + 1
    assert row.status == "failed"
    assert row.error, "the run has no diagnosis at all"

    stored = f"{row.error} {row.error_code or ''}"
    for label, needle in (
        ("the API key", FAKE_API_KEY),
        ("the bearer value", FAKE_BEARER.split()[1]),
        ("the résumé's email", "zhangwei.private@example.com"),
        ("the résumé's phone", "13800001111"),
        ("the résumé's body", DOCUMENT_TEXT[:60]),
    ):
        assert needle not in stored, f"{label} was stored: {stored!r}"


async def test_the_sanitiser_runs_on_the_http_path_too(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """The same guarantee through a real request: the sanitised text is what gets stored.

    The provider here declares its own outage — it raises ``ProviderUnavailableError`` with a leaky
    message inside it — so the chain passes that message through instead of flattening it into its own
    classification. That is the case where the sanitiser is the *only* thing between an arbitrary
    exception and a browsable table, and it is the shape a real SDK produces: "upstream returned 400
    for body={...}" with the body quoted inside the message.

    Without the sanitiser this fails on the first forbidden needle, which is what makes it worth
    keeping. The sibling test one screen up uses a plain ``ProviderError`` and asserts only the
    invariant, because the chain's own classification never contains anything sensitive — a test that
    cannot fail there, and said so.

    **What is honestly lost.** This message is 486 characters of Chinese prose *around* the leak, so
    the document rule fires and the whole thing collapses to ``[omitted:486 chars]``. The secret
    removal and the length marker win; the sentence that says which upstream failed does not survive.
    That is the trade-off the sanitiser makes deliberately — a leaked résumé is worse than a vague
    error — and the machine-readable ``error_code`` beside it is what an operator filters on. A
    shorter message keeps its diagnosis, which ``test_error_report.py`` asserts directly.
    """
    account = await make_user(display_name="No leaks on the HTTP path")
    before = await run_count(app)
    install_chain(app, primary=DeclaredOutageProvider(LEAKY_ERROR), fallbacks=[], max_retries=0)

    response = await post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 400, response.text
    assert await run_count(app) == before + 1, "the failed request left no row to inspect"

    row = (await newest_runs(app, limit=1))[0]
    assert row.status == "failed"
    assert row.error, "the row carries no error at all"
    assert row.error_code, "the row carries no machine-readable classification"
    stored = row.error
    for label, needle in (
        ("the API key", FAKE_API_KEY),
        ("the bearer value", FAKE_BEARER.split()[1]),
        ("the résumé's email", RESUME_EMAIL),
        ("the résumé's phone", RESUME_PHONE),
        ("the résumé's body", DOCUMENT_TEXT[:60]),
    ):
        assert needle not in stored, f"{label} reached a stored row: {stored!r}"


async def test_disabling_the_journal_brings_the_lost_trace_back(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The proof that the row above comes from the journal and not from somewhere else.

    A test that cannot fail is worthless, so the persistence is explicitly disabled here: the
    journal's flush becomes a no-op, which is exactly the pre-PHASE-13 behaviour (the run was written
    inside the request transaction and went down with the rollback). The assertion then flips — no
    new row — and the test above is shown to be measuring the fix rather than a coincidence.

    Deliberately *not* asserting the old behaviour as the expectation: this test fails if the journal
    is ever wired somewhere that bypasses ``flush``, which is the regression worth catching.
    """
    account = await make_user(display_name="Journal disabled")
    before = await run_count(app)
    journal = journal_of(app)

    async def no_flush() -> int:
        return 0

    monkeypatch.setattr(journal, "flush", no_flush)
    install_chain(app, primary=ScriptedProvider(TIMEOUT), fallbacks=[], max_retries=0)

    response = await post(client, account, "/ai/analyze/jd", {"text": JD_TEXT})
    assert response.status_code == 400, response.text
    assert await run_count(app) == before, (
        "the failed run was persisted even though the journal was disabled, so the row in "
        "test_a_failed_request_still_leaves_a_trace_behind comes from somewhere else"
    )
