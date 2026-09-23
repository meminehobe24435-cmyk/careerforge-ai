"""``documents``, ``document_chunks`` — ``docs/DATABASE.md`` §2.3.

This is the table pair that turns "the candidate uploaded something" into material the
rest of the system can cite. Two design points are load-bearing:

* ``sha256`` is unique per user, so re-uploading the same résumé updates one row instead
  of creating a second evidence graph from identical bytes;
* ``parse_status`` plus ``parse_error`` make a failed parse a *stored fact*. A résumé that
  could not be read is the single most important thing to tell a candidate, and it cannot
  be told if the failure only existed in a log line.

``raw_text`` is nullable on purpose: Local Mode (``users.storage_scope = 'local'``) and
the ``retainRawText: false`` privacy setting both mean the owner's document text is never
persisted, while the row and its metadata still exist so the UI can show what was read.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType, UUIDType

__all__ = [
    "DOCUMENT_KINDS",
    "DOCUMENT_PARSE_STATUSES",
    "Document",
    "DocumentChunk",
]

#: ``docs/DATABASE.md`` §2.3 — mirrors ``careerforge_ai``'s notion of a material kind.
DOCUMENT_KINDS: tuple[str, ...] = ("resume", "project_doc", "interview_note", "jd", "notes")

#: A parse is a small state machine, not a boolean: a scanned PDF is ``parsed`` with a
#: warning, while an unreadable file is ``failed`` with an error the user can act on.
DOCUMENT_PARSE_STATUSES: tuple[str, ...] = ("pending", "parsing", "parsed", "failed")

_KIND_LIST = ", ".join(f"'{kind}'" for kind in DOCUMENT_KINDS)
_STATUS_LIST = ", ".join(f"'{status}'" for status in DOCUMENT_PARSE_STATUSES)


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One uploaded file and the outcome of reading it."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_KIND_LIST})", name="kind_valid"),
        CheckConstraint(f"parse_status IN ({_STATUS_LIST})", name="parse_status_valid"),
        CheckConstraint("size_bytes >= 0", name="size_bytes_non_negative"),
        CheckConstraint("page_count IS NULL OR page_count >= 0", name="page_count_non_negative"),
        # Re-uploading identical bytes must not fork the evidence graph. Scoped to the
        # user so one candidate's upload cannot reveal that another has the same file.
        UniqueConstraint("user_id", "sha256", name="uq_documents_user_id_sha256"),
        Index("ix_documents_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    #: Already sanitised for path traversal and length; see the service.
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Content hash — the de-duplication key and the parse cache key.
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    #: Object-store key. ``None`` in Local Mode, where bytes never leave the machine.
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ``None`` when the owner disabled raw-text retention.
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Whether the *stored* text was redacted. Owner-facing reads keep it unredacted;
    #: the public page redacts on projection, which is where it actually matters.
    is_redacted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Format, detected encoding, ingestion warnings, PII finding count.
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def was_parsed(self) -> bool:
        return self.parse_status == "parsed"

    @property
    def has_readable_text(self) -> bool:
        """Whether anything downstream can actually work with this document."""
        return bool(self.raw_text and self.raw_text.strip())

    @property
    def warnings(self) -> list[str]:
        """Ingestion warnings, e.g. a scanned PDF or a non-UTF-8 decode."""
        found = self.metadata_.get("warnings")
        return [str(item) for item in found] if isinstance(found, list) else []


class DocumentChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A heading-scoped fragment of a document, ready for retrieval.

    ``user_id`` is denormalised from the parent document because every read is filtered
    by it (``docs/DATABASE.md`` §1.1) and the retrieval query filters chunks directly.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("chunk_index >= 0", name="chunk_index_non_negative"),
        CheckConstraint("token_count >= 0", name="token_count_non_negative"),
        CheckConstraint("char_start >= 0 AND char_end >= char_start", name="char_range_valid"),
        CheckConstraint("page_no IS NULL OR page_no >= 1", name="page_no_positive"),
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_id"),
        Index(
            "ix_document_chunks_user_id_document_id_chunk_index",
            "user_id",
            "document_id",
            "chunk_index",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: ``"实习经历 > 某某科技"`` — what makes a retrieved hit justifiable to a human.
    heading_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    document: Mapped[Document] = relationship(back_populates="chunks")

    @property
    def locator_display(self) -> str:
        """Compact reference shown next to a claim, e.g. ``resume.pdf · page 2``."""
        if self.heading_path:
            return self.heading_path
        if self.page_no:
            return f"page {self.page_no}"
        return f"chars {self.char_start}–{self.char_end}"
