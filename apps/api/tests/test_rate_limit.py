"""Rate limiting: the documented groups, budgets, headers and ``429`` body.

``docs/API.md`` §1.7 fixes the numbers and the response headers. The limiter is
tested through a real request against an app configured with a tiny budget, because
that is the only way to prove the middleware is actually in the chain in the
documented position.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest_asyncio

from careerforge_api.core.config import APISettings
from careerforge_api.main import create_app
from careerforge_api.middleware.ratelimit import (
    HEADER_LIMIT,
    HEADER_REMAINING,
    HEADER_RESET,
    RateLimitRule,
    TokenBucketLimiter,
    classify_request,
)
from tests.conftest import EnvelopeCheck


@pytest_asyncio.fixture
async def tight_app(settings_factory) -> AsyncIterator[FastAPI]:  # type: ignore[no-untyped-def]
    """An app whose authentication budget is 2 requests per minute."""
    settings: APISettings = settings_factory(rate_limit_auth_per_min=2)
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        yield application


@pytest_asyncio.fixture
async def tight_client(tight_app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=tight_app), base_url="http://testserver"
    ) as http:
        yield http


async def test_exceeding_the_auth_budget_returns_429_with_retry_after(
    tight_client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    first = await tight_client.post("/api/v1/auth/demo")
    second = await tight_client.post("/api/v1/auth/demo")
    third = await tight_client.post("/api/v1/auth/demo")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429

    payload = envelope(third, success=False)
    assert payload["error"]["code"] == "RATE_LIMITED"
    assert int(third.headers["retry-after"]) >= 1
    assert third.headers["x-ratelimit-limit"] == "2"
    assert third.headers["x-ratelimit-remaining"] == "0"
    assert int(third.headers["x-ratelimit-reset"]) >= 1


async def test_successful_responses_publish_the_rate_limit_headers(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/system/health")
    assert response.status_code == 200
    assert response.headers[HEADER_LIMIT.lower()] == "10000"
    assert int(response.headers[HEADER_REMAINING.lower()]) >= 0
    assert int(response.headers[HEADER_RESET.lower()]) >= 0


async def test_retry_after_header_is_absent_on_success(client: AsyncClient) -> None:
    response = await client.get("/api/v1/system/health")
    assert "retry-after" not in response.headers


def test_endpoint_groups_map_to_the_documented_budgets(settings: APISettings) -> None:
    """§1.7: auth 10/min/IP · read 300/min/user · write 60/min/user · AI 20/min/user."""
    assert classify_request("POST", "/api/v1/auth/login", settings).group == "auth"
    assert classify_request("POST", "/api/v1/auth/register", settings).scope == "ip"
    assert classify_request("GET", "/api/v1/jobs", settings).group == "read"
    assert classify_request("PATCH", "/api/v1/profile", settings).group == "write"
    assert classify_request("POST", "/api/v1/jobs/analyze", settings).group == "ai"
    assert classify_request("POST", "/api/v1/documents", settings).group == "upload"

    auth = classify_request("POST", "/api/v1/auth/login", settings)
    assert (auth.limit, auth.window_seconds) == (settings.rate_limit_auth_per_min, 60.0)
    read = classify_request("GET", "/api/v1/jobs", settings)
    assert (read.limit, read.window_seconds) == (settings.rate_limit_read_per_min, 60.0)
    write = classify_request("POST", "/api/v1/jobs", settings)
    assert (write.limit, write.window_seconds) == (settings.rate_limit_write_per_min, 60.0)
    ai = classify_request("POST", "/api/v1/jobs/analyze", settings)
    assert (ai.limit, ai.window_seconds) == (settings.rate_limit_ai_per_min, 60.0)
    upload = classify_request("POST", "/api/v1/documents", settings)
    # The hourly bucket is a *setting* since PHASE 14 (it was hard-coded at 20 in the middleware), so
    # this asserts three things the hard-coded version could not distinguish: the classifier uses the
    # configured value, the shipped default is still the documented 20/hour, and raising it works.
    assert (upload.limit, upload.window_seconds) == (settings.rate_limit_upload_per_hour, 3600.0)
    assert APISettings.model_fields["rate_limit_upload_per_hour"].default == 20, (
        "the documented production default is 20 uploads per hour"
    )
    raised = classify_request(
        "POST", "/api/v1/documents", settings.model_copy(update={"rate_limit_upload_per_hour": 500})
    )
    assert raised.limit == 500, (
        "the upload budget must be configurable: a hard-coded limit cannot be raised for a test "
        "suite or a self-hosted deployment, and the workaround is always worse than the setting"
    )


def test_the_ai_budget_counts_model_spend_not_reads(settings: APISettings) -> None:
    """The AI budget bounds model spend, so only the requests that can spend are in it.

    ``GET /jobs/{id}/match`` reads the stored row (``routers/jobs.py`` says so itself: the stored
    response cannot even report evidence coverage, because no column holds it) and
    ``GET /ai/interview/{id}`` reads the session store. Neither reaches a provider. Charging them to
    the twenty-a-minute AI budget let a user exhaust it by reloading a page — measured in PHASE 14,
    where the browser suite collected two ``429``s, one of them on `GET /ai/interview/{id}`.
    """
    # Reads of AI state are reads.
    assert classify_request("GET", "/api/v1/jobs/abc/match", settings).group == "read"
    assert classify_request("GET", "/api/v1/ai/interview/abc", settings).group == "read"
    # Removing an AI resource is a write.
    assert classify_request("DELETE", "/api/v1/ai/interview/abc", settings).group == "write"

    # Everything that can spend a token is still on the strict budget, with the documented limit.
    spending = [
        ("POST", "/api/v1/jobs/analyze"),
        ("POST", "/api/v1/jobs/abc/match"),
        ("POST", "/api/v1/ai/match"),
        ("POST", "/api/v1/ai/analyze/jd"),
        ("POST", "/api/v1/ai/interview/start"),
        ("POST", "/api/v1/ai/interview/abc/answer"),
        ("POST", "/api/v1/ai/interview/abc/finish"),
        ("POST", "/api/v1/resume/optimize"),
    ]
    for method, path in spending:
        rule = classify_request(method, path, settings)
        assert rule.group == "ai", f"{method} {path} must stay on the AI budget"
        assert (rule.limit, rule.window_seconds) == (settings.rate_limit_ai_per_min, 60.0)
    assert APISettings.model_fields["rate_limit_ai_per_min"].default == 20, (
        "the documented production default is 20 AI requests per minute"
    )


async def test_a_page_read_does_not_consume_the_ai_budget(
    settings_factory, envelope: EnvelopeCheck
) -> None:
    """The behavioural half: reads must not take tokens out of the AI bucket.

    The requests below are unauthenticated, which is deliberate — the limiter sits *outside* the auth
    dependency and buckets by identity before any handler runs, so a `401` proves the bucket was
    charged. With a budget of two, five reads of an AI path must leave both tokens for the two posts
    that follow, and the third post must be refused.
    """
    settings: APISettings = settings_factory(rate_limit_ai_per_min=2)
    application = create_app(settings)

    async with (
        application.router.lifespan_context(application),
        AsyncClient(transport=ASGITransport(app=application), base_url="http://testserver") as http,
    ):
        for _ in range(5):
            response = await http.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000/match")
            assert response.status_code in {401, 404}, response.text

        first = await http.post("/api/v1/ai/match", json={})
        second = await http.post("/api/v1/ai/match", json={})
        assert first.status_code == 401, first.text
        assert second.status_code == 401, (
            "five reads consumed the AI budget: a GET must be charged to `read`, not to the budget "
            "that exists to bound model spend"
        )

        third = await http.post("/api/v1/ai/match", json={})
        assert third.status_code == 429, "the AI budget must still refuse the third call"
        envelope(third, success=False)


async def test_token_bucket_refills_over_time(settings: APISettings) -> None:
    """A bucket must not stay empty: the refill rate is the documented budget."""
    limiter = TokenBucketLimiter()
    rule = RateLimitRule("read", limit=60, window_seconds=1.0, scope="user")

    decisions = [await limiter.check("key", rule) for _ in range(60)]
    assert all(decision.allowed for decision in decisions)
    exhausted = await limiter.check("key", rule)
    assert exhausted.allowed is False
    assert exhausted.remaining == 0
    assert exhausted.reset_after_seconds >= 1

    await asyncio.sleep(0.05)
    assert (await limiter.check("key", rule)).allowed is True


async def test_limiter_is_per_identity(settings: APISettings) -> None:
    limiter = TokenBucketLimiter()
    rule = RateLimitRule("auth", limit=1, window_seconds=60.0, scope="ip")
    assert (await limiter.check("ip:1.2.3.4", rule)).allowed is True
    assert (await limiter.check("ip:1.2.3.4", rule)).allowed is False
    assert (await limiter.check("ip:5.6.7.8", rule)).allowed is True


async def test_rate_limit_can_be_disabled(settings_factory, envelope: EnvelopeCheck) -> None:
    settings: APISettings = settings_factory(rate_limit_auth_per_min=1, rate_limit_enabled=False)
    application = create_app(settings)
    async with (
        application.router.lifespan_context(application),
        AsyncClient(transport=ASGITransport(app=application), base_url="http://testserver") as http,
    ):
        for _ in range(3):
            assert (await http.post("/api/v1/auth/demo")).status_code == 200
