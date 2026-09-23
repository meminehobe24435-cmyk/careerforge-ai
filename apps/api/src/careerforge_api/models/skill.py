"""``skills`` — the global skill dictionary (``docs/DATABASE.md`` §2.2).

No ``user_id``: this is shared taxonomy, not user data (one of the documented
exceptions in §1.1). The rows are seeded from
:mod:`careerforge_ai.parsing.skill_taxonomy`, and ``docs/DATABASE.md`` §6 requires
``infra/db/init/002_skills.sql`` to stay isomorphic with that module — the
generator is ``scripts/gen_skills_sql.py`` and
``tests/test_skill_taxonomy.py`` asserts the two agree.
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType

__all__ = ["SKILL_CATEGORIES", "Skill"]

#: ``docs/DATABASE.md`` §2.2 — mirrors ``careerforge_ai.schemas.common.SkillCategory``.
SKILL_CATEGORIES: tuple[str, ...] = (
    "language",
    "framework",
    "embedded",
    "backend",
    "frontend",
    "ai",
    "devops",
    "database",
    "tool",
    "domain",
    "soft",
)

_CATEGORY_LIST = ", ".join(f"'{category}'" for category in SKILL_CATEGORIES)


class Skill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One controlled-vocabulary skill."""

    __tablename__ = "skills"
    __table_args__ = (
        CheckConstraint(f"category IN ({_CATEGORY_LIST})", name="category_valid"),
        UniqueConstraint("canonical_id", name="uq_skills_canonical_id"),
    )

    #: Stable normalised id used everywhere downstream, e.g. ``stm32``.
    canonical_id: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    #: ``["STM32F407", "stm32f4"]`` — used by the lexical matcher.
    aliases: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
