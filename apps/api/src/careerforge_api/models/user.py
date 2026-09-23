"""``users``, ``profiles``, ``public_profiles`` — ``docs/DATABASE.md`` §2.1.

The ``CHECK`` constraints are the schema's own statement of the product rules:
``role``, ``storage_scope`` and the 0–100 profile strength are validated by the
database, not only by the request schemas, so a future internal job cannot write a
value the API would have rejected.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
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
from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType

__all__ = ["Profile", "PublicProfile", "User"]

ROLE_VALUES = ("user", "admin")
STORAGE_SCOPE_VALUES = ("cloud", "local")


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An account. Demonstration accounts have ``password_hash IS NULL`` + ``is_demo``."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user','admin')", name="role_valid"),
        CheckConstraint("storage_scope IN ('cloud','local')", name="storage_scope_valid"),
        CheckConstraint(
            "password_hash IS NOT NULL OR is_demo = true",
            name="demo_accounts_need_no_password",
        ),
        UniqueConstraint("email", name="uq_users_email"),
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    #: bcrypt digest; ``None`` only for demo accounts (``docs/DATABASE.md`` §2.1).
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="user")
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage_scope: Mapped[str] = mapped_column(Text, nullable=False, default="cloud")
    #: Public-page visibility, raw-text retention, … (``docs/API.md`` §2.1 ``/me/settings``).
    privacy_settings: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="zh-CN")
    last_login_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)

    profile: Mapped[Profile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    public_profile: Mapped[PublicProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def is_demo_account(self) -> bool:
        return bool(self.is_demo)

    @property
    def prefers_local_storage(self) -> bool:
        """Local Mode: resume text is never persisted server-side."""
        return self.storage_scope == "local"


class Profile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One-to-one career profile; ``slug`` is the public page key."""

    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(
            "profile_strength IS NULL OR (profile_strength >= 0 AND profile_strength <= 100)",
            name="profile_strength_range",
        ),
        CheckConstraint(
            "years_experience IS NULL OR (years_experience >= 0 AND years_experience <= 99.9)",
            name="years_experience_range",
        ),
        UniqueConstraint("user_id", name="uq_profiles_user_id"),
        UniqueConstraint("slug", name="uq_profiles_slug"),
    )

    #: Tenant key — every read of this table is filtered by it.
    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    github_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: e.g. ``["Embedded Engineer","AI Application Engineer"]``
    target_roles: Mapped[list[str]] = mapped_column(JSONType, nullable=False, default=list)
    years_experience: Mapped[Decimal | None] = mapped_column(NumericType(3, 1), nullable=True)
    profile_strength: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Five-dimension breakdown + suggestions (``docs/API.md`` §2.2).
    strength_breakdown: Mapped[dict[str, Any]] = mapped_column(
        JSONType, nullable=False, default=dict
    )
    #: Redundant counters refreshed on write (evidence/skills/projects).
    stats: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)

    user: Mapped[User] = relationship(back_populates="profile")


class PublicProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Published view of a profile, with per-section visibility (``docs/API.md`` §2.12)."""

    __tablename__ = "public_profiles"
    __table_args__ = (
        CheckConstraint("view_count >= 0", name="view_count_non_negative"),
        UniqueConstraint("user_id", name="uq_public_profiles_user_id"),
        UniqueConstraint("slug", name="uq_public_profiles_slug"),
        Index("ix_public_profiles_is_published", "is_published"),
    )

    user_id: Mapped[UUID] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: ``{skills: true, projects: true, evidence: true, contact: false}``
    sections: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    highlights: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    interview_topics: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)

    user: Mapped[User] = relationship(back_populates="public_profile")
