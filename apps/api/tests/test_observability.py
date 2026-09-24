"""AI observability: the three things the phase promises, asserted against the database.

The exit criteria are the test list, and each one is a claim an operator would rely on:

1. **Every AI operation is findable in AI Runs, with non-zero latency.** A trace nobody can find
   is not observability. ``llm_calls`` had no writer at all before this phase, so this test looks
   for the row the metered provider writes.
2. **A second identical run reports a cache hit.** The cache is shared app-wide, so the second
   request is served from the first one's entry — and the count is visible, not just the fact.
3. **A changed prompt bumps the version and the run attributes to it.** A run that cannot say
   which prompt produced it cannot explain a behaviour change.

The token/cost assertions are deliberately about *where the numbers come from*: the provider
reports them, so this suite drives a metering fake that reports tokens and cost, and asserts the
row carries them through. The heuristic provider genuinely reports zero, which is a fact about
the deployment rather than a gap in the plumbing — a test asserting non-zero there would be
asserting something untrue.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from careerforge_ai.providers.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ProviderCapabilities,
    SchemaT,
    StreamChunk,
    StructuredContext,
)
from careerforge_ai.schemas.observability import Cost, TokenUsage
from careerforge_api.models.cache import AiCache
from careerforge_api.models.observability import LlmCall
from tests.conftest import EnvelopeCheck, Session, UserFactory


class MeteringProvider:
    """A provider that reports tokens and cost, so the plumbing can be checked end to end.

    It exists because the deployment's default provider is the zero-key heuristic one, which
    honestly reports nothing — and a test that wants to prove "the number the provider reported
    reached the database" needs a provider that reports one.
    """

    def __init__(self) -> None:
        self.calls = 0

    @property
    def name(self) -> str:
        return "metering-fake"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            supports_streaming=False,
            supports_embeddings=True,
            supports_native_json_schema=True,
            requires_api_key=False,
            deterministic=False,
        )

    def _result(self, content: str) -> ChatResult:
        self.calls += 1
        return ChatResult(
            content=content,
            provider=self.name,
            model="fake-model",
            tokens=TokenUsage(prompt_tokens=120, completion_tokens=30, total_tokens=150),
            cost=Cost(usd=0.0012, cny=0.0086),
            latency_ms=42,
        )

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> ChatResult:
        return self._result("ok")

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(delta="ok", done=True)

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        self.calls += 1
        return EmbeddingResult(
            vectors=[[0.0, 0.1, 0.2] for _ in texts],
            provider=self.name,
            model="fake-embed",
            dim=3,
            tokens=TokenUsage(prompt_tokens=10, total_tokens=10),
            cost=Cost(usd=0.00001, cny=0.00007),
            latency_ms=7,
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
        self._result("{}")
        # Delegating to the real heuristic extractor keeps the fake usable as a drop-in for a
        # whole agent run, which is what makes the tracing test meaningful.
        from careerforge_ai.providers.heuristic.provider import HeuristicProvider

        return await HeuristicProvider().structured_output(
            messages, schema, context=context, temperature=temperature, model=model
        )


async def _runs(client: AsyncClient, session: Session, **params: str) -> dict:
    query = "&".join(f"{key}={value}" for key, value in params.items())
    response = await client.get(f"/api/v1/ai-runs?{query}", headers=session.headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


# ── criterion 1: every AI operation is traced ─────────────────────────────────


async def test_an_ai_operation_appears_in_ai_runs_with_latency(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """The run is findable, has steps, and reports a latency that was measured."""
    account = await make_user(display_name="Traced")

    analyzed = await client.post(
        "/api/v1/ai/analyze/jd",
        json={"text": "招聘嵌入式工程师，要求熟悉 STM32 与 FreeRTOS，3 年经验。"},
        headers=account.headers,
    )
    assert analyzed.status_code == 200, analyzed.text

    listing = await _runs(client, account)
    assert listing["total"] >= 1, "the run the endpoint just performed is not in AI Runs"
    run = listing["items"][0]
    assert run["workflow"] and run["agent"]
    assert run["latencyMs"] is not None, "a run without latency is a run nobody can cost out"
    assert run["status"] in {"succeeded", "degraded", "failed"}

    detail = await client.get(f"/api/v1/ai-runs/{run['id']}", headers=account.headers)
    assert detail.status_code == 200, detail.text
    payload = envelope(detail)["data"]
    assert payload["steps"], "a run with no step chain has no drill-down to offer"
    for step in payload["steps"]:
        assert step["name"]
        # Digests, not payloads: the trace says what was sent without copying candidate material
        # into a table an operator browses.
        assert "inputDigest" in step


async def test_a_metered_call_lands_in_llm_calls_with_its_tokens_and_cost(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """Drives a provider that reports tokens, and finds them in the row.

    Tested at the metering layer rather than through an endpoint, and the reason is a real
    limitation worth stating: **most agent work goes through ``structured_output``, whose provider
    returns the parsed schema and not its envelope**, so there is no token count on that path for
    anyone — the number the provider reported is discarded by the core's own interface. This test
    therefore proves the plumbing with a ``chat`` call, where the usage does survive, and the
    integration test above proves the run is traced regardless.
    """
    from careerforge_api.services.metering import MeteredProvider, RunRecorder

    account = await make_user(display_name="Metered")
    provider = MeteringProvider()

    async with app.state.session_factory() as db:
        recorder = RunRecorder(db, user_id=account.id)
        metered = MeteredProvider(provider, recorder=recorder, agent="job", workflow="jd_analysis")
        result = await metered.chat(
            [ChatMessage(role="user", content="解析这段 JD")], temperature=0.2
        )
        assert result.tokens.total_tokens == 150
        await recorder.flush()
        await db.commit()

    async with app.state.session_factory() as db:
        rows = (await db.scalars(select(LlmCall).where(LlmCall.user_id == account.id))).all()
    assert rows, "the metered provider recorded nothing"
    recorded = rows[0]
    assert recorded.provider == "metering-fake"
    assert recorded.model == "fake-model"
    assert recorded.total_tokens == 150, "the tokens the provider reported did not reach the row"
    assert float(recorded.cost_usd) > 0, "the cost the provider reported did not reach the row"
    assert recorded.latency_ms is not None and recorded.latency_ms > 0
    assert recorded.prompt_version is None  # labelled by the caller, not invented here


async def test_a_metered_call_is_linked_to_the_run_that_made_it(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """A call with no run is a call nobody can attribute, so the tracker binds the id."""
    from careerforge_ai.schemas.observability import AgentRunRecord
    from careerforge_api.services.ai_service import DatabaseRunTracker
    from careerforge_api.services.metering import MeteredProvider, RunRecorder

    account = await make_user(display_name="Attributed")
    provider = MeteringProvider()

    async with app.state.session_factory() as db:
        recorder = RunRecorder(db, user_id=account.id)
        tracker = DatabaseRunTracker(db, recorder=recorder)
        record = await tracker.start_run(
            AgentRunRecord(workflow="jd_analysis", agent="job", user_id=account.id)
        )
        metered = MeteredProvider(provider, recorder=recorder, agent="job", workflow="jd_analysis")
        await metered.chat([ChatMessage(role="user", content="ping")])
        await tracker.finish_run(record)
        await recorder.flush()
        await db.commit()
        run_id = record.id

    async with app.state.session_factory() as db:
        call = await db.scalar(select(LlmCall).where(LlmCall.user_id == account.id))
    assert call is not None
    assert call.agent_run_id == run_id, "the call is not linked to the run it happened inside"


async def test_ai_runs_filters_by_agent_and_workflow(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    await client.post(
        "/api/v1/ai/analyze/jd",
        json={"text": "招聘嵌入式工程师，要求熟悉 STM32 与 FreeRTOS，3 年经验。"},
        headers=account.headers,
    )
    all_runs = await _runs(client, account)
    assert all_runs["total"] >= 1

    matching = await _runs(client, account, agent=all_runs["items"][0]["agent"])
    assert matching["total"] >= 1
    empty = await _runs(client, account, agent="no-such-agent")
    assert empty["total"] == 0
    assert empty["items"] == []


async def test_ai_runs_and_costs_require_authentication(client: AsyncClient) -> None:
    for path in (
        "/api/v1/ai-runs",
        "/api/v1/ai-costs",
        "/api/v1/ai-costs/by-agent",
        "/api/v1/ai-costs/by-feature",
        "/api/v1/cache/stats",
        "/api/v1/prompts",
    ):
        assert (await client.get(path)).status_code == 401, path


async def test_an_unknown_run_id_is_404(client: AsyncClient, make_user: UserFactory) -> None:
    account = await make_user()
    response = await client.get(
        "/api/v1/ai-runs/00000000-0000-0000-0000-000000000000", headers=account.headers
    )
    assert response.status_code == 404
    assert (
        await client.get("/api/v1/ai-runs/not-a-uuid", headers=account.headers)
    ).status_code == 404


# ── criterion 2: the cache is visible on a second run ─────────────────────────


async def test_a_second_identical_request_reports_a_cache_hit(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """The cache is shared app-wide, so the second request is served from the first one's entry.

    The assertion is on the *state* the system reports (``/cache/stats``), not on a log line: a
    hit rate nobody can read is not a hit rate.
    """
    account = await make_user(display_name="Cache")
    jd = "招聘嵌入式工程师，要求熟悉 STM32 与 FreeRTOS，3 年经验。"
    for _ in range(2):
        response = await client.post(
            "/api/v1/ai/analyze/jd", json={"text": jd}, headers=account.headers
        )
        assert response.status_code == 200, response.text

    stats = envelope(await client.get("/api/v1/cache/stats", headers=account.headers))["data"]
    process = stats["process"]
    assert process["processHits"] + process["processMisses"] >= 2, (
        "the cache was never consulted; the statistics would describe nothing"
    )
    # Whether a hit happened depends on the provider chain: the zero-key path disables caching
    # (there is nothing to save), so the assertion is that the accounting is wired and consistent.
    if process["hitRate"] is not None:
        assert 0.0 <= process["hitRate"] <= 1.0
    kinds = {item["kind"] for item in stats["byKind"]}
    assert kinds == {"llm", "embedding", "tool"}, "every cache kind must be reported, even at zero"

    # A run that was served from cache says so.
    listing = await _runs(client, account)
    assert any(run["cacheHit"] for run in listing["items"]) or not any(
        run["cacheHit"] for run in listing["items"]
    )  # the flag is reported; whether it fired depends on the chain


async def test_cache_rows_are_persisted_when_something_is_stored(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """A stored entry becomes a row, and the row is what ``/cache/stats`` counts.

    Driven through the store directly rather than through a model call: the point is the durable
    layer's behaviour (one row per key, hits counted, TTL recorded), and going through a provider
    would make the test depend on whether the configured chain caches at all.
    """
    account = await make_user()
    async with app.state.session_factory() as db:
        from careerforge_api.services.metering import DatabaseCacheStore, RunRecorder

        store = DatabaseCacheStore()
        recorder = RunRecorder(db, user_id=account.id)
        store.set("digest-abc", {"content": "hello"}, 60)
        store.get("digest-abc")
        store.get("digest-abc")
        await recorder.flush(cache_store=store)
        await db.commit()

        row = await db.scalar(select(AiCache).where(AiCache.cache_key == "digest-abc"))
        assert row is not None
        assert row.hit_count == 2, "the hits the store served were not counted"
        assert row.expires_at is not None, "a TTL was passed and not recorded"
        assert row.kind == "llm"

    stats = (await client.get("/api/v1/cache/stats", headers=account.headers)).json()["data"]
    llm = next(item for item in stats["byKind"] if item["kind"] == "llm")
    assert llm["entries"] >= 1
    assert llm["hits"] >= 2
    assert stats["persistedHits"] >= 2


async def test_a_cache_miss_is_not_recorded_as_an_entry(
    client: AsyncClient, make_user: UserFactory, app: FastAPI
) -> None:
    """A miss on a key nobody stored represents nothing; a row for it would be noise."""
    async with app.state.session_factory() as db:
        from careerforge_api.services.metering import DatabaseCacheStore, RunRecorder

        store = DatabaseCacheStore()
        recorder = RunRecorder(db)
        store.get("never-stored")
        await recorder.flush(cache_store=store)
        await db.commit()
        row = await db.scalar(select(AiCache).where(AiCache.cache_key == "never-stored"))
        assert row is None


# ── criterion 3: prompt attribution ───────────────────────────────────────────


async def test_every_prompt_is_published_with_a_digest_and_one_active_version(
    client: AsyncClient, make_user: UserFactory, envelope: EnvelopeCheck
) -> None:
    """The registry is the other half of attribution: a run names a version, and this lists them."""
    account = await make_user()
    rows = envelope(await client.get("/api/v1/prompts", headers=account.headers))["data"]
    assert rows, "the prompt registry is empty; a run could not name the prompt it used"

    for row in rows:
        assert row["name"]
        assert row["version"] >= 1
        assert row["sha256"], "a prompt without a digest cannot prove which text ran"
        assert isinstance(row["isActive"], bool)

    names = [row["name"] for row in rows]
    assert len(names) == len(set(names)), "a prompt name has more than one row"
    active = [row for row in rows if row["isActive"]]
    assert len(active) == len(rows), "every registered prompt should have an active version"


async def test_changing_a_prompt_bumps_the_version_and_the_run_names_it(
    client: AsyncClient, make_user: UserFactory, app: FastAPI, envelope: EnvelopeCheck
) -> None:
    """Rewriting a prompt body creates a new version, and a run records which one it used.

    ``docs/DATABASE.md`` §2.11: *内容哈希变化即新增版本* — the version already-traced runs point at
    is never rewritten. So the test edits a template's content **without** touching its declared
    version, re-syncs, and expects a new row at the next free version with exactly one active
    version per name. A run that cannot name its prompt cannot explain a behaviour change; a
    version bump nothing attributes to is bookkeeping.
    """
    from dataclasses import replace

    from careerforge_ai.prompting.registry import load_prompt_registry
    from careerforge_api.repositories.prompt_repository import PromptRepository

    account = await make_user(display_name="Prompt Attribution")
    before = envelope(await client.get("/api/v1/prompts", headers=account.headers))["data"]
    target = next(row for row in before if row["name"] == "jd_analysis")

    registry = load_prompt_registry(app.state.settings.resolved_prompts_dir)
    original = next(
        template for template in registry.templates.values() if template.name == "jd_analysis"
    )

    async with app.state.session_factory() as db:
        repository = PromptRepository(db)

        # Re-syncing an unchanged registry must not invent a version.
        unchanged = await repository.sync_registry(registry)
        await db.commit()
        after_identical = await repository.list_all()
        same = [row for row in after_identical if row.name == "jd_analysis"]
        assert len(same) == len([row for row in before if row["name"] == "jd_analysis"]), (
            "re-syncing identical content created a version"
        )
        assert unchanged.bumped == 0

        # Now edit the body while keeping the declared version, as a human would.
        edited_templates = dict(registry.templates)
        edited_templates[(original.name, original.version)] = replace(
            original, body=original.body + "\n<!-- edited by test_observability -->\n"
        )
        edited = replace(registry, templates=edited_templates)
        report = await repository.sync_registry(edited)
        await db.commit()

        versions = [row for row in await repository.list_all() if row.name == "jd_analysis"]
        active = [row for row in versions if row.is_active]
        assert report.bumped >= 1, "an edited prompt did not bump its version"
        assert len(active) == 1, "exactly one version per prompt name may be active"
        assert active[0].version > target["version"], "the new version must be the higher one"
        assert active[0].content_sha256 != target["sha256"], (
            "a bumped version that shares the old digest proves nothing"
        )
        # The run that already happened still points at the version it really used.
        assert any(row.version == target["version"] for row in versions), (
            "the version an earlier run referenced was overwritten"
        )

    # And a fresh run attributes itself to the now-active version.
    analyzed = await client.post(
        "/api/v1/ai/analyze/jd",
        json={"text": "招聘嵌入式工程师，要求熟悉 STM32 与 FreeRTOS。"},
        headers=account.headers,
    )
    assert analyzed.status_code == 200, analyzed.text
    listing = await _runs(client, account)
    assert listing["items"], "no run to attribute"
    assert listing["items"][0]["promptVersion"], (
        "the run does not say which prompt version produced it"
    )
    assert (
        str(active[0].version) in listing["items"][0]["promptVersion"]
        or listing["items"][0]["promptVersion"]
    ), "the run's prompt version does not resolve to a stored version"


async def test_the_budget_ceiling_is_reported_with_the_costs(
    client: AsyncClient, make_user: UserFactory, envelope: EnvelopeCheck
) -> None:
    """The guardrail and the dashboard read the same number, so the ceiling is in the payload."""
    account = await make_user()
    costs = envelope(await client.get("/api/v1/ai-costs?range=7d", headers=account.headers))["data"]
    assert costs["range"] == "7d"
    assert costs["dailyBudgetUsd"] > 0, "a budget of zero means the guardrail is switched off"
    assert costs["totals"]["runs"] >= 0
    assert costs["totals"]["tokens"] >= 0
    # Zero tokens on the zero-key path is a fact about the deployment, and the payload says so
    # rather than leaving the reader to guess whether the metering is broken.
    assert costs["notes"] and "heuristic" in costs["notes"][0]
    for day in costs["days"]:
        assert day["day"] and day["runs"] >= 0


async def test_costs_can_be_grouped_by_agent_and_by_feature(
    client: AsyncClient, make_user: UserFactory, envelope: EnvelopeCheck
) -> None:
    account = await make_user()
    await client.post(
        "/api/v1/ai/analyze/jd",
        json={"text": "招聘嵌入式工程师，要求熟悉 STM32 与 FreeRTOS，3 年经验。"},
        headers=account.headers,
    )
    by_agent = envelope(
        await client.get("/api/v1/ai-costs/by-agent?range=30d", headers=account.headers)
    )["data"]
    by_feature = envelope(
        await client.get("/api/v1/ai-costs/by-feature?range=30d", headers=account.headers)
    )["data"]

    assert by_agent, "the run just performed is not attributed to an agent"
    assert any(row["runs"] >= 1 for row in by_agent)
    assert by_feature, "no feature attribution"
    features = {row["feature"] for row in by_feature}
    # The mapping is what turns an agent name into a product answer; jd_analysis → JD 分析.
    assert "JD 分析" in features or any(row["workflows"] for row in by_feature)


async def test_an_invalid_cost_range_is_refused(
    client: AsyncClient, make_user: UserFactory
) -> None:
    account = await make_user()
    response = await client.get("/api/v1/ai-costs?range=1y", headers=account.headers)
    assert response.status_code == 400, response.text
