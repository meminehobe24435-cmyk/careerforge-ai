"""``prompt_versions`` — the database mirror of the prompt registry.

``docs/DATABASE.md`` §2.11 and ``docs/ARCHITECTURE.md`` §9: the registry lives on
disk (``prompts/*.md``, the reviewable artefact) and the active set is synchronised
into this table at startup so a run can reference ``name@version`` and
``content_sha256`` long after the file changed.

No ``user_id`` (documented exception in §1.1) — prompts are product configuration.

Version semantics, from ``docs/DATABASE.md`` §2.11: *"内容哈希变化即新增版本"*. A
file whose content changed without bumping its declared ``version:`` therefore
produces a **new row** at the next free version, instead of silently rewriting
history that already-traced runs point at.
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType

__all__ = ["PromptVersion"]


class PromptVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One immutable revision of one prompt."""

    __tablename__ = "prompt_versions"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        UniqueConstraint("name", "version", name="uq_prompt_versions_name_version"),
        Index("ix_prompt_versions_name_is_active", "name", "is_active"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Full prompt body, stored so a historical run can be reproduced verbatim.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    variables: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Exactly one active version per ``name`` (maintained by the sync service).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    @property
    def ref(self) -> str:
        """``jd_analysis@v2`` — the string recorded on every LLM call."""
        return f"{self.name}@v{self.version}"
