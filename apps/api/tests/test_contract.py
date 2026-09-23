"""The response envelope, the error-code table and request correlation.

``docs/API.md`` §1.1/§1.6 are the parts of the contract a client cannot work around:
an unenveloped body breaks the frontend's error handling, and an undocumented code
breaks its ``switch``. These tests assert both, including on the paths that a
framework normally answers without the application seeing them (unknown route,
method mismatch, validation, unexpected exception).
"""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from careerforge_api.core.config import APISettings
from careerforge_api.core.errors import ERROR_CODE_STATUS, ApiError, error_class
from careerforge_api.main import create_app
from careerforge_api.schemas.envelope import ApiEnvelope
from tests.conftest import EnvelopeCheck

#: The documented table of docs/API.md §1.6 — code → status.
DOCUMENTED_ERROR_CODES: dict[str, int] = {
    "VALIDATION_ERROR": 400,
    "UNSUPPORTED_FILE_TYPE": 400,
    "FILE_TOO_LARGE": 400,
    "UNAUTHORIZED": 401,
    "TOKEN_EXPIRED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "CLAIM_REJECTED": 422,
    "RATE_LIMITED": 429,
    "AI_BUDGET_EXCEEDED": 429,
    "AI_PROVIDER_ERROR": 502,
    "GITHUB_ERROR": 502,
    "DEPENDENCY_UNAVAILABLE": 503,
    "AI_PROVIDER_UNAVAILABLE": 503,
    "INTERNAL_ERROR": 500,
}


def test_get_owned_or_404_hides_existence() -> None:
    """The single place that decides "yours" vs "not found" (docs/API.md §1.2)."""
    from uuid import uuid4

    from careerforge_api.core.errors import NotFoundError
    from careerforge_api.deps import get_owned_or_404

    class Row:
        def __init__(self, user_id: object) -> None:
            self.user_id = user_id

    mine = Row(uuid4())
    assert get_owned_or_404(mine, user_id=mine.user_id) is mine

    # Somebody else's row and a missing row must be indistinguishable.
    with pytest.raises(NotFoundError):
        get_owned_or_404(mine, user_id=uuid4())
    with pytest.raises(NotFoundError):
        get_owned_or_404(None, user_id=uuid4())


def test_every_documented_error_code_exists_with_the_documented_status() -> None:
    for code, status in DOCUMENTED_ERROR_CODES.items():
        error = error_class(code)()
        assert error.code == code
        assert error.status_code == status
        assert error.message
        assert error.to_payload()["details"] == []
    assert set(DOCUMENTED_ERROR_CODES) <= set(ERROR_CODE_STATUS)


def test_error_payload_is_a_plain_json_object() -> None:
    payload = ApiError(
        "boom", code="AI_PROVIDER_ERROR", status_code=502, details=[{"field": "x", "issue": "y"}]
    ).to_payload()
    assert payload == {
        "code": "AI_PROVIDER_ERROR",
        "message": "boom",
        "details": [{"field": "x", "issue": "y"}],
    }
    json.dumps(payload)


async def test_unknown_route_is_enveloped_not_a_bare_fastapi_body(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.get("/api/v1/definitely-not-a-route")
    assert response.status_code == 404
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "NOT_FOUND"
    # A bare FastAPI body would be {"detail": "Not Found"} with only that key.
    assert set(response.json()) == {"success", "data", "error", "requestId"}


async def test_wrong_method_is_enveloped(client: AsyncClient, envelope: EnvelopeCheck) -> None:
    response = await client.get("/api/v1/auth/login")
    assert response.status_code == 405
    assert envelope(response, success=False)["error"]["code"] == "METHOD_NOT_ALLOWED"


async def test_validation_failure_carries_details(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 400
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["message"]
    details = payload["error"]["details"]
    assert isinstance(details, list) and details
    for detail in details:
        assert set(detail) >= {"field", "issue"}
        assert detail["field"] in {"email", "password"}


async def test_malformed_json_body_is_a_validation_error(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        content=b"{not json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    # `field` must name something a client can act on, not pydantic's character offset.
    assert payload["error"]["details"][0]["field"] == "body"
    assert payload["error"]["details"][0]["issue"] == "json_invalid"


async def test_request_id_is_echoed_when_the_client_supplies_one(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.get(
        "/api/v1/system/health", headers={"X-Request-Id": "client-supplied-id-42"}
    )
    assert response.headers["x-request-id"] == "client-supplied-id-42"
    assert envelope(response)["requestId"] == "client-supplied-id-42"


async def test_server_generates_a_request_id_when_missing(
    client: AsyncClient, envelope: EnvelopeCheck
) -> None:
    response = await client.get("/api/v1/system/health")
    request_id = response.headers["x-request-id"]
    assert request_id.startswith("req_")
    assert len(request_id) == len("req_") + 26  # ULID
    assert envelope(response)["requestId"] == request_id


@pytest.mark.parametrize("bad", ["has space", "bad!id", "x" * 200])
async def test_hostile_request_ids_are_replaced(
    client: AsyncClient, envelope: EnvelopeCheck, bad: str
) -> None:
    response = await client.get("/api/v1/system/health", headers={"X-Request-Id": bad})
    request_id = response.headers["x-request-id"]
    assert request_id != bad
    assert request_id.startswith("req_")


async def test_success_envelope_matches_the_schema(client: AsyncClient, demo) -> None:
    response = await client.get("/api/v1/auth/me", headers=demo.headers)
    parsed = ApiEnvelope[dict].model_validate(response.json())
    assert parsed.success is True
    assert parsed.error is None
    assert parsed.data is not None
    assert str(parsed.request_id) == response.headers["x-request-id"]


async def test_error_envelope_matches_the_schema(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    parsed = ApiEnvelope[dict].model_validate(response.json())
    assert parsed.success is False
    assert parsed.data is None
    assert parsed.error is not None and parsed.error.code == "UNAUTHORIZED"
    assert parsed.error.details == []


async def test_unexpected_exception_becomes_internal_error_without_leaking(
    settings: APISettings, envelope: EnvelopeCheck
) -> None:
    """A raising route must be logged with a traceback and answered with `INTERNAL_ERROR`."""
    application: FastAPI = create_app(settings)

    @application.get("/api/v1/_boom-test-only")
    async def boom() -> dict[str, str]:  # pragma: no cover - only runs inside the test
        raise RuntimeError("kaboom-secret-internal-detail")

    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            response = await http.get("/api/v1/_boom-test-only")

    assert response.status_code == 500
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert "kaboom" not in response.text
    assert payload["requestId"] == response.headers["x-request-id"]


async def test_api_error_raised_in_a_route_is_mapped(
    settings: APISettings, envelope: EnvelopeCheck
) -> None:
    from careerforge_api.core.errors import ClaimRejectedError

    application: FastAPI = create_app(settings)

    @application.get("/api/v1/_reject-test-only")
    async def reject() -> dict[str, str]:  # pragma: no cover - only runs inside the test
        raise ClaimRejectedError(
            "The claim has no supporting evidence",
            details=[{"field": "text", "issue": "numeric_without_evidence"}],
        )

    async with application.router.lifespan_context(application):
        transport = ASGITransport(app=application)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            response = await http.get("/api/v1/_reject-test-only")

    assert response.status_code == 422
    payload = envelope(response, success=False)
    assert payload["error"]["code"] == "CLAIM_REJECTED"
    assert payload["error"]["details"][0]["issue"] == "numeric_without_evidence"


async def test_non_json_responses_are_not_enveloped(client: AsyncClient) -> None:
    """The envelope applies to JSON only; the docs page and SSE must pass through."""
    response = await client.get("/docs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "success" not in response.text[:200]


async def test_internal_envelope_marker_never_reaches_a_client(client: AsyncClient, demo) -> None:
    """The handshake header between the error handlers and the envelope writer is private.

    Checked across the paths that produce a response at different middleware depths:
    a normal route, an authenticated route, the rate limiter's own 429 and a framework
    404. A leak here would be an implementation detail inside the frozen contract.
    """
    responses = [
        await client.get("/api/v1/system/health"),
        await client.get("/api/v1/auth/me"),
        await client.get("/api/v1/auth/me", headers=demo.headers),
        await client.get("/api/v1/nope"),
        await client.post("/api/v1/auth/login", json={"email": "x", "password": "y"}),
    ]
    for response in responses:
        assert "x-envelope-complete" not in response.headers, response.request.url
        assert response.headers["x-request-id"]


async def test_rate_limited_response_has_no_internal_marker(
    settings_factory,
) -> None:
    """The 429 is built by a middleware outside the envelope writer — still no marker."""
    from careerforge_api.main import create_app

    settings: APISettings = settings_factory(rate_limit_auth_per_min=1)
    application = create_app(settings)
    async with (
        application.router.lifespan_context(application),
        AsyncClient(transport=ASGITransport(app=application), base_url="http://testserver") as http,
    ):
        await http.post("/api/v1/auth/demo")
        limited = await http.post("/api/v1/auth/demo")

    assert limited.status_code == 429
    assert "x-envelope-complete" not in limited.headers
    assert limited.headers["retry-after"]
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


async def test_root_document_is_enveloped(client: AsyncClient, envelope: EnvelopeCheck) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    data = envelope(response)["data"]
    assert data["api"] == "/api/v1"
    assert data["health"] == "/api/v1/system/health"


async def test_openapi_document_is_served_unwrapped(client: AsyncClient) -> None:
    """The OpenAPI document must stay a plain OpenAPI 3.1 body: `pnpm gen:api` reads it."""
    response = await client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    document = response.json()
    assert document["openapi"].startswith("3.1")
    paths = document["paths"]
    for path in (
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/demo",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/system/health",
        "/api/v1/system/info",
        "/api/v1/tasks/{task_id}",
        "/api/v1/tasks/{task_id}/cancel",
    ):
        assert path in paths, path


def test_logging_formatter_emits_the_documented_request_fields_and_redacts() -> None:
    """request_id/method/path/status/duration_ms, with PII masked (ARCHITECTURE §9)."""
    from careerforge_api.core.logging import JsonFormatter

    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="careerforge_api",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="login for alex@careerforge.ai with Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abc",
        args=(),
        exc_info=None,
    )
    record.request_id = "req_01HQ"
    record.method = "POST"
    record.path = "/api/v1/auth/login"
    record.status = 401
    record.duration_ms = 12.5
    record.model = "should-be-dropped"  # not allow-listed

    payload = json.loads(formatter.format(record))
    assert payload["request_id"] == "req_01HQ"
    assert payload["method"] == "POST"
    assert payload["path"] == "/api/v1/auth/login"
    assert payload["status"] == 401
    assert payload["duration_ms"] == 12.5
    assert "model" not in payload
    assert "alex@careerforge.ai" not in payload["message"]
    assert "eyJhbGciOiJIUzI1NiJ9" not in payload["message"]
