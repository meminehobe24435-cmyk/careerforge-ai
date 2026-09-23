"""``/documents`` — upload, list, read and delete candidate material (``docs/API.md`` §2.3).

The documented contract is a ``202`` with a task id, because parsing a 20 MB PDF does not
belong in a request handler. The flow is:

1. ``POST /documents`` validates the type and size, spools the bytes, writes a ``pending``
   row, and enqueues ``document.ingest``;
2. the worker parses, chunks and stores, reporting progress to ``background_jobs``;
3. the client follows ``GET /tasks/{id}`` (or reads ``GET /documents/{id}``) until the
   status leaves ``pending``.

Uploading the same bytes twice is idempotent: the second call returns the existing
document with ``deduplicated: true`` and no second parse, so re-uploading a résumé cannot
fork the evidence graph.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, Request, UploadFile, status
from sqlalchemy import func, select

from careerforge_ai.errors import (
    DocumentParseError,
    DocumentTooLargeError,
    UnsupportedDocumentError,
)
from careerforge_api.core.config import get_api_settings
from careerforge_api.core.errors import (
    FileTooLargeError,
    NotFoundError,
    UnsupportedFileTypeError,
    ValidationError,
)
from careerforge_api.core.ids import task_public_id
from careerforge_api.deps import CurrentUser, DbSession
from careerforge_api.models.document import DOCUMENT_KINDS, Document, DocumentChunk
from careerforge_api.schemas.document import (
    ChunkResponse,
    DocumentDetail,
    DocumentListResponse,
    DocumentResponse,
    DocumentTextResponse,
    DocumentUploadAccepted,
)
from careerforge_api.services.document_service import DocumentService

__all__ = ["router"]

router = APIRouter(prefix="/documents", tags=["documents"])

#: Chunks returned by one call. A résumé produces a handful; a long project doc a few
#: dozen. The cap keeps a pathological document from turning the explanation endpoint
#: into a dump.
MAX_CHUNKS_RETURNED = 200


def _parse_uuid(raw: str) -> UUID:
    """A malformed id is a ``404``, not a ``400``: it is simply an id that does not exist."""
    try:
        return UUID(raw)
    except ValueError as exc:
        raise NotFoundError("Document not found") from exc


def _map_parse_error(exc: DocumentParseError) -> Exception:
    """Translate a core ingestion error into the API's own error taxonomy."""
    if isinstance(exc, UnsupportedDocumentError):
        return UnsupportedFileTypeError(str(exc))
    if isinstance(exc, DocumentTooLargeError):
        return FileTooLargeError(str(exc))
    return ValidationError(str(exc))


async def _load_own(document_id: str, *, session: DbSession, user: CurrentUser) -> Document:
    document = await DocumentService(session).get(_parse_uuid(document_id), user=user)
    if document is None:
        raise NotFoundError("Document not found")
    return document


async def _chunk_count(session: DbSession, document: Document) -> int:
    statement = (
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
    )
    return int(await session.scalar(statement) or 0)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a document for parsing",
)
async def upload_document(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    file: Annotated[UploadFile, File(description="PDF, DOCX, Markdown or plain text")],
    kind: Annotated[str, Form(description="resume | project_doc | interview_note | jd | notes")] = (
        "resume"
    ),
) -> DocumentUploadAccepted:
    if kind not in DOCUMENT_KINDS:
        raise ValidationError(
            f"unknown document kind '{kind}'",
            details=[
                {
                    "field": "kind",
                    "issue": "not_allowed",
                    "message": f"allowed: {', '.join(DOCUMENT_KINDS)}",
                }
            ],
        )

    settings = get_api_settings()
    # Read one byte past the limit so an oversized upload is detected without buffering
    # the whole thing: the point of a limit is not to allocate the thing it refuses.
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise FileTooLargeError(
            f"{file.filename or 'the uploaded file'} is larger than "
            f"{settings.max_upload_bytes // 1_048_576} MiB"
        )

    service = DocumentService(session)
    try:
        staged = await service.stage_upload(
            user=user,
            filename=file.filename,
            data=data,
            kind=kind,
            mime=file.content_type,
        )
    except DocumentParseError as exc:
        raise _map_parse_error(exc) from exc

    if staged.deduplicated:
        # Nothing to parse: these bytes are already stored under this hash. The response
        # says so and carries the document instead of a task id — a fresh task id would
        # promise work that is not going to happen.
        return DocumentUploadAccepted(
            task_id=None,
            document_id=str(staged.document.id),
            status=staged.document.parse_status,
            deduplicated=True,
        )

    queue = getattr(request.app.state, "queue", None)
    if queue is None:  # pragma: no cover - only when create_app was bypassed
        raise ValidationError("the task queue is not available in this process")

    # Committed before enqueueing, for two reasons. The worker reads the document from its
    # own session — possibly in another process — so a row still open inside this request's
    # transaction would be invisible to it and the job would fail with "does not exist".
    # And on SQLite, enqueueing opens a second connection to the same file: while this
    # transaction holds the write lock, that insert fails with "database is locked".
    await session.commit()

    job = await queue.enqueue(
        kind="document.ingest",
        payload={"documentId": str(staged.document.id)},
        user_id=user.id,
    )
    return DocumentUploadAccepted(
        task_id=task_public_id(job.id),
        document_id=str(staged.document.id),
        status=job.status,
    )


@router.get("", summary="List documents")
async def list_documents(
    session: DbSession,
    user: CurrentUser,
    kind: Annotated[str | None, Query(description="Filter by document kind")] = None,
    parse_status: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    service = DocumentService(session)
    documents, total = await service.list(
        user=user, kind=kind, parse_status=parse_status, limit=limit, offset=offset
    )
    return DocumentListResponse(
        items=[DocumentResponse.from_document(document) for document in documents],
        total=total,
        by_kind=await service.counts_by_kind(user=user),
    )


@router.get("/{document_id}", summary="Document detail")
async def get_document(
    document_id: str,
    session: DbSession,
    user: CurrentUser,
) -> DocumentDetail:
    document = await _load_own(document_id, session=session, user=user)
    return DocumentDetail.from_document(document, chunk_count=await _chunk_count(session, document))


@router.get("/{document_id}/chunks", summary="Stored chunks (debugging and explanation)")
async def list_chunks(
    document_id: str,
    session: DbSession,
    user: CurrentUser,
) -> list[ChunkResponse]:
    document = await _load_own(document_id, session=session, user=user)
    statement = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .limit(MAX_CHUNKS_RETURNED)
    )
    rows = (await session.scalars(statement)).all()
    return [
        ChunkResponse(
            index=row.chunk_index,
            content=row.content,
            token_count=row.token_count,
            heading_path=row.heading_path,
            page_no=row.page_no,
            char_start=row.char_start,
            char_end=row.char_end,
        )
        for row in rows
    ]


@router.get("/{document_id}/text", summary="The stored text, or why it is absent")
async def get_document_text(
    document_id: str,
    session: DbSession,
    user: CurrentUser,
) -> DocumentTextResponse:
    """Separate from the detail response because the text can be large and is exactly
    what Local Mode does not keep."""
    document = await _load_own(document_id, session=session, user=user)
    if document.raw_text:
        return DocumentTextResponse(
            document_id=str(document.id), text=document.raw_text, char_count=len(document.raw_text)
        )

    reason = "local_mode" if user.prefers_local_storage else "retention_disabled"
    if document.parse_status == "failed":
        reason = "parse_failed"
    elif document.parse_status == "pending":
        reason = "not_parsed_yet"
    return DocumentTextResponse(document_id=str(document.id), unavailable_reason=reason)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete")
async def delete_document(document_id: str, session: DbSession, user: CurrentUser) -> None:
    """Hard delete; chunks and any future evidence rows go with it via the FK cascade."""
    document = await _load_own(document_id, session=session, user=user)
    await DocumentService(session).delete(document)
