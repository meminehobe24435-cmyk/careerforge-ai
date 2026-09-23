"""Middleware chain for the HTTP API.

Installed by :func:`careerforge_api.main.create_app` in the order frozen by
``docs/ARCHITECTURE.md`` §8.2::

    RequestID → 结构化日志 → CORS → 速率限制 → 认证(JWT) → 路由 → 全局异常处理 → 信封包装

In Starlette the *last* middleware added is the *outermost*, so ``create_app`` adds
them innermost-first and the reading order above maps to the execution order on the
way in and the reverse on the way out. Two placements are deliberate and are
called out in the API README:

* ``ErrorHandlingMiddleware`` sits inside the rate limiter, so the limiter's own
  429 is built there and still leaves as a documented envelope.
* the envelope writer is the innermost user middleware, immediately outside the
  router, so it sees every JSON response — including one produced by a FastAPI
  exception handler.

Authentication is not a middleware: only some routes need an identity, and a
middleware would have to guess. It is a dependency
(:func:`careerforge_api.deps.get_current_user`) resolved per route, which is where
"missing/invalid token → 401, other people's resources → 404" belongs.
"""

from __future__ import annotations

from careerforge_api.middleware.envelope import ENVELOPE_COMPLETE_HEADER, EnvelopeMiddleware
from careerforge_api.middleware.errors import ErrorHandlingMiddleware
from careerforge_api.middleware.logging import RequestLoggingMiddleware
from careerforge_api.middleware.ratelimit import RateLimitMiddleware, TokenBucketLimiter
from careerforge_api.middleware.request_id import REQUEST_ID_HEADER, RequestIDMiddleware

__all__ = [
    "ENVELOPE_COMPLETE_HEADER",
    "REQUEST_ID_HEADER",
    "EnvelopeMiddleware",
    "ErrorHandlingMiddleware",
    "RateLimitMiddleware",
    "RequestIDMiddleware",
    "RequestLoggingMiddleware",
    "TokenBucketLimiter",
]
