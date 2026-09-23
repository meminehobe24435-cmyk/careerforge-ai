"""``evidence``, ``evidence_links`` — ``docs/DATABASE.md`` §2.5, the core of the product.

Two decisions are enforced here rather than in application code:

* the **confidence formula is a ``CHECK`` constraint** (``docs/DATABASE.md`` §3). The
  number a UI shows as "0.72 confidence" can therefore be recomputed in SQL and must
  agree with the five stored factors; a future writer cannot store a confidence that its
  own inputs do not produce. The tolerance (0.002) exists because the engine rounds to
  three decimals.
* an **edge is unique per five-tuple** ``(user_id, from_type, from_id, to_type, to_id,
  relation)``, so rebuilding a graph is idempotent instead of silently doubling it.

``repo_file_id`` and ``repo_commit_id`` from §2.5 are **not** declared yet: they are
foreign keys into §2.4's ``repo_files`` / ``repo_commits``, which arrive with GitHub
Intelligence. Creating a column whose referenced table does not exist would fail the
migration, and a column without its foreign key would accept dangling ids. ``metadata``
carries the repository provenance until then.
"""

from __future__ import annotations

from datetime import datetime
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
from sqlalchemy.orm import Mapped, mapped_column

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType

__all__ = [
    "EVIDENCE_KINDS",
    "EVIDENCE_RELATIONS",
    "ConfidenceFormulaError",
    "Evidence",
    "EvidenceLinkRow",
    "confidence_formula_sql",
]

#: ``docs/DATABASE.md`` §2.5 — mirrors ``careerforge_ai.schemas.common.EvidenceKind``.
EVIDENCE_KINDS: tuple[str, ...] = (
    "repo_file",
    "commit",
    "readme",
    "document_chunk",
    "experience",
    "project",
    "achievement",
    "manual",
    "llm_inference",
)

#: Mirrors ``careerforge_ai.schemas.common.EvidenceRelation``.
EVIDENCE_RELATIONS: tuple[str, ...] = (
    "HAS",
    "DEMONSTRATES",
    "EVIDENCED_BY",
    "SUPPORTS",
    "REQUIRES",
    "MATCHES",
    "GAP",
    "DERIVED_FROM",
)

_KIND_LIST = ", ".join(f"'{kind}'" for kind in EVIDENCE_KINDS)
_RELATION_LIST = ", ".join(f"'{relation}'" for relation in EVIDENCE_RELATIONS)


class ConfidenceFormulaError(ValueError):
    """Raised when a stored confidence does not match its inputs."""


def confidence_formula_sql() -> str:
    """The five-factor formula, as a single SQL expression.

    Written with ``CASE`` rather than ``least()``: PostgreSQL has ``least`` and SQLite
    has the two-argument ``min``, and this expression has to mean the same thing on both
    (ADR-004). ``docs/DATABASE.md`` §3 shows the PostgreSQL spelling of the same maths.
    """
    corroboration = (
        "CASE WHEN 0.4 + 0.2 * corroboration_count > 1.0 THEN 1.0 "
        "ELSE 0.4 + 0.2 * corroboration_count END"
    )
    return (
        "0.30 * source_authority + 0.15 * recency_score + 0.20 * specificity "
        f"+ 0.20 * ({corroboration}) + 0.15 * extraction_quality"
    )


#: The constraint the database enforces. Kept next to the expression so the migration,
#: the model and any test that recomputes a confidence all refer to one definition.
_CONFIDENCE_CHECK = "abs(confidence - (" + confidence_formula_sql() + ")) < 0.002"

_UNIT_COLUMNS = (
    "source_authority",
    "specificity",
    "extraction_quality",
    "recency_score",
    "confidence",
)


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One piece of evidence, with the factors that produced its confidence."""

    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_KIND_LIST})", name="kind_valid"),
        *(
            CheckConstraint(f"{column} BETWEEN 0 AND 1", name=f"{column}_unit_range")
            for column in _UNIT_COLUMNS
        ),
        CheckConstraint("corroboration_count >= 0", name="corroboration_non_negative"),
        CheckConstraint(_CONFIDENCE_CHECK, name="confidence_formula"),
        # Re-extracting the same text must update one row, not create a second copy.
        UniqueConstraint("user_id", "kind", "content_hash", name="uq_evidence_user_id"),
        Index("ix_evidence_user_id_kind", "user_id", "kind"),
        Index("ix_evidence_user_id_confidence", "user_id", "confidence"),
        Index("ix_evidence_user_id_occurred_at", "user_id", "occurred_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    snippet: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: ``{path, line, url, sha, page, char_start, char_end, section}``
    locator: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)

    # ── the five factors, stored so the score can be reproduced ──────────────
    source_authority: Mapped[Decimal] = mapped_column(NumericType(4, 3), nullable=False)
    specificity: Mapped[Decimal] = mapped_column(NumericType(4, 3), nullable=False)
    extraction_quality: Mapped[Decimal] = mapped_column(NumericType(4, 3), nullable=False)
    recency_score: Mapped[Decimal] = mapped_column(NumericType(4, 3), nullable=False)
    corroboration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[Decimal] = mapped_column(NumericType(4, 3), nullable=False)

    occurred_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)
    #: Set when the evidence came from an uploaded document. ``SET NULL`` keeps the
    #: evidence if the chunk is re-chunked, rather than deleting a citation.
    document_chunk_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("document_chunks.id", ondelete="SET NULL"), nullable=True
    )
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONType, nullable=False, default=dict
    )

    @property
    def sources(self) -> int:
        """Independent sources behind this item, for the corroboration explanation."""
        return int(self.corroboration_count)

    @property
    def recomputed_confidence(self) -> float:
        """The formula applied to the stored factors — what the DB constraint checks."""
        corroboration = min(1.0, 0.4 + 0.2 * float(self.corroboration_count))
        return round(
            0.30 * float(self.source_authority)
            + 0.15 * float(self.recency_score)
            + 0.20 * float(self.specificity)
            + 0.20 * corroboration
            + 0.15 * float(self.extraction_quality),
            3,
        )


class EvidenceLinkRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One edge of the graph, stored as an adjacency row (ADR-005).

    Named ``EvidenceLinkRow`` because ``EvidenceLink`` is the schema object the AI core
    passes around; the two are deliberately different — one is a portable value, the
    other a row with tenancy and timestamps.
    """

    __tablename__ = "evidence_links"
    __table_args__ = (
        CheckConstraint(f"relation IN ({_RELATION_LIST})", name="relation_valid"),
        CheckConstraint("weight BETWEEN 0 AND 1", name="weight_unit_range"),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1", name="confidence_unit_range"
        ),
        CheckConstraint("from_id <> to_id", name="no_self_loops"),
        UniqueConstraint(
            "user_id",
            "from_type",
            "from_id",
            "to_type",
            "to_id",
            "relation",
            name="uq_evidence_links_user_id",
        ),
        Index("ix_evidence_links_user_id_from", "user_id", "from_type", "from_id"),
        Index("ix_evidence_links_user_id_to", "user_id", "to_type", "to_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Polymorphic endpoints: ``GraphNodeType`` values, not foreign keys — a node may be
    #: a candidate, a skill, an evidence item or (later) a claim.
    from_type: Mapped[str] = mapped_column(Text, nullable=False)
    from_id: Mapped[UUID] = mapped_column(UUIDType, nullable=False)
    to_type: Mapped[str] = mapped_column(Text, nullable=False)
    to_id: Mapped[UUID] = mapped_column(UUIDType, nullable=False)
    relation: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[Decimal] = mapped_column(
        NumericType(4, 3), nullable=False, default=Decimal("1.0")
    )
    confidence: Mapped[Decimal | None] = mapped_column(NumericType(4, 3), nullable=True)
    #: Why this edge exists, in the words a human would use — the "Why?" of the UI.
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
