"""Document models: ``/documents`` (``docs/API.md`` §2.3).

The response shape follows one rule from the documented contract: **``rawText`` is null
in Local Mode**. It is therefore never the primary payload — the list and detail
responses carry a short ``textPreview`` plus the metadata a UI needs, and the full stored
text has its own endpoint. Returning a 20 MB résumé inside a list response would make the
list unusable, and it would put the candidate's text on the wire for pages that only
needed a filename.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ChunkResponse",
    "DocumentDetail",
    "DocumentListResponse",
    "DocumentResponse",
    "DocumentTextResponse",
    "DocumentUploadAccepted",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class DocumentResponse(_CamelModel):
    """One document's metadata, warnings included."""

    id: str
    kind: str
    filename: str
    mime: str | None = None
    size_bytes: int = Field(default=0, alias="sizeBytes")
    sha256: str = ""
    page_count: int | None = Field(default=None, alias="pageCount")
    parse_status: str = Field(alias="parseStatus")
    parse_error: str | None = Field(default=None, alias="parseError")
    is_redacted: bool = Field(default=False, alias="isRedacted")
    #: Ingestion warnings — a scanned PDF, a non-UTF-8 decode. Shown, never swallowed.
    warnings: list[str] = Field(default_factory=list)
    #: Whether the server holds this document's text at all.
    text_retained: bool = Field(default=False, alias="textRetained")
    char_count: int = Field(default=0, alias="charCount")
    chunk_count: int = Field(default=0, alias="chunkCount")
    #: First few hundred characters, for a UI that wants to show what was read.
    text_preview: str | None = Field(default=None, alias="textPreview")
    pii_finding_count: int = Field(default=0, alias="piiFindingCount")
    pii_kinds: list[str] = Field(default_factory=list, alias="piiKinds")

    @classmethod
    def from_document(
        cls,
        document: Any,
        *,
        chunk_count: int = 0,
        preview_chars: int = 400,
    ) -> DocumentResponse:
        """Project the ORM row. ``metadata`` is the JSON catch-all from §2.3."""
        metadata = document.metadata_ or {}
        text = document.raw_text or ""
        return cls(
            id=str(document.id),
            kind=document.kind,
            filename=document.filename,
            mime=document.mime,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            page_count=document.page_count,
            parse_status=document.parse_status,
            parse_error=document.parse_error,
            is_redacted=document.is_redacted,
            warnings=document.warnings,
            text_retained=bool(metadata.get("textRetained")),
            char_count=int(metadata.get("charCount") or len(text)),
            chunk_count=chunk_count,
            text_preview=text[:preview_chars] if text else None,
            pii_finding_count=int(metadata.get("piiFindingCount") or 0),
            pii_kinds=[str(kind) for kind in metadata.get("piiKinds") or []],
        )


class DocumentDetail(DocumentResponse):
    """``GET /documents/{id}`` — the same row plus the detected format."""

    format: str | None = None
    encoding: str | None = None
    created_at: datetime | None = Field(default=None, alias="createdAt")

    @classmethod
    def from_document(
        cls,
        document: Any,
        *,
        chunk_count: int = 0,
        preview_chars: int = 400,
    ) -> DocumentDetail:
        base = DocumentResponse.from_document(
            document, chunk_count=chunk_count, preview_chars=preview_chars
        )
        metadata = document.metadata_ or {}
        # Field names here, not aliases: the model is built with ``populate_by_name``.
        return cls(
            **base.model_dump(),
            format=metadata.get("format"),
            encoding=metadata.get("encoding"),
            created_at=document.created_at,
        )


class DocumentListResponse(_CamelModel):
    """``GET /documents`` — items plus the counts the filter chips need."""

    items: list[DocumentResponse] = Field(default_factory=list)
    total: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict, alias="byKind")


class ChunkResponse(_CamelModel):
    """One heading-scoped fragment, as stored for retrieval."""

    index: int
    content: str
    token_count: int = Field(default=0, alias="tokenCount")
    heading_path: str = Field(default="", alias="headingPath")
    page_no: int | None = Field(default=None, alias="pageNo")
    char_start: int = Field(default=0, alias="charStart")
    char_end: int = Field(default=0, alias="charEnd")


class DocumentTextResponse(_CamelModel):
    """``GET /documents/{id}/text`` — the stored text, or the reason it is absent."""

    document_id: str = Field(alias="documentId")
    text: str | None = None
    char_count: int = Field(default=0, alias="charCount")
    #: ``local_mode`` / ``retention_disabled`` when ``text`` is null, so the UI can
    #: explain the absence instead of showing an empty box.
    unavailable_reason: str | None = Field(default=None, alias="unavailableReason")


class DocumentUploadAccepted(_CamelModel):
    """``202`` body for an accepted upload (``docs/API.md`` §1.4 shape).

    ``task_id`` is nullable because a de-duplicated upload has nothing to wait for: the
    client should read the document instead of polling a job that does not exist.
    """

    task_id: str | None = Field(default=None, alias="taskId")
    status: str = "queued"
    stream_url: str | None = Field(default=None, alias="streamUrl")
    document_id: str = Field(alias="documentId")
    #: True when these exact bytes were already stored, in which case the task id refers
    #: to the earlier job and nothing is re-parsed.
    deduplicated: bool = False
