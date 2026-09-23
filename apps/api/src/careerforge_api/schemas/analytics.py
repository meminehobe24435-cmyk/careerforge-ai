"""Analytics response models (``docs/API.md`` §2.11).

The shapes mirror the engine's value objects field for field, in camelCase, and they keep the
one property that matters: **a rate never travels without its counts**. A client that renders
"Interview Rate 40%" has, in the same object, the ``2 / 5`` it came from and the ``sufficient``
flag that says whether five is enough to say anything — and the definitions of every stage and
card are in the payload rather than in a tooltip somebody has to maintain twice.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AnalyticsMeta",
    "CategoryPerformanceResponse",
    "FunnelResponse",
    "FunnelStageResponse",
    "RateCardResponse",
    "RatesResponse",
    "SkillCorrelationResponse",
    "TimelineBucketResponse",
    "TimelineEntryResponse",
    "TimelineResponse",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class AnalyticsMeta(_CamelModel):
    """The window and the sample policy, shipped with every analytics payload."""

    range: str = Field(description="7d / 30d / 90d / all.")
    from_at: datetime | None = Field(default=None, alias="fromAt")
    to_at: datetime | None = Field(default=None, alias="toAt")
    #: Cards **created** in the window, wishlist bookmarks included — the pool the funnel draws
    #: from, not the funnel's denominator. The funnel's denominator is its first stage
    #: (``applications``: cards that ever left the wishlist), and each rate carries its own
    #: ``denominator``. Live check: six cards created, one still a bookmark, ``cohortSize`` 6
    #: while ``applications`` is 5.
    cohort_size: int = Field(default=0, alias="cohortSize")
    minimum_sample: int = Field(
        default=5,
        alias="minimumSample",
        description="Below this, a rate is reported but marked insufficient.",
    )
    window_basis: str = Field(
        default="applications",
        alias="windowBasis",
        description=(
            "What the range filters. 'applications' = cohort by creation time (funnel, rates, "
            "correlation, categories); 'events' = by when milestones happened (timeline)."
        ),
    )
    notes: list[str] = Field(default_factory=list)


class FunnelStageResponse(_CamelModel):
    key: str
    label: str
    count: int
    share_of_first: float = Field(alias="shareOfFirst")
    #: ``null`` when the stage above it is empty — nobody converted, and 1.0 would read as
    #: "everyone did".
    step_rate: float | None = Field(default=None, alias="stepRate")
    basis: str = ""


class FunnelResponse(_CamelModel):
    meta: AnalyticsMeta
    stages: list[FunnelStageResponse] = Field(default_factory=list)


class RateCardResponse(_CamelModel):
    key: str
    label: str
    #: ``null`` when there is nothing to divide by.
    rate: float | None = None
    numerator: int = 0
    denominator: int = 0
    sufficient: bool = False
    interval_low: float = Field(default=0.0, alias="intervalLow")
    interval_high: float = Field(default=0.0, alias="intervalHigh")
    definition: str = ""


class RatesResponse(_CamelModel):
    meta: AnalyticsMeta
    cards: list[RateCardResponse] = Field(default_factory=list)


class SkillCorrelationResponse(_CamelModel):
    skill_id: str = Field(alias="skillId")
    display_name: str = Field(alias="displayName")
    with_skill_total: int = Field(default=0, alias="withSkillTotal")
    with_skill_successes: int = Field(default=0, alias="withSkillSuccesses")
    with_skill_rate: float = Field(default=0.0, alias="withSkillRate")
    without_skill_total: int = Field(default=0, alias="withoutSkillTotal")
    without_skill_successes: int = Field(default=0, alias="withoutSkillSuccesses")
    without_skill_rate: float = Field(default=0.0, alias="withoutSkillRate")
    lift: float = 0.0
    sufficient: bool = False
    notable: bool = False
    note: str = ""


class CategoryPerformanceResponse(_CamelModel):
    category: str
    applications: int = 0
    interviews: int = 0
    offers: int = 0
    interview_rate: float = Field(default=0.0, alias="interviewRate")
    average_match_score: float | None = Field(default=None, alias="averageMatchScore")
    sufficient: bool = False


class TimelineEntryResponse(_CamelModel):
    kind: str
    title: str
    occurred_at: datetime = Field(alias="occurredAt")
    status: str | None = None
    ref_id: str | None = Field(default=None, alias="refId")


class TimelineBucketResponse(_CamelModel):
    month: str
    applications: int = 0
    interviews: int = 0
    offers: int = 0


class TimelineResponse(_CamelModel):
    meta: AnalyticsMeta
    entries: list[TimelineEntryResponse] = Field(default_factory=list)
    buckets: list[TimelineBucketResponse] = Field(default_factory=list)
