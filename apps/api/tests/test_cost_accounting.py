"""Cost accounting: the sums on the pages must add up to the totals they print beside them.

The Cost page shows three views of the same money — a daily series, a per-agent breakdown and a
per-feature breakdown — and an operator reads them as one answer. So each view is checked against
the totals with an explicit tolerance (never bare float equality on money), and the windows are
checked to be real: a range that quietly ignores itself would make every downstream comparison
meaningless while still looking plausible.

Two kinds of rows are used, and the difference is stated rather than hidden: **endpoint-driven**
runs (the groupings are the product's own) and **seeded** runs written through the same
``DatabaseRunTracker``/``RunRecorder`` the product uses, carrying the usage a correctly-accounted
step would report. The second kind is necessary because no shipped step accounts usage at all —
see :func:`_seed_priced_run` and the gap recorded in ``test_usage_reported_by_the_provider_is_dropped``.
Without them every total here would be zero and the arithmetic would pass whatever it did.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import AsyncClient
import pytest
from sqlalchemy import func, or_, select

from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.observability import AgentRunRecord, Cost, StepTrace, TokenUsage
from careerforge_api.db.compat import utcnow
from careerforge_api.models.observability import AgentRun, LlmCall
from careerforge_api.services.ai_service import DatabaseRunTracker
from careerforge_api.services.metering import RunRecorder
from tests.conftest import EnvelopeCheck, Session, UserFactory
from tests.failure_support import JD_TEXT, MATCH_PAYLOAD, ScriptedProvider, install_chain
from tests.observability_support import fetch_runs

#: The money tolerance. The columns are ``NUMERIC(10,6)`` and both sides are rounded to six
#: decimals, so a thousandth of a cent is far below anything that could be a real disagreement.
TOLERANCE = 1e-6


async def _costs(client: AsyncClient, account: Session, path: str, range_key: str) -> dict:
    response = await client.get(f"/api/v1{path}?range={range_key}", headers=account.headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _seed_priced_run(
    app: FastAPI,
    *,
    user_id: str,
    agent: str,
    workflow: str,
    usd: float,
    cny: float,
    tokens: int,
    started_at: datetime | None = None,
) -> UUID:
    """Write one run with real usage, through the production tracker and recorder.

    The rows are produced by ``DatabaseRunTracker`` + ``RunRecorder`` — the same writers an
    endpoint uses — with a step trace that carries reported usage, because **no shipped step
    accounts any**: ``RunContext.structured`` never calls ``add_usage``, so a workflow driven
    through the API records zero tokens and zero cost no matter what the provider reported. A
    cost-aggregation test over endpoint-only rows could not distinguish correct arithmetic from a
    broken ``GROUP BY``, so the priced rows are the *input* the aggregation is checked on.
    """
    usage = TokenUsage(prompt_tokens=max(tokens - 10, 0), completion_tokens=10, total_tokens=tokens)
    cost = Cost(usd=usd, cny=cny)
    async with app.state.session_factory() as db:
        recorder = RunRecorder(db, user_id=UUID(user_id))
        tracker = DatabaseRunTracker(db, recorder=recorder)
        record = AgentRunRecord(
            id=uuid4(),
            user_id=UUID(user_id),
            workflow=workflow,
            agent=agent,
            trigger="seed",
            started_at=started_at or utcnow(),
        )
        await tracker.start_run(record)
        await tracker.record_step(
            record,
            StepTrace(
                name="extract",
                status="ok",
                tokens=usage,
                cost=cost,
                latency_ms=41,
                provider="seeded",
            ),
        )
        recorder.note_call(
            agent=agent,
            workflow=workflow,
            operation="structured",
            provider="seeded",
            model="seeded-model",
            prompt_version=None,
            latency_ms=41,
            tokens=usage,
            cost=cost,
            cache_hit=False,
            status="ok",
        )
        await tracker.finish_run(record)
        await recorder.flush()
        await db.commit()
        return record.id


async def _counts_in_window(
    app: FastAPI, *, days: int | None, user_id: UUID | None = None
) -> tuple[int, int]:
    """``(runs, calls)`` in the window the API's ``range`` argument describes, counted from the DB.

    The scope mirrors the service's own: one account plus the deployment's ownerless runs. Counting
    every row in the database (as this helper first did) only agreed with the API while the API was
    leaking other accounts' runs — PHASE 12 fixed that, and the helper had to follow.
    """
    since = None if days is None else utcnow() - timedelta(days=days)
    scope = (
        or_(AgentRun.user_id == user_id, AgentRun.user_id.is_(None))
        if user_id is not None
        else None
    )
    async with app.state.session_factory() as db:
        run_statement = select(func.count()).select_from(AgentRun)
        call_statement = (
            select(func.count())
            .select_from(LlmCall)
            .join(AgentRun, LlmCall.agent_run_id == AgentRun.id)
        )
        if scope is not None:
            run_statement = run_statement.where(scope)
            call_statement = call_statement.where(scope)
        if since is not None:
            run_statement = run_statement.where(AgentRun.started_at >= since)
            call_statement = call_statement.where(AgentRun.started_at >= since)
        return (
            int(await db.scalar(run_statement) or 0),
            int(await db.scalar(call_statement) or 0),
        )


# ── the three views agree ────────────────────────────────────────────────────


async def test_the_agent_and_feature_breakdowns_sum_to_the_totals(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """``sum(per agent) == sum(per feature) == totals``, for money and for tokens.

    The runs come from two different AI endpoints (so the agent and workflow groupings are the
    product's own) plus two priced runs on agents of their own (so the sums are not all zero).
    """
    account = await make_user(display_name="Costs")
    install_chain(app, primary=ScriptedProvider(), fallbacks=[HeuristicProvider()])
    for path, payload in (("/ai/analyze/jd", {"text": JD_TEXT}), ("/ai/match", MATCH_PAYLOAD)):
        response = await client.post(f"/api/v1{path}", json=payload, headers=account.headers)
        assert response.status_code == 200, response.text

    await _seed_priced_run(
        app,
        user_id=account.id,
        agent="audit-a",
        workflow="jd_analysis",
        usd=0.001234,
        cny=0.00883,
        tokens=111,
    )
    await _seed_priced_run(
        app,
        user_id=account.id,
        agent="audit-b",
        workflow="skill_gap",
        usd=0.002,
        cny=0.0143,
        tokens=222,
    )

    summary = await _costs(client, account, "/ai-costs", "all")
    by_agent = await _costs(client, account, "/ai-costs/by-agent", "all")
    by_feature = await _costs(client, account, "/ai-costs/by-feature", "all")
    totals = summary["totals"]

    raw = envelope(await client.get("/api/v1/ai-costs?range=all", headers=account.headers))["data"]
    assert raw["range"] == "all", "the range the totals were computed for is not stated"
    assert raw["notes"], "zero tokens must be explained rather than left to the reader"

    assert totals["costUsd"] > 0, "every total is zero, so this comparison proves nothing"
    assert len(by_agent) >= 2, "only one agent was attributed; the grouping is not exercised"
    assert len(by_feature) >= 2, "only one feature was attributed; the mapping is not exercised"
    assert {"audit-a", "audit-b"} <= {row["agent"] for row in by_agent}

    for rows, key in ((by_agent, "agent"), (by_feature, "feature")):
        assert sum(row["costUsd"] for row in rows) == pytest.approx(
            totals["costUsd"], abs=TOLERANCE
        ), f"the {key} breakdown does not add up to the total it is shown beside"
        assert sum(row["costCny"] for row in rows) == pytest.approx(
            totals["costCny"], abs=TOLERANCE
        )
        assert sum(row["tokens"] for row in rows) == totals["tokens"]

    # The daily series is the third view of the same money and must agree too.
    assert sum(day["runs"] for day in summary["days"]) == totals["runs"]
    assert sum(day["costUsd"] for day in summary["days"]) == pytest.approx(
        totals["costUsd"], abs=TOLERANCE
    )
    assert sum(day["tokens"] for day in summary["days"]) == totals["tokens"]

    # …and the agent breakdown's own runs column sums to the same run count.
    assert sum(row["runs"] for row in by_agent) == totals["runs"]
    assert sum(row["runs"] for row in by_feature) == totals["runs"]


async def test_the_totals_count_the_rows_they_summarise(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """``totals.runs`` is the number of runs in the window and ``modelCalls`` the number of calls.

    Counted from the database with the same window the route builds, so a payload that reported a
    page size, a cache size or a constant would fail here.
    """
    account = await make_user(display_name="Counters")
    await client.post("/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers)

    for range_key, days in (("7d", 7), ("all", None)):
        summary = await _costs(client, account, "/ai-costs", range_key)
        runs, calls = await _counts_in_window(app, days=days, user_id=UUID(account.id))
        assert summary["totals"]["runs"] == runs, f"range={range_key}"
        assert summary["totals"]["modelCalls"] == calls, f"range={range_key}"

    listing = await fetch_runs(client, account, limit="1")
    assert listing["total"] >= 1
    windowed = await _costs(client, account, "/ai-costs", "7d")
    assert windowed["totals"]["runs"] <= listing["total"], (
        "the totals must not count more runs than the listing can show"
    )


async def test_the_range_is_a_real_window_not_a_label(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """A run outside the window must be excluded from it — and included in ``all``.

    A range argument that only relabels the same numbers is the kind of decoration that makes an
    operator trust a comparison between two periods that were never different.
    """
    account = await make_user(display_name="Window")
    await _seed_priced_run(
        app,
        user_id=account.id,
        agent="ancient",
        workflow="jd_analysis",
        usd=0.5,
        cny=3.5,
        tokens=9000,
        started_at=utcnow() - timedelta(days=100),
    )

    recent = await _costs(client, account, "/ai-costs", "7d")
    everything = await _costs(client, account, "/ai-costs", "all")

    assert everything["totals"]["runs"] == recent["totals"]["runs"] + 1, (
        "a run from 100 days ago is inside the 7-day window"
    )
    assert everything["totals"]["costUsd"] == pytest.approx(
        recent["totals"]["costUsd"] + 0.5, abs=TOLERANCE
    )
    assert everything["totals"]["tokens"] == recent["totals"]["tokens"] + 9000

    agents_7d = {row["agent"] for row in await _costs(client, account, "/ai-costs/by-agent", "7d")}
    agents_all = {
        row["agent"] for row in await _costs(client, account, "/ai-costs/by-agent", "all")
    }
    assert "ancient" not in agents_7d, "the 7-day breakdown includes a 100-day-old agent"
    assert "ancient" in agents_all


async def test_a_seeded_run_is_attributed_to_its_feature(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """``workflow → feature`` is a mapping, and an unmapped workflow is reported as itself.

    ``WORKFLOW_FEATURES`` turns an agent name into the button a candidate recognises. An unmapped
    workflow must not silently vanish from the breakdown — a cost that disappears from the feature
    view is a cost nobody can act on.
    """
    account = await make_user(display_name="Feature")
    await _seed_priced_run(
        app,
        user_id=account.id,
        agent="mapped",
        workflow="resume_optimize",
        usd=0.01,
        cny=0.07,
        tokens=500,
    )
    await _seed_priced_run(
        app,
        user_id=account.id,
        agent="unmapped",
        workflow="workflow_with_no_feature",
        usd=0.02,
        cny=0.14,
        tokens=600,
    )

    features = await _costs(client, account, "/ai-costs/by-feature", "all")
    by_name = {row["feature"]: row for row in features}
    assert "简历优化" in by_name, sorted(by_name)
    assert by_name["简历优化"]["workflows"] == ["resume_optimize"]
    assert "workflow_with_no_feature" in by_name, "an unmapped workflow was dropped from the view"
    assert by_name["workflow_with_no_feature"]["costUsd"] == pytest.approx(0.02, abs=TOLERANCE)


# ── what the provider reported, and where it goes ────────────────────────────


async def test_usage_reported_by_the_provider_is_dropped_before_it_reaches_a_run(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """GAP, asserted on purpose: a provider that reports 150 tokens produces a run of zero.

    The AI core's structured path cannot carry usage at all: ``structured_output`` returns the
    parsed schema rather than the provider's envelope, ``RunContext.structured`` never calls
    ``add_usage`` (nothing in the product calls ``RunContext.chat`` either), and
    ``MeteredProvider.structured_output`` writes ``tokens=None, cost=None`` for that reason. So
    ``agent_runs.total_tokens``/``cost_usd`` and the ``llm_calls`` rows of every AI endpoint are
    structurally zero, and the Cost page's headline figure is zero on every deployment — including
    one with a paid key. ``metering.py``'s promise that a model call's "tokens, cost, latency"
    reach the row holds only for the ``chat``/``embedding`` paths, which no agent uses.
    """
    account = await make_user(display_name="Usage")
    provider = ScriptedProvider()
    install_chain(app, primary=provider, fallbacks=[HeuristicProvider()])

    response = await client.post(
        "/api/v1/ai/analyze/jd", json={"text": JD_TEXT}, headers=account.headers
    )
    assert response.status_code == 200, response.text
    assert provider.tokens.total_tokens == 150, "the provider does report usage on the chat path"

    detail = (
        await client.get(
            f"/api/v1/ai-runs/{response.json()['data']['meta']['run_id']}", headers=account.headers
        )
    ).json()["data"]
    assert detail["totalTokens"] == 0, "usage now reaches the run; this gap is closed"
    assert detail["costUsd"] == 0.0 and detail["costCny"] == 0.0

    assert detail["calls"], "the model call was not metered at all"
    for call in detail["calls"]:
        assert call["totalTokens"] == 0
        assert call["costUsd"] == 0.0
        assert call["operation"] == "structured"
        assert call["provider"] == "scripted", "the call does name the provider that served it"


async def test_a_run_outside_the_window_is_absent_from_the_agent_breakdown(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """The window applies to the breakdowns as well as to the totals — measured, not assumed."""
    account = await make_user(display_name="Breakdown window")
    await _seed_priced_run(
        app,
        user_id=account.id,
        agent="stale-agent",
        workflow="jd_analysis",
        usd=0.75,
        cny=5.2,
        tokens=8000,
        started_at=utcnow() - timedelta(days=200),
    )
    recent = await _costs(client, account, "/ai-costs/by-agent", "30d")
    everything = await _costs(client, account, "/ai-costs/by-agent", "all")
    assert "stale-agent" not in {row["agent"] for row in recent}
    stale = next(row for row in everything if row["agent"] == "stale-agent")
    assert stale["costUsd"] == pytest.approx(0.75, abs=TOLERANCE)
    assert stale["tokens"] == 8000
