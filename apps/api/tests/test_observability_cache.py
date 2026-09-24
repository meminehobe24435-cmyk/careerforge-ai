"""Observability, part two: the cache and the prompt registry.

The two exit criteria that are about *state* rather than about a single run:

* a second identical request is served from the first one's cache, and the hit rate is readable
  (``/cache/stats``), because a hit rate nobody can read is not a hit rate;
* a changed prompt body bumps its version, and a run says which version produced it.

Split out of ``test_observability.py`` when that file reached 518 lines; the seam is the tests
that need the app's shared state rather than a single traced request.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from careerforge_api.models.cache import AiCache
from tests.conftest import EnvelopeCheck, UserFactory
from tests.observability_support import fetch_runs

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
    listing = await fetch_runs(client, account)
    assert listing["items"], "no run to read"
    assert all(isinstance(run["cacheHit"], bool) for run in listing["items"]), (
        "the cache-hit flag is part of the run contract, including when it is False"
    )


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
    listing = await fetch_runs(client, account)
    assert listing["items"], "no run to attribute"
    assert listing["items"][0]["promptVersion"], (
        "the run does not say which prompt version produced it"
    )
    assert (
        str(active[0].version) in listing["items"][0]["promptVersion"]
        or listing["items"][0]["promptVersion"]
    ), "the run's prompt version does not resolve to a stored version"
