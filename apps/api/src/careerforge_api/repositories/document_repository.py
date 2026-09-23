"""Document data access.

Same tenant rule as every other repository: **every query filters by ``user_id``**, and a
cross-tenant lookup returns ``None`` so the router can answer ``404`` without confirming
that someone else's document exists (``docs/API.md`` §1.2).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_api.models.document import Document, DocumentChunk

__all__ = ["DocumentRepository"]


class DocumentRepository:
    """Tenant-scoped reads and writes for ``documents`` / ``document_chunks``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── documents ────────────────────────────────────────────────────────────

    async def get(self, document_id: UUID, *, user_id: UUID) -> Document | None:
        statement = select(Document).where(Document.id == document_id, Document.user_id == user_id)
        return await self._session.scalar(statement)

    async def get_by_sha256(self, sha256: str, *, user_id: UUID) -> Document | None:
        """The de-duplication probe: identical bytes must not fork the graph."""
        statement = select(Document).where(Document.user_id == user_id, Document.sha256 == sha256)
        return await self._session.scalar(statement)

    async def list(
        self,
        *,
        user_id: UUID,
        kind: str | None = None,
        parse_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Document]:
        """Filtered list. Every filter is applied in SQL: filtering after a ``LIMIT``
        would silently return short pages and a wrong total."""
        statement = select(Document).where(Document.user_id == user_id)
        if kind is not None:
            statement = statement.where(Document.kind == kind)
        if parse_status is not None:
            statement = statement.where(Document.parse_status == parse_status)
        statement = statement.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        return (await self._session.scalars(statement)).all()

    async def count(
        self,
        *,
        user_id: UUID,
        kind: str | None = None,
        parse_status: str | None = None,
    ) -> int:
        statement = select(func.count()).select_from(Document).where(Document.user_id == user_id)
        if kind is not None:
            statement = statement.where(Document.kind == kind)
        if parse_status is not None:
            statement = statement.where(Document.parse_status == parse_status)
        return int(await self._session.scalar(statement) or 0)

    async def counts_by_kind(self, *, user_id: UUID) -> dict[str, int]:
        """One grouped query rather than one per kind: the filter chips need all of them."""
        statement = (
            select(Document.kind, func.count())
            .where(Document.user_id == user_id)
            .group_by(Document.kind)
        )
        return {str(kind): int(count) for kind, count in (await self._session.execute(statement))}

    async def create(
        self,
        *,
        user_id: UUID,
        kind: str,
        filename: str,
        sha256: str,
        size_bytes: int,
        mime: str | None = None,
        storage_path: str | None = None,
        raw_text: str | None = None,
        page_count: int | None = None,
        parse_status: str = "pending",
        parse_error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Document:
        document = Document(
            user_id=user_id,
            kind=kind,
            filename=filename,
            mime=mime,
            size_bytes=size_bytes,
            sha256=sha256,
            storage_path=storage_path,
            raw_text=raw_text,
            page_count=page_count,
            parse_status=parse_status,
            parse_error=parse_error,
            metadata_=dict(metadata or {}),
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def set_parsed(
        self,
        document: Document,
        *,
        raw_text: str | None,
        page_count: int | None,
        metadata: dict[str, Any],
    ) -> None:
        document.raw_text = raw_text
        document.page_count = page_count
        document.parse_status = "parsed"
        document.parse_error = None
        document.metadata_ = dict(metadata)
        await self._session.flush()

    async def mark_failed(self, document: Document, *, error: str) -> None:
        """A failed parse is stored, not just raised: the user has to be told, and the
        log line is not where a candidate looks."""
        document.parse_status = "failed"
        document.parse_error = error[:1000]
        await self._session.flush()

    async def delete(self, document: Document) -> None:
        """Hard delete: chunks and raw text go with it (the FK cascades)."""
        await self._session.delete(document)
        await self._session.flush()

    # ── chunks ───────────────────────────────────────────────────────────────

    async def replace_chunks(
        self,
        document: Document,
        chunks: Sequence[tuple[int, str, int, str, int, int]],
    ) -> int:
        """Replace a document's chunks atomically and return how many were written.

        Chunks are replaced rather than appended because re-parsing a document that was
        already ingested would otherwise leave the old fragments in the retrieval index,
        and a citation pointing at a chunk that no longer reflects the file is worse than
        no citation.
        """
        await self._session.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
        )
        for index, content, token_count, heading_path, char_start, char_end in chunks:
            self._session.add(
                DocumentChunk(
                    user_id=document.user_id,
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    token_count=token_count,
                    heading_path=heading_path,
                    char_start=char_start,
                    char_end=char_end,
                )
            )
        await self._session.flush()
        return len(chunks)

    async def count_chunks(self, *, document_id: UUID, user_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id, DocumentChunk.user_id == user_id)
        )
        return int(await self._session.scalar(statement) or 0)
