"""The funnel, the rates and the cohort window.

The whole module answers one question in one way: **what actually happened to these
applications?** The board shows where cards *are*; a funnel shows how far they *got*, and the
two differ on purpose — a card that reached an interview and was then rejected is
``rejected`` on the board and *was interviewed* in the funnel. PHASE 8b documented that
distinction when it defined the dashboard's ``interviews`` metric as a snapshot; this is the
other half of it.

Counting rules, each stated in the response as ``basis`` so a reader can check it:

* **Applications** — cards that ever left ``wishlist``. A wishlist card is a bookmark, not an
  application, and counting it would deflate every rate below it.
* **Replies** — ever reached ``oa`` / ``interview`` / ``final`` / ``offer``, or was rejected
  *after applying*. A rejection is a reply; treating it as silence would understate the
  response rate and, worse, would teach the candidate that their applications vanish.
* **Interviews** — ever reached ``interview`` / ``final`` / ``offer``.
* **Finals** — ever reached ``final`` / ``offer``.
* **Offers** — ever reached ``offer``.

Everything comes from ``application_events``, which is why that table is append-only and why
the tracker writes a row for every status change including a rewind: a card dragged backwards
still happened.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from careerforge_ai.analytics.stats import (
    MIN_SAMPLE,
    mean_or_none,
    sample_is_sufficient,
    wilson_interval,
)
from careerforge_ai.schemas.analytics import FunnelCohort, FunnelStage, RateCard
from careerforge_ai.schemas.common import ApplicationStatus

__all__ = [
    "RANGE_DAYS",
    "ApplicationRecord",
    "build_funnel",
    "cohort_window",
    "compute_rates",
    "in_range",
]

#: Supported ``?range=`` values and their window in days. ``all`` is unbounded.
RANGE_DAYS: dict[str, int | None] = {"7d": 7, "30d": 30, "90d": 90, "all": None}

#: Statuses that count as "the employer replied".
_REPLY_STATUSES: tuple[str, ...] = ("oa", "interview", "final", "offer")
_INTERVIEW_STATUSES: tuple[str, ...] = ("interview", "final", "offer")
_FINAL_STATUSES: tuple[str, ...] = ("final", "offer")
_OFFER_STATUSES: tuple[str, ...] = ("offer",)


@dataclass(frozen=True, slots=True)
class ApplicationRecord:
    """One application, reduced to what the analytics need.

    ``statuses_seen`` is the union of every status the card has ever held (from the event log),
    not its current status — see the module docstring.
    """

    id: str
    created_at: datetime
    statuses_seen: frozenset[str]
    match_score: float | None = None
    job_id: str | None = None
    required_skills: tuple[str, ...] = ()
    category: str | None = None

    @property
    def was_applied(self) -> bool:
        """Left the wishlist at some point — the funnel's first stage."""
        return any(status != ApplicationStatus.WISHLIST.value for status in self.statuses_seen)

    def reached(self, targets: Sequence[str]) -> bool:
        return any(target in self.statuses_seen for target in targets)

    @property
    def was_rejected(self) -> bool:
        return ApplicationStatus.REJECTED.value in self.statuses_seen


def cohort_window(
    *, range_key: str, now: datetime, records: Sequence[ApplicationRecord]
) -> tuple[FunnelCohort, list[ApplicationRecord]]:
    """Filter the cohort and describe the window that was actually applied.

    ``from_at`` is ``None`` for ``all`` — and it is worth saying out loud in the response,
    because "no lower bound" and "a bound we forgot to send" look identical otherwise.
    """
    if range_key not in RANGE_DAYS:
        raise ValueError(f"unknown range '{range_key}'; expected one of {', '.join(RANGE_DAYS)}")
    days = RANGE_DAYS[range_key]
    from_at = None if days is None else now - timedelta(days=days)
    selected = [record for record in records if in_range(record, from_at=from_at)]
    return (
        FunnelCohort(range=range_key, from_at=from_at, to_at=now, applications=len(selected)),
        selected,
    )


def in_range(record: ApplicationRecord, *, from_at: datetime | None) -> bool:
    """Whether a card belongs to the cohort (creation time, normalised to UTC)."""
    if from_at is None:
        return True
    created = record.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created >= from_at


@dataclass(slots=True)
class _Stage:
    key: str
    label: str
    basis: str
    members: list[ApplicationRecord] = field(default_factory=list)


def build_funnel(records: Sequence[ApplicationRecord]) -> list[FunnelStage]:
    """Count the five documented stages from what the event log says happened.

    The first stage is the denominator for ``share_of_first``; each later stage also reports
    ``step_rate`` against the stage above it, because "40% of applications became interviews"
    and "50% of replies became interviews" are different stories and a funnel that shows only
    one of them invites the wrong conclusion.
    """
    stages = [
        _Stage(
            key="applications",
            label="投递",
            basis="曾离开 wishlist 的卡片（来自事件流，不是当前状态）",
        ),
        _Stage(
            key="replies",
            label="有回复",
            basis="曾进入 oa/interview/final/offer，或投递后被拒（被拒也是回复）",
        ),
        _Stage(
            key="interviews",
            label="面试",
            basis="曾进入 interview/final/offer",
        ),
        _Stage(key="finals", label="终面", basis="曾进入 final/offer"),
        _Stage(key="offers", label="Offer", basis="曾进入 offer"),
    ]

    for record in records:
        if not record.was_applied:
            continue
        stages[0].members.append(record)
        if record.reached(_REPLY_STATUSES) or record.was_rejected:
            stages[1].members.append(record)
        if record.reached(_INTERVIEW_STATUSES):
            stages[2].members.append(record)
        if record.reached(_FINAL_STATUSES):
            stages[3].members.append(record)
        if record.reached(_OFFER_STATUSES):
            stages[4].members.append(record)

    first = len(stages[0].members)
    out: list[FunnelStage] = []
    previous = first
    for index, stage in enumerate(stages):
        count = len(stage.members)
        # ``None`` when the stage above is empty: there is no conversion to report, and both
        # 0.0 and 1.0 would be claims about a set with nothing in it.
        if index == 0:
            step: float | None = 1.0
        elif previous == 0:
            step = None
        else:
            step = count / previous
        out.append(
            FunnelStage(
                key=stage.key,
                label=stage.label,
                count=count,
                share_of_first=(count / first) if first else 0.0,
                step_rate=step,
                basis=stage.basis,
            )
        )
        previous = count
    return out


def compute_rates(records: Sequence[ApplicationRecord], *, cohort: FunnelCohort) -> list[RateCard]:
    """The four headline numbers (FR-14.2), each with its counts and interval.

    ``averageMatchScore`` is reported as a rate-shaped card so every card on the page has the
    same anatomy — but its denominator is the cards *that have a score*, and its definition
    says so. Mixing "average over 12" with "average over 5" without saying which is how a
    dashboard lies without a single wrong number in it.
    """
    applied = [record for record in records if record.was_applied]
    total = len(applied)
    replies = sum(1 for r in applied if r.reached(_REPLY_STATUSES) or r.was_rejected)
    interviews = sum(1 for r in applied if r.reached(_INTERVIEW_STATUSES))
    offers = sum(1 for r in applied if r.reached(_OFFER_STATUSES))

    scored = [record for record in applied if record.match_score is not None]
    average_match = mean_or_none(record.match_score for record in scored)
    match_denominator = len(scored)

    def card(key: str, label: str, successes: int, denominator: int, definition: str) -> RateCard:
        low, high = wilson_interval(successes, denominator)
        return RateCard(
            key=key,
            label=label,
            rate=(successes / denominator) if denominator else None,
            numerator=successes,
            denominator=denominator,
            sufficient=sample_is_sufficient(denominator),
            interval_low=low,
            interval_high=high,
            definition=definition,
        )

    return [
        card(
            "responseRate",
            "Response Rate",
            replies,
            total,
            f"有回复的投递 ÷ 全部投递（分母：本区间内投出 {total} 次）",
        ),
        card(
            "interviewRate",
            "Interview Rate",
            interviews,
            total,
            f"进入面试的投递 ÷ 全部投递（分母：本区间内投出 {total} 次）",
        ),
        card(
            "offerRate",
            "Offer Rate",
            offers,
            total,
            f"拿到 Offer 的投递 ÷ 全部投递（分母：本区间内投出 {total} 次）",
        ),
        RateCard(
            key="averageMatchScore",
            label="Avg Match Score",
            # A score out of 100 is normalised to the same 0–1 scale the other cards use, and
            # the definition says which denominator produced it. ``None`` when no card in the
            # cohort has ever been matched.
            rate=((average_match / 100.0) if average_match is not None else None),
            numerator=round(average_match) if average_match is not None else 0,
            denominator=match_denominator,
            sufficient=sample_is_sufficient(match_denominator),
            interval_low=0.0,
            interval_high=0.0,
            definition=(
                "本区间内已评分卡片的平均匹配分 ÷ 100"
                f"（分母：{match_denominator} 张有分数的卡片；未评分的卡片不计入，也不按 0 计）"
            ),
        ),
        RateCard(
            key="cohortSize",
            label="Cohort",
            # Not a rate at all: the cohort size is the denominator of everything else on the
            # page, shown as a card so the reader sees how much evidence the page rests on.
            rate=None,
            numerator=cohort.applications,
            denominator=cohort.applications,
            sufficient=sample_is_sufficient(cohort.applications),
            interval_low=0.0,
            interval_high=1.0,
            definition=f"本区间内创建的卡片数（含 wishlist）：{cohort.applications}",
        ),
    ]


#: Re-exported so callers do not have to import the stats module for the policy constant.
MINIMUM_SAMPLE = MIN_SAMPLE
