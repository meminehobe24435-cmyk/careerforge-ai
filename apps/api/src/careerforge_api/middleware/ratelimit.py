"""Rate limiting: token buckets per identity and endpoint group.

``docs/API.md`` §1.7 freezes both the groups and their budgets::

    auth (login/register/demo)   10 / minute / IP
    read                        300 / minute / user
    write                        60 / minute / user
    AI                           20 / minute / user
    upload                       20 / hour   / user

The identity is the authenticated user when a valid bearer token is present and the
client IP otherwise — the limiter runs before the auth dependency, so it decodes
the JWT signature itself and never touches the database.

``docs/ARCHITECTURE.md`` §1.3 assigns Redis to this job in the Docker topology;
with no Redis available the in-process implementation below is **semantically
equivalent for a single process**, and that limitation is stated on
``GET /system/health`` (``checks.queue``) rather than hidden. A shared limiter
arrives with the Redis queue in PHASE 15.

This middleware builds its own response for ``429`` (it sits outside both the
error handlers and the envelope writer) using the same helpers, so a throttled
request still leaves the API as a documented envelope with ``Retry-After``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
import time

import jwt
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from careerforge_api.core.config import APISettings
from careerforge_api.core.errors import RateLimitedError
from careerforge_api.core.ids import new_request_id
from careerforge_api.middleware.envelope import error_envelope
from careerforge_api.middleware.request_id import request_id_of

__all__ = [
    "AUTH_PATHS",
    "RATE_LIMIT_GROUPS",
    "RateLimitMiddleware",
    "RateLimitRule",
    "TokenBucketLimiter",
    "classify_request",
]

#: Endpoint groups from ``docs/API.md`` §1.7.
RATE_LIMIT_GROUPS = ("auth", "read", "write", "ai", "upload")

#: Paths that use the (stricter, IP-keyed) authentication budget.
AUTH_PATHS = ("/auth/login", "/auth/register", "/auth/demo", "/auth/refresh", "/auth/logout")

#: Substrings that mark an AI endpoint (they get their own tighter quota).
_AI_MARKERS = ("/analyze", "/match", "/optimize", "/interview", "/deep-dive")

#: Substrings that mark an upload endpoint.
_UPLOAD_MARKERS = ("/import", "/upload", "/documents")

_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Header names from ``docs/API.md`` §1.7.
HEADER_LIMIT = "X-RateLimit-Limit"
HEADER_REMAINING = "X-RateLimit-Remaining"
HEADER_RESET = "X-RateLimit-Reset"


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    """One documented quota."""

    group: str
    limit: int
    window_seconds: float
    #: ``"user"`` → bucket per authenticated user, ``"ip"`` → bucket per client IP.
    scope: str

    @property
    def key_prefix(self) -> str:
        return f"{self.group}:{self.scope}"


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated_at: float


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Outcome of a bucket check."""

    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int

    @property
    def headers(self) -> dict[str, str]:
        return {
            HEADER_LIMIT: str(self.limit),
            HEADER_REMAINING: str(max(0, self.remaining)),
            HEADER_RESET: str(self.reset_after_seconds),
        }


class TokenBucketLimiter:
    """In-process token bucket store (one bucket per ``rule + identity``)."""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, rule: RateLimitRule, *, cost: float = 1.0) -> RateLimitDecision:
        now = time.monotonic()
        rate = rule.limit / rule.window_seconds
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=float(rule.limit), updated_at=now)
                self._buckets[key] = bucket
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(float(rule.limit), bucket.tokens + elapsed * rate)
            bucket.updated_at = now

            if bucket.tokens >= cost:
                bucket.tokens -= cost
                allowed = True
            else:
                allowed = False

            deficit = max(0.0, cost - bucket.tokens)
            reset_after = math.ceil(deficit / rate) if deficit else 0
            remaining = int(bucket.tokens)

        return RateLimitDecision(
            allowed=allowed,
            limit=rule.limit,
            remaining=remaining,
            reset_after_seconds=reset_after,
        )

    async def reset(self) -> None:
        async with self._lock:
            self._buckets.clear()

    def bucket_count(self) -> int:
        return len(self._buckets)


def classify_request(method: str, path: str, settings: APISettings) -> RateLimitRule:
    """Pick the documented rule that governs this request."""
    suffix = path
    prefix = settings.api_prefix
    if prefix and suffix.startswith(prefix):
        suffix = suffix[len(prefix) :] or "/"
    normalized = suffix if suffix.startswith("/") else f"/{suffix}"
    upper = method.upper()

    if upper in _WRITE_METHODS and any(
        normalized.startswith(candidate) for candidate in AUTH_PATHS
    ):
        return RateLimitRule("auth", settings.rate_limit_auth_per_min, 60.0, "ip")
    if any(marker in normalized for marker in _UPLOAD_MARKERS) and upper in _WRITE_METHODS:
        # Configurable since PHASE 14. Hard-coded at 20 here, it could not be raised for a test suite
        # or a self-hosted deployment that ingests more than twenty documents an hour — and a test
        # that passes alone then fails inside a full run reads as a product bug.
        return RateLimitRule("upload", settings.rate_limit_upload_per_hour, 3600.0, "user")
    if any(marker in normalized for marker in _AI_MARKERS):
        return RateLimitRule("ai", settings.rate_limit_ai_per_min, 60.0, "user")
    if upper in _READ_METHODS:
        return RateLimitRule("read", settings.rate_limit_read_per_min, 60.0, "user")
    return RateLimitRule("write", settings.rate_limit_write_per_min, 60.0, "user")


def _client_ip(scope: Scope) -> str:
    client = scope.get("client")
    if client:
        return str(client[0])
    return "unknown"


def _bearer_subject(scope: Scope, settings: APISettings) -> str | None:
    for key, value in scope.get("headers") or []:
        if key.lower() != b"authorization":
            continue
        try:
            raw = value.decode("latin-1")
        except UnicodeDecodeError:  # pragma: no cover - latin-1 never fails
            return None
        if not raw.lower().startswith("bearer "):
            return None
        token = raw[7:].strip()
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
                options={"verify_aud": False},
            )
        except jwt.PyJWTError:
            # An invalid token is not an identity, but it must not escape the
            # limiter either: fall back to the IP bucket.
            return None
        subject = payload.get("sub")
        return str(subject) if subject else None
    return None


class RateLimitMiddleware:
    """Applies the §1.7 budgets and publishes the ``X-RateLimit-*`` headers."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: APISettings,
        limiter: TokenBucketLimiter | None = None,
    ) -> None:
        self.app = app
        self.settings = settings
        self.limiter = limiter or TokenBucketLimiter()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.settings.rate_limit_enabled:
            await self.app(scope, receive, send)
            return

        request_id = request_id_of(scope) or new_request_id()
        method = str(scope.get("method", "GET"))
        path = str(scope.get("path", ""))
        rule = classify_request(method, path, self.settings)

        if rule.scope == "ip":
            identity = _client_ip(scope)
        else:
            # Authenticated traffic is bucketed per user; anonymous traffic per IP.
            identity = _bearer_subject(scope, self.settings) or _client_ip(scope)
        decision = await self.limiter.check(f"{rule.key_prefix}:{identity}", rule)

        if not decision.allowed:
            error = RateLimitedError(
                f"Rate limit exceeded for {rule.group} requests; retry in "
                f"{decision.reset_after_seconds}s",
                retry_after_seconds=decision.reset_after_seconds,
                details=[{"field": "rateLimit", "issue": rule.group}],
                headers=decision.headers,
            )
            response = JSONResponse(
                status_code=error.status_code,
                content=error_envelope(error, request_id=request_id),
                # No envelope marker needed: this middleware sits *outside* the envelope
                # writer, so this body already is the finished, documented envelope.
                headers={**error.headers, "X-Request-Id": request_id},
            )
            await response(scope, receive, send)
            return

        async def add_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                lowered = {key.lower() for key, _ in headers}
                for name, value in decision.headers.items():
                    encoded = name.lower().encode("latin-1")
                    if encoded not in lowered:
                        headers.append((encoded, value.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, add_headers)
