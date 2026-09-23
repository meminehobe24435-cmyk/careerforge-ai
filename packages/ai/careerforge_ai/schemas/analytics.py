"""Analytics schemas — the shapes the funnel, the rates and the correlations come in.

These are internal value objects, not LLM contracts: no model ever produces one of these
numbers. They live in the AI core anyway because the arithmetic does, and because the same
objects can then be produced by a test, by the eval harness or by the API without a second
definition.

The single design rule: **a rate never travels alone.** Every rate carries the counts it was
computed from and whether those counts clear the sample minimum, so a caller cannot render
"67%" without also having the "out of 3" to render beside it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from careerforge_ai.schemas.common import CFBaseModel

__all__ = [
    "CategoryPerformance",
    "FunnelCohort",
    "FunnelStage",
    "RateCard",
    "SkillCorrelation",
    "TimelineBucket",
    "TimelineEntry",
]


class FunnelCohort(CFBaseModel):
    """The window a funnel was computed over, stated in the response.

    The window filters **applications by creation time**, not events: the question a funnel
    answers is "of the applications I started in this period, how many progressed", and a
    numerator drawn from a different window than the denominator would make the rate mean
    something nobody asked for.
    """

    range: str = Field(description="One of 7d / 30d / 90d / all.")
    from_at: datetime | None = None
    to_at: datetime | None = None
    applications: int = 0


class FunnelStage(CFBaseModel):
    """One bar of the funnel, counted from what actually happened."""

    key: str = Field(description="Machine key, e.g. applications / replies / interviews.")
    label: str = Field(description="Human label, shown as given.")
    count: int = Field(ge=0)
    #: Share of the first stage (``applications``), not of the previous stage: two funnels
    #: are then comparable at a glance. The step-to-step ratio is ``step_rate``.
    share_of_first: float = Field(ge=0, le=1)
    step_rate: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Conversion from the previous stage; 1.0 for the first stage and **null when the "
            "previous stage is empty** — nobody converted, and 1.0 there would read as "
            "'everyone did'."
        ),
    )
    basis: str = Field(
        default="",
        description="How this stage was counted — a stage whose definition is implicit is a "
        "stage nobody can verify.",
    )


class RateCard(CFBaseModel):
    """A headline ratio with its counts and its verdict on sample size."""

    key: str
    label: str
    #: Null when there is nothing to divide by — "no applications in this window" is not a
    #: rate of zero, and a dashboard that prints 0% for an empty account states something it
    #: cannot know.
    rate: float | None = Field(default=None, ge=0, le=1)
    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)
    sufficient: bool
    interval_low: float = Field(ge=0, le=1)
    interval_high: float = Field(ge=0, le=1)
    definition: str = ""


class SkillCorrelation(CFBaseModel):
    """One skill's association with reaching an interview.

    Both groups are reported. A skill present in every application has no comparison group,
    and the honest answer there is "cannot tell" rather than a rate against nothing.
    """

    skill_id: str
    display_name: str
    with_skill_total: int = Field(ge=0)
    with_skill_successes: int = Field(ge=0)
    with_skill_rate: float = Field(ge=0, le=1)
    without_skill_total: int = Field(ge=0)
    without_skill_successes: int = Field(ge=0)
    without_skill_rate: float = Field(ge=0, le=1)
    lift: float = Field(description="with − without; signed, and negative is a finding.")
    sufficient: bool
    notable: bool = Field(
        description="Both groups clear the minimum and their 95% intervals do not overlap."
    )
    note: str = ""


class CategoryPerformance(CFBaseModel):
    """One role family's record: applications, interviews, offers, mean match score."""

    category: str
    applications: int = Field(ge=0)
    interviews: int = Field(ge=0)
    offers: int = Field(ge=0)
    interview_rate: float = Field(ge=0, le=1)
    average_match_score: float | None = None
    sufficient: bool


class TimelineEntry(CFBaseModel):
    """One milestone, as the candidate would tell it."""

    kind: str
    title: str
    occurred_at: datetime
    status: str | None = None
    ref_id: str | None = None


class TimelineBucket(CFBaseModel):
    """One month of activity, for the trend chart."""

    month: str = Field(description="YYYY-MM.")
    applications: int = Field(ge=0)
    interviews: int = Field(ge=0)
    offers: int = Field(ge=0)
