"""``resume_versions``, ``resume_claims``, ``claim_evidence`` — ``docs/DATABASE.md`` §2.9.

This is the anti-hallucination gate's memory, and the reason the product can make its central
claim. Three design points carry it:

* **a claim row stores its own verdict, not just its text.** Status, confidence, the rules that
  fired and the safer rewrite all persist, so "why was this sentence rewritten" is answerable
  months later without re-running a model that may not even be configured.
* **``claim_evidence`` is the traceability itself.** A supported claim without a row here would
  be an assertion with nothing behind it, so the UI reads this table to show *which* evidence
  justifies a sentence. ``relevance`` and ``channel`` are kept because "found by keyword" and
  "found by meaning" deserve different levels of trust.
* **``resume_version_id`` is nullable on a claim.** The Validator page lets a candidate check a
  single sentence without creating a résumé version, and a claim that cannot be stored on its own
  would make that page impossible.

``claim_validations`` (§2.9's re-validation history) is not here yet: the verdict columns on the
claim row are what this build reads, and a history table nothing writes to would be scaffolding.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType, NumericType, UUIDType

__all__ = [
    "CLAIM_SECTIONS",
    "CLAIM_STATUSES",
    "RESUME_SOURCES",
    "RETRIEVAL_CHANNELS",
    "ClaimEvidence",
    "ResumeClaim",
    "ResumeVersion",
]

#: Mirrors the AI core's ``ClaimStatus``, ``RetrievalChannel`` and the docs' section list.
CLAIM_STATUSES: tuple[str, ...] = (
    "pending",
    "supported",
    "partially_supported",
    "unsupported",
    "contradicted",
)
CLAIM_SECTIONS: tuple[str, ...] = ("summary", "experience", "project", "skill", "education")
RETRIEVAL_CHANNELS: tuple[str, ...] = ("semantic", "keyword", "both", "manual")
RESUME_SOURCES: tuple[str, ...] = ("generated", "uploaded", "manual")


def _check(column: str, values: tuple[str, ...]) -> CheckConstraint:
    return CheckConstraint(
        f"{column} IN ({', '.join(repr(value) for value in values)})", name=f"{column}_valid"
    )


class ResumeVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One résumé state: what was generated, for which job, and how well supported it is."""

    __tablename__ = "resume_versions"
    __table_args__ = (
        _check("source", RESUME_SOURCES),
        CheckConstraint("integrity_score BETWEEN 0 AND 1", name="integrity_score_unit_range"),
        Index("ix_resume_versions_user_id_created_at", "user_id", "created_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: The posting this version was tailored to, when there is one. ``SET NULL`` on delete:
    #: removing a job must not delete the résumé a candidate wrote for it.
    target_job_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(Text, nullable=False, default="generated")
    content_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    #: Previous version, for a diff. No cascade: a version chain is history, not ownership.
    parent_version_id: Mapped[UUID | None] = mapped_column(UUIDType, nullable=True)
    diff_summary: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    #: Share of bullets with evidence behind them — the number this whole feature exists for.
    integrity_score: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("0.0")
    )
    #: ``{supported: 8, partially_supported: 2, unsupported: 1, contradicted: 0}``
    claim_stats: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)

    claims: Mapped[list[ResumeClaim]] = relationship(
        back_populates="version", cascade="all, delete-orphan", lazy="selectin"
    )


class ResumeClaim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One sentence the candidate asserts, with the gate's verdict on it."""

    __tablename__ = "resume_claims"
    __table_args__ = (
        _check("section", CLAIM_SECTIONS),
        _check("status", CLAIM_STATUSES),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_unit_range"),
        Index("ix_resume_claims_user_id_status", "user_id", "status"),
        Index("ix_resume_claims_resume_version_id", "resume_version_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Nullable: the Validator page checks a sentence that belongs to no version yet.
    resume_version_id: Mapped[UUID | None] = mapped_column(
        UUIDType,
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        nullable=True,
    )
    target_job_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    section: Mapped[str] = mapped_column(Text, nullable=False, default="summary")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    #: The candidate's own wording, kept so a diff can show what changed and a reviewer can
    #: judge whether the rewrite invented something.
    original_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    confidence: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("0.0")
    )
    safe_rewrite: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: The rules that fired, each with its message — `numeric_without_evidence` and friends.
    reasons: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    #: Retrieval detail: which channels ran and what they returned.
    retrieval: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    has_quantified_claim: Mapped[bool] = mapped_column(nullable=False, default=False)
    independent_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rule_version: Mapped[str] = mapped_column(Text, nullable=False, default="claim_rules@1.0.0")
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)

    version: Mapped[ResumeVersion | None] = relationship(back_populates="claims")
    evidence: Mapped[list[ClaimEvidence]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_supported(self) -> bool:
        return self.status in {"supported", "partially_supported"}


class ClaimEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The link that makes a claim traceable: this sentence rests on that evidence.

    A row here is the difference between "the gate said yes" and "here is why". Deleting the
    evidence removes the row (``ON DELETE CASCADE``): a citation pointing at material that no
    longer exists is worse than no citation, because it looks like proof.
    """

    __tablename__ = "claim_evidence"
    __table_args__ = (
        _check("channel", RETRIEVAL_CHANNELS),
        CheckConstraint("relevance BETWEEN 0 AND 1", name="relevance_unit_range"),
        CheckConstraint("rank >= 0", name="rank_non_negative"),
        UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence_claim_id"),
        Index("ix_claim_evidence_evidence_id", "evidence_id"),
    )

    claim_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("resume_claims.id", ondelete="CASCADE"), nullable=False
    )
    evidence_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False
    )
    #: Denormalised for the same reason as elsewhere: every read is tenant-filtered (§1.1).
    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relevance: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("0.0")
    )
    #: Which arm of the hybrid retrieval produced it, so the UI can say how it was found.
    channel: Mapped[str] = mapped_column(Text, nullable=False, default="semantic")
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    claim: Mapped[ResumeClaim] = relationship(back_populates="evidence")
