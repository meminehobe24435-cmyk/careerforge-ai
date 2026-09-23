"""``agent_runs`` and ``llm_calls`` — the observability tables (§2.11).

These two tables are what make the AI Runs and Cost dashboards real rather than
decorative (``docs/ARCHITECTURE.md`` §9). Both carry ``request_id`` so an HTTP call
can be joined with the agent steps and the individual model calls it produced, and
both keep ``prompt_version`` so a quality regression can be traced to the prompt
revision that caused it.
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from careerforge_api.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from careerforge_api.db.compat import JSONType, NumericType, TimestampType, UUIDType

__all__ = ["AgentRun", "LlmCall"]

AGENT_RUN_STATUSES: tuple[str, ...] = ("running", "succeeded", "failed", "degraded")
AGENT_RUN_TRIGGERS: tuple[str, ...] = ("api", "job", "manual", "seed", "eval")
LLM_OPERATIONS: tuple[str, ...] = ("chat", "stream", "embed", "structured")
LLM_STATUSES: tuple[str, ...] = ("ok", "error", "timeout", "rate_limited", "cache_hit")


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One workflow execution: steps, tokens, cost and latency."""

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in_list(AGENT_RUN_STATUSES)})", name="status_valid"),
        CheckConstraint(f"trigger IN ({_in_list(AGENT_RUN_TRIGGERS)})", name="trigger_valid"),
        CheckConstraint(
            "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0",
            name="token_counts_non_negative",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_non_negative"),
        Index("ix_agent_runs_user_id_started_at", "user_id", "started_at"),
        Index("ix_agent_runs_workflow_started_at", "workflow", "started_at"),
        Index("ix_agent_runs_request_id", "request_id"),
    )

    #: Nullable: system-triggered runs (seeding, evaluation) have no user.
    user_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    workflow: Mapped[str] = mapped_column(Text, nullable=False)
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")
    trigger: Mapped[str] = mapped_column(Text, nullable=False, default="api")
    #: Step trace array (``StepTrace`` models from the AI core).
    steps: Mapped[list[Any]] = mapped_column(JSONType, nullable=False, default=list)
    #: Redacted summaries only — never full document text (``docs/DATABASE.md`` §7).
    input_ref: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    output_ref: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False, default=dict)
    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(
        NumericType(10, 6), nullable=False, default=Decimal(0)
    )
    cost_cny: Mapped[Decimal] = mapped_column(
        NumericType(10, 6), nullable=False, default=Decimal(0)
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Sub-workflow linkage (nullable self-reference).
    parent_run_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    #: Correlates with the ``X-Request-Id`` response header.
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(TimestampType, nullable=True)

    #: Navigation only. ``lazy="raise"`` because an implicit load in an async
    #: session is a bug; ``passive_deletes`` because the FK already cascades.
    calls: Mapped[list[LlmCall]] = relationship(
        back_populates="run", lazy="raise", passive_deletes=True
    )


class LlmCall(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One model invocation, priced by ``careerforge_ai.observability.pricing``."""

    __tablename__ = "llm_calls"
    __table_args__ = (
        CheckConstraint(f"operation IN ({_in_list(LLM_OPERATIONS)})", name="operation_valid"),
        CheckConstraint(f"status IN ({_in_list(LLM_STATUSES)})", name="status_valid"),
        CheckConstraint(
            "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0",
            name="token_counts_non_negative",
        ),
        CheckConstraint("latency_ms IS NULL OR latency_ms >= 0", name="latency_non_negative"),
        Index("ix_llm_calls_user_id_created_at", "user_id", "created_at"),
        Index("ix_llm_calls_agent_created_at", "agent", "created_at"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        UUIDType, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True
    )
    agent: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    operation: Mapped[str] = mapped_column(Text, nullable=False, default="chat")
    prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(
        NumericType(10, 6), nullable=False, default=Decimal(0)
    )
    cost_cny: Mapped[Decimal] = mapped_column(
        NumericType(10, 6), nullable=False, default=Decimal(0)
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="ok")
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[AgentRun | None] = relationship(back_populates="calls", lazy="raise")
