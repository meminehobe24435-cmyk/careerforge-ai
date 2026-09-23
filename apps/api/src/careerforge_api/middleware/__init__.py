"""Middleware chain for the HTTP API.

``docs/ARCHITECTURE.md`` §8.2 freezes the order::

    RequestID → 结构化日志 → CORS → 速率限制 → 认证(JWT) → 路由 → 全局异常处理 → 信封包装

Installed by :func:`careerforge_api.main.create_app`, which adds middleware
innermost-first because in Starlette the **last** middleware added is the outermost.
Executed order on the way in is therefore:

    RequestID → RequestLogging → [TrustedHost] → CORS → RateLimit → ErrorHandling →
    Envelope → (FastAPI exception handlers) → router

and the reverse on the way out. Two placements are deliberate and differ from a naive
reading of the documented list:

* **ErrorHandling sits inside RateLimit** (the document puts it after the router).
  A Starlette exception raised by one middleware never travels back through a
  middleware *outside* it, so an error handler placed below the limiter could not
  transform the limiter's own ``429`` into an envelope. The limiter raises
  :class:`~careerforge_api.core.errors.RateLimitedError` and this layer writes the
  documented body.
* **Envelope is the innermost user middleware** (immediately outside the router), so it
  sees every JSON response including the ones a FastAPI exception handler produced. It
  is skipped for the OpenAPI document and the docs pages, which tooling consumes raw.

Two more deliberate choices:

* **Authentication is not middleware.** Only some routes need an identity, and a
  middleware would have to guess which; it is a dependency
  (:func:`careerforge_api.deps.get_current_user`) resolved per route, where
  "missing/invalid token → 401, someone else's resource → 404" belongs.
* **``X-Envelope-Complete``** is the internal handshake between the error/limit layers
  and the envelope writer. It is stripped by the outermost middleware, so it can never
  appear in a response a client sees.
"""

from __future__ import annotations

from careerforge_api.middleware.envelope import ENVELOPE_COMPLETE_HEADER, EnvelopeMiddleware
from careerforge_api.middleware.errors import ErrorHandlingMiddleware
from careerforge_api.middleware.headers import REQUEST_ID_HEADER, strip_internal_headers
from careerforge_api.middleware.logging import RequestLoggingMiddleware
from careerforge_api.middleware.ratelimit import RateLimitMiddleware, TokenBucketLimiter
from careerforge_api.middleware.request_id import RequestIDMiddleware

__all__ = [
    "ENVELOPE_COMPLETE_HEADER",
    "REQUEST_ID_HEADER",
    "EnvelopeMiddleware",
    "ErrorHandlingMiddleware",
    "RateLimitMiddleware",
    "RequestIDMiddleware",
    "RequestLoggingMiddleware",
    "TokenBucketLimiter",
    "strip_internal_headers",
]
