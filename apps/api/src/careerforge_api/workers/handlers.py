"""Job handlers for the queue port.

Handlers live here rather than inside the queue because the queue is infrastructure
(``docs/ARCHITECTURE.md`` §7): it knows about ``background_jobs`` rows, retries and
progress reporting, and nothing about documents or résumés. This module is the seam —
each domain handler is registered against the queue by kind, so the API process and the
standalone worker run the *same* implementation.

The session factory is captured at registration time. ``HandlerContext`` deliberately
carries no session: a handler that held a request-scoped session would keep a transaction
open for the whole job, and a long parse would pin a connection.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from careerforge_ai.errors import DocumentParseError
from careerforge_api.core.logging import get_logger
from careerforge_api.models.document import Document
from careerforge_api.models.user import User
from careerforge_api.services.document_service import DocumentService
from careerforge_api.workers.queue import HandlerContext, JobHandler, QueuePort

__all__ = ["DOCUMENT_INGEST_KIND", "build_document_ingest_handler", "register_default_handlers"]

_logger = get_logger("careerforge_api.workers.handlers")

#: Job kind for "parse this staged upload". Dotted, matching ``system.ping``.
DOCUMENT_INGEST_KIND = "document.ingest"

SessionFactory = async_sessionmaker[AsyncSession]


def register_default_handlers(queue: QueuePort, session_factory: SessionFactory) -> None:
    """Attach every domain handler known to this build.

    Called by both entrypoints (the API lifespan and the standalone worker) so a job kind
    cannot work in one process and be "no handler registered" in the other.
    """
    queue.register_handler(DOCUMENT_INGEST_KIND, build_document_ingest_handler(session_factory))
    _logger.info(
        "job_handlers_registered",
        extra={"event": "job_handlers_registered", "kinds": queue.registered_kinds()},
    )


def build_document_ingest_handler(session_factory: SessionFactory) -> JobHandler:
    """Parse the staged upload named by ``payload['documentId']``."""

    async def handle(context: HandlerContext) -> Mapping[str, Any] | None:
        raw_id = context.payload.get("documentId")
        if not raw_id or context.user_id is None:
            raise ValueError("document.ingest requires payload.documentId and a user_id")

        async with session_factory() as session:
            document = await session.get(Document, _as_uuid(raw_id))
            if document is None or document.user_id != context.user_id:
                raise ValueError(f"document {raw_id} does not exist for this user")
            user = await session.get(User, document.user_id)
            if user is None:  # pragma: no cover - the FK cascades, so this cannot happen
                raise ValueError("the document's owner no longer exists")

            # Reported before this handler writes anything, and deliberately not again
            # afterwards: ``report`` persists through its own connection, so a report
            # issued while this transaction holds the write lock fails on SQLite with
            # "database is locked" — and on PostgreSQL it would be invisible until the
            # commit anyway. The queue records the job's own 100/succeeded on return.
            await context.report("parsing", 20)
            try:
                result = await DocumentService(session).ingest_staged(document, user=user)
            except DocumentParseError as exc:
                # The row already records why; the job fails so ``/tasks/{id}`` shows it
                # too, and the error text is the same one the candidate will read.
                raise ValueError(str(exc)) from exc

            await session.commit()
            return {
                "documentId": str(document.id),
                "filename": document.filename,
                "parseStatus": document.parse_status,
                "chunkCount": result.chunk_count,
                "textRetained": result.text_retained,
                "warnings": result.warnings,
                "pageCount": document.page_count,
            }

    return handle


def _as_uuid(value: object) -> UUID:
    """The payload column is JSON, so an id arrives as a string.

    A malformed one raises ``ValueError``, which the queue records as the job's error
    rather than letting it escape as an unhandled crash.
    """
    return value if isinstance(value, UUID) else UUID(str(value))
