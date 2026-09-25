"""Flush the failure journal once the request's transaction has settled.

This is the second half of the fix for "a failed request leaves no run row". The tracker
(:mod:`careerforge_api.services.ai_service`) hands a failed run to the journal instead of writing
it inside the request's transaction, and this middleware is what writes it — *after* the response or
the exception has passed all the way out through ``get_db``, i.e. after the transaction is committed
or rolled back. Opening the write session any earlier would contend with the request's own
transaction for SQLite's single writer slot, which is the "database is locked" failure PHASE 2
already paid for.

It is deliberately the **outermost** middleware. Anything inside it — the error handler that turns an
exception into an envelope, the access logger — runs first, so by the time this ``finally`` block
executes the request is completely finished.

The middleware never raises and never changes a response: a journal that cannot write logs a warning
and gets out of the way. Observability failing must not fail the request it was observing.
"""

from __future__ import annotations

from typing import Any

from starlette.types import ASGIApp, Receive, Scope, Send

from careerforge_api.core.logging import get_logger

__all__ = ["FailureJournalMiddleware"]

logger = get_logger("careerforge_api.failures")


def _journal_of(scope: Scope) -> Any | None:
    app = scope.get("app")
    return getattr(getattr(app, "state", None), "failure_journal", None)


class FailureJournalMiddleware:
    """Persist any journaled failed run after the request is over."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        try:
            await self.app(scope, receive, send)
        finally:
            journal = _journal_of(scope)
            if journal is not None:
                try:
                    await journal.flush()
                except Exception as exc:  # pragma: no cover - defensive, journal logs its own
                    logger.warning(
                        "failure_journal_flush_failed",
                        extra={
                            "event": "failure_journal_flush_failed",
                            "detail": f"{type(exc).__name__}: {exc}",
                        },
                    )
