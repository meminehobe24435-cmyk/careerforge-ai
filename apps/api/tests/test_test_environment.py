"""The test environment itself, asserted.

Two PHASE 13 findings were about the suite rather than the product, and both cost real time:

* the API suite **inherited the developer's `.env`**. On a machine configured for the Docker path
  (``USE_SQLITE=false``), the unit suite tried to reach a PostgreSQL and a Redis that were not
  running — 272 connection errors and a 24-minute run, from a suite documented as needing no
  external service;
* the ``upload`` bucket is **20 per hour**, so a scenario that ingests several documents passed
  alone and failed in a full run, which reads as a product bug.

These tests pin the fix. They are deliberately about the *environment*: a test that fails here is
telling you the suite is not reproducible, not that the product is broken.
"""

from __future__ import annotations

from fastapi import FastAPI
from httpx import AsyncClient

from careerforge_api.core.config import APISettings
from careerforge_api.db.session import is_sqlite_url


def test_the_suite_runs_on_a_throwaway_sqlite_file(settings: APISettings) -> None:
    """No external database, whatever the machine is configured for."""
    assert settings.use_sqlite is True, (
        "the unit suite must not depend on a running PostgreSQL: it silently inherited a local "
        ".env with USE_SQLITE=false and produced 272 connection errors"
    )
    assert is_sqlite_url(settings.resolved_database_url)
    assert "careerforge-test.db" in settings.resolved_database_url


def test_the_suite_never_needs_redis(settings: APISettings) -> None:
    """The queue is in-process, so a unit test cannot reach for a Redis that is not there."""
    assert settings.queue_backend == "inprocess", (
        "the queue fell back to Redis: unit tests must not connect to an external service they "
        "were never told about"
    )


def test_the_quiet_limits_include_the_hourly_upload_bucket(settings: APISettings) -> None:
    """The per-minute buckets alone were not enough: `upload` is 20/hour in production."""
    assert settings.rate_limit_upload_per_hour >= 1_000
    assert settings.rate_limit_ai_per_min >= 1_000


async def test_the_limiter_is_per_application_so_runs_do_not_pollute_each_other(
    client: AsyncClient, app: FastAPI
) -> None:
    """A second identical request in the same app is not rejected.

    The limiter's buckets live on the application instance, and the suite builds one application per
    test — which is why the browser suite (one long-lived server, one shared identity) hit the
    hourly upload wall while this suite did not. This asserts the property that makes the API suite
    re-runnable twice in a row.
    """
    first = await client.post("/api/v1/auth/demo")
    second = await client.post("/api/v1/auth/demo")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, (
        "the second identical request was limited; either the buckets are not per-application or the "
        "test limits are not quiet"
    )
    assert app.state.rate_limiter is not None
