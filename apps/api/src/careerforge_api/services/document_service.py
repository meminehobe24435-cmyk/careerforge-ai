"""Document ingestion: upload → parse → chunk → store.

The service owns three product decisions that are easy to get wrong:

1. **A failed parse is stored, not just raised.** ``parse_status``/``parse_error`` exist in
   ``docs/DATABASE.md`` §2.3 so the candidate can be shown *why* their résumé was not read.
   That means committing the failure row before raising — the request transaction would
   otherwise roll it back (see ``deps.get_db``), and the explanation would exist only in a
   server log the candidate will never see.
2. **Identical bytes do not fork the graph.** ``sha256`` is unique per user, so a re-upload
   returns the existing document instead of producing a second evidence graph from the same
   file.
3. **Local Mode means the text is not stored.** ``users.storage_scope = 'local'`` or
   ``privacy_settings.retainRawText = false`` keeps the document row and its warnings but
   persists no text and no chunks. Storing the chunks anyway would quietly contradict the
   setting, since chunks *are* the text.
"""

from __future__ import annotations

from collections.abc import Sequence
import contextlib
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.errors import (
    DocumentParseError,
    DocumentTooLargeError,
    UnsupportedDocumentError,
)
from careerforge_ai.parsing.documents import (
    ParsedDocument,
    detect_format,
    parse_document,
    sha256_of,
)
from careerforge_ai.parsing.pii import scan_pii
from careerforge_ai.rag.chunking import SourceKind, chunk_text
from careerforge_api.core.config import get_api_settings
from careerforge_api.models.document import Document
from careerforge_api.models.user import User
from careerforge_api.repositories.document_repository import DocumentRepository

__all__ = ["DocumentIngestResult", "DocumentService", "safe_filename"]

#: Longest filename kept. The name is displayed and used in ``Content-Disposition``; a
#: 4 000-character name is an attack, not a filename.
MAX_FILENAME_LENGTH = 180

_UNSAFE_FILENAME = re.compile(r"[\x00-\x1f\x7f]")

#: Document kind → chunking kind. Only ``resume`` has its own sizing today (smaller
#: chunks, because a résumé's sections are short); everything else uses the prose default.
_CHUNKING_KIND: dict[str, SourceKind] = {
    "resume": "resume",
    "project_doc": "project_doc",
    "interview_note": "interview_note",
    "jd": "job_description",
}


def safe_filename(filename: str | None, *, fallback: str = "upload") -> str:
    """Reduce an uploaded name to something safe to store and display.

    Browsers send whatever the file was called, including a full Windows path
    (``C:\\Users\\me\\简历.pdf``) and, in a malicious case, ``../../etc/passwd``. Only the
    final component is kept.
    """
    candidate = (filename or "").strip().replace("\\", "/")
    candidate = candidate.rsplit("/", 1)[-1]
    candidate = _UNSAFE_FILENAME.sub("", candidate).strip()
    if not candidate or candidate in {".", ".."}:
        return fallback
    if len(candidate) > MAX_FILENAME_LENGTH:
        stem, dot, suffix = candidate.rpartition(".")
        keep = MAX_FILENAME_LENGTH - len(dot + suffix) if dot else MAX_FILENAME_LENGTH
        candidate = (
            f"{stem[: max(1, keep)]}{dot}{suffix}" if dot else candidate[:MAX_FILENAME_LENGTH]
        )
    return candidate


@dataclass(frozen=True, slots=True)
class DocumentIngestResult:
    """What an upload produced, including whether it was a re-upload.

    ``parsed`` is ``None`` when the bytes were already stored: the caller then has a
    document but no fresh parse, which is a different situation from a parse that failed.
    """

    document: Document
    parsed: ParsedDocument | None
    chunk_count: int
    text_retained: bool
    deduplicated: bool

    @property
    def warnings(self) -> list[str]:
        return self.document.warnings


@dataclass(frozen=True, slots=True)
class StagedUpload:
    """A stored upload that no one has parsed yet.

    ``document_id`` is what the queued job carries: bytes cannot travel through the job
    payload (``background_jobs.payload`` is JSON), so they wait in the spool directory
    that ``storage_path`` points at.
    """

    document: Document
    deduplicated: bool
    spool_path: Path


class DocumentService:
    """Upload handling for one user."""

    def __init__(self, session: AsyncSession, *, upload_dir: Path | None = None) -> None:
        self._session = session
        self._documents = DocumentRepository(session)
        self._upload_dir = upload_dir

    # ── stage ────────────────────────────────────────────────────────────────

    async def stage_upload(
        self,
        *,
        user: User,
        filename: str | None,
        data: bytes,
        kind: str = "resume",
        mime: str | None = None,
    ) -> StagedUpload:
        """Persist the upload and a ``pending`` row, ready for the worker.

        Raises:
            DocumentTooLargeError: the payload exceeds the configured limit.
        """
        if len(data) > self._max_bytes:
            raise DocumentTooLargeError(
                f"{safe_filename(filename)} is {len(data) / 1_048_576:.1f} MiB, above the "
                f"{self._max_bytes // 1_048_576} MiB upload limit"
            )
        if not data:
            raise DocumentParseError("the uploaded file is empty")

        name = safe_filename(filename)
        # Rejected here rather than in the worker: a file this build cannot read should get
        # a 400 naming the problem, not a 202 followed by a failed task minutes later.
        if detect_format(name, mime) is None:
            raise UnsupportedDocumentError(
                f"unsupported file type: {name}. This build reads PDF, DOCX, Markdown and "
                "plain text.",
                details={"filename": name, "mime": mime},
            )

        digest = sha256_of(data)
        existing = await self._documents.get_by_sha256(digest, user_id=user.id)
        if existing is not None:
            # Same bytes, same user: idempotent. The caller answers with the existing
            # document rather than starting a second parse of identical content.
            return StagedUpload(document=existing, deduplicated=True, spool_path=Path())

        retain = self.retains_raw_text(user)
        spool_path = self._spool(data, digest)
        document = await self._documents.create(
            user_id=user.id,
            kind=kind,
            filename=name,
            mime=mime,
            size_bytes=len(data),
            sha256=digest,
            storage_path=str(spool_path),
            parse_status="pending",
            metadata={"textRetained": retain},
        )
        await self._session.flush()
        return StagedUpload(document=document, deduplicated=False, spool_path=spool_path)

    def _spool(self, data: bytes, digest: str) -> Path:
        """Write the bytes to the spool directory, named by content hash.

        Named by hash so two concurrent uploads of the same file cannot collide, and so an
        abandoned file is recognisable without reading it — which is what the TTL sweep
        will rely on.
        """
        directory = self._upload_dir or get_api_settings().upload_path
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{digest}.bin"
        path.write_bytes(data)
        return path

    @property
    def _max_bytes(self) -> int:
        return get_api_settings().max_upload_bytes

    # ── ingest (runs in the worker) ───────────────────────────────────────────

    async def ingest_staged(self, document: Document, *, user: User) -> DocumentIngestResult:
        """Parse a staged document, write its chunks, and drop the spooled bytes.

        Raises:
            DocumentParseError: the file could not be read. The failure row is committed
                first, so ``GET /documents`` still shows what happened.
        """
        spool_path = Path(document.storage_path) if document.storage_path else None
        if spool_path is None or not spool_path.exists():
            message = (
                "the uploaded file is no longer available (it was spooled for parsing and "
                "the spool entry is gone); upload it again"
            )
            await self._documents.mark_failed(document, error=message)
            await self._session.commit()
            raise DocumentParseError(message)

        try:
            parsed = parse_document(
                spool_path.read_bytes(),
                filename=document.filename,
                mime=document.mime,
            )
        except DocumentParseError as exc:
            await self._documents.mark_failed(document, error=str(exc))
            # Committed on purpose: the row is the explanation the candidate will read,
            # and the request transaction would otherwise roll it back.
            await self._session.commit()
            raise

        retain = self.retains_raw_text(user)
        findings = scan_pii(parsed.text) if parsed.text else []
        metadata: dict[str, Any] = {
            "format": parsed.format.value,
            "encoding": parsed.encoding,
            "warnings": list(parsed.warnings),
            "charCount": parsed.char_count,
            "textRetained": retain and not parsed.is_empty,
            # Counted, not stored: the offsets would be as sensitive as the PII itself.
            "piiFindingCount": len(findings),
            "piiKinds": sorted({finding.kind.value for finding in findings}),
        }

        text = parsed.text if retain else None
        await self._documents.set_parsed(
            document, raw_text=text, page_count=parsed.page_count, metadata=metadata
        )

        chunk_count = 0
        if retain and not parsed.is_empty:
            chunk_count = await self._write_chunks(document, parsed)

        # The spool file has served its purpose. Leaving it behind would keep a copy of
        # the résumé on disk, which is exactly what ``raw_text IS NULL`` promises not to.
        document.storage_path = None
        await self._drop_spool(spool_path)
        await self._session.flush()

        return DocumentIngestResult(
            document=document,
            parsed=parsed,
            chunk_count=chunk_count,
            text_retained=retain and not parsed.is_empty,
            deduplicated=False,
        )

    @staticmethod
    async def _drop_spool(path: Path) -> None:
        # A read-only or already-removed spool entry must not fail an ingest whose real
        # work has already succeeded.
        with contextlib.suppress(OSError):
            path.unlink(missing_ok=True)

    @staticmethod
    def retains_raw_text(user: User) -> bool:
        """Whether this account allows server-side retention of document text.

        Local Mode (``storage_scope = 'local'``) is the documented promise that résumé
        text never leaves the machine; ``retainRawText: false`` is the per-account
        opt-out. Either one means no ``raw_text`` and no chunks — storing the chunks
        anyway would quietly contradict the setting, since chunks *are* the text.
        """
        if user.prefers_local_storage:
            return False
        return bool(user.privacy_settings.get("retainRawText", True))

    async def _write_chunks(self, document: Document, parsed: ParsedDocument) -> int:
        chunks = chunk_text(parsed.text, kind=_CHUNKING_KIND.get(document.kind, "notes"))
        rows = [
            (
                chunk.index,
                chunk.content,
                chunk.token_count,
                chunk.heading_path,
                chunk.char_start,
                chunk.char_end,
            )
            for chunk in chunks
            if chunk.content.strip()
        ]
        return await self._documents.replace_chunks(document, rows)

    # ── reads ────────────────────────────────────────────────────────────────

    async def get(self, document_id: UUID, *, user: User) -> Document | None:
        return await self._documents.get(document_id, user_id=user.id)

    async def list(
        self,
        *,
        user: User,
        kind: str | None = None,
        parse_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Document], int]:
        documents = await self._documents.list(
            user_id=user.id, kind=kind, parse_status=parse_status, limit=limit, offset=offset
        )
        total = await self._documents.count(user_id=user.id, kind=kind, parse_status=parse_status)
        return documents, total

    async def counts_by_kind(self, *, user: User) -> dict[str, int]:
        return await self._documents.counts_by_kind(user_id=user.id)

    async def delete(self, document: Document) -> None:
        await self._documents.delete(document)

    async def chunk_count(self, document: Document) -> int:
        return await self._documents.count_chunks(document_id=document.id, user_id=document.user_id)
