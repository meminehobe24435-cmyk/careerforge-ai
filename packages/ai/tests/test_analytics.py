"""The analytics engine: the funnel, the rates, the correlation, the trend.

The interesting cases are the boundaries, not the happy path — an empty cohort, one
application, every card rejected, a skill every posting required (so there is no comparison
group), and a month with no activity. Those are the shapes a real account passes through in its
first weeks, and they are where a naive implementation prints a confident number about nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from careerforge_ai.analytics import (
    MIN_SAMPLE,
    ApplicationRecord,
    build_funnel,
    category_performance,
    cohort_window,
    compute_rates,
    monthly_buckets,
    recent_entries,
    skill_correlation,
    wilson_interval,
)
from careerforge_ai.analytics.timeline import month_key
from careerforge_ai.schemas.analytics import TimelineEntry

NOW = datetime(2026, 3, 15, 12, 0, tzinfo=UTC)


def record(
    app_id: str,
    *,
    statuses: tuple[str, ...],
    days_ago: int = 1,
    score: float | None = None,
    skills: tuple[str, ...] = (),
    category: str | None = None,
) -> ApplicationRecord:
    return ApplicationRecord(
        id=app_id,
        created_at=NOW - timedelta(days=days_ago),
        statuses_seen=frozenset({"wishlist", *statuses}),
        match_score=score,
        required_skills=skills,
        category=category,
    )


# ── the funnel ────────────────────────────────────────────────────────────────


def test_a_rejected_card_was_still_interviewed() -> None:
    """The distinction the whole funnel rests on: the board says ``rejected``, the history says
    "reached an interview". Counting current status would erase every outcome that ended."""
    records = [
        record("a", statuses=("applied", "interview", "rejected")),
        record("b", statuses=("applied", "rejected")),
    ]
    stages = {stage.key: stage for stage in build_funnel(records)}
    assert stages["applications"].count == 2
    assert stages["replies"].count == 2, "a rejection is a reply, not silence"
    assert stages["interviews"].count == 1
    assert stages["offers"].count == 0


def test_a_wishlist_card_is_not_an_application() -> None:
    records = [record("a", statuses=()), record("b", statuses=("applied",))]
    stages = {stage.key: stage for stage in build_funnel(records)}
    assert stages["applications"].count == 1
    assert stages["applications"].step_rate == 1.0
    assert stages["replies"].count == 0


def test_the_step_rate_is_undefined_rather_than_perfect_when_the_stage_above_is_empty() -> None:
    """0 offers out of 0 final rounds is not a 100% conversion.

    The distinction between the two assertions below is the whole point: a step rate's
    denominator is the stage *above it*, so "no replies out of one application" is a real
    zero while "no offers out of no final rounds" has nothing to divide by.
    """
    records = [record("a", statuses=("applied",))]
    stages = {stage.key: stage for stage in build_funnel(records)}

    assert stages["applications"].count == 1
    assert stages["replies"].step_rate == 0.0, "one application, no replies — a real zero"
    assert stages["interviews"].step_rate is None, "0 replies is not a denominator"
    assert stages["finals"].step_rate is None
    assert stages["offers"].step_rate is None


def test_share_is_of_the_first_stage_and_step_is_of_the_previous() -> None:
    """Two different denominators on purpose: a funnel that shows only one of them invites the
    wrong conclusion ("40% of applications become interviews" and "50% of replies become
    interviews" are both true of the same four applications)."""
    records = [
        record("a", statuses=("applied", "interview", "final", "offer")),
        record("b", statuses=("applied", "interview", "final")),
        record("c", statuses=("applied",)),
        record("d", statuses=("applied",)),
    ]
    stages = {stage.key: stage for stage in build_funnel(records)}

    assert stages["applications"].count == 4
    assert stages["replies"].count == 2, "only a and b were ever replied to"
    assert stages["interviews"].count == 2
    assert stages["finals"].count == 2

    assert stages["interviews"].share_of_first == pytest.approx(0.5)
    assert stages["interviews"].step_rate == pytest.approx(1.0), "both replies became interviews"
    assert stages["finals"].step_rate == pytest.approx(1.0), "both interviews reached a final"
    assert stages["offers"].share_of_first == pytest.approx(0.25)
    assert stages["offers"].step_rate == pytest.approx(0.5), "one of the two finals converted"


def test_an_empty_cohort_produces_zeros_and_no_division_by_zero() -> None:
    stages = build_funnel([])
    assert [stage.count for stage in stages] == [0, 0, 0, 0, 0]
    assert all(stage.share_of_first == 0.0 for stage in stages)
    assert stages[0].step_rate == 1.0
    assert all(stage.step_rate is None for stage in stages[1:])


def test_every_stage_ships_the_basis_it_was_counted_from() -> None:
    for stage in build_funnel([record("a", statuses=("applied",))]):
        assert stage.basis.strip(), f"{stage.key} has no stated basis"


# ── the cohort window ─────────────────────────────────────────────────────────


def test_the_window_filters_by_creation_time() -> None:
    records = [
        record("recent", statuses=("applied",), days_ago=3),
        record("old", statuses=("applied", "interview"), days_ago=40),
    ]
    cohort, selected = cohort_window(range_key="7d", now=NOW, records=records)
    assert cohort.applications == 1
    assert [item.id for item in selected] == ["recent"]
    assert cohort.from_at == NOW - timedelta(days=7)

    everything, all_selected = cohort_window(range_key="all", now=NOW, records=records)
    assert everything.applications == 2
    assert everything.from_at is None, "'all' states its boundlessness instead of hiding it"
    assert len(all_selected) == 2


def test_the_window_is_a_cohort_not_an_event_filter() -> None:
    """An application started 40 days ago that reached an interview yesterday is outside the
    7-day cohort — and correctly so: the funnel asks how far *this period's* applications got."""
    records = [record("old-but-active", statuses=("applied", "interview"), days_ago=40)]
    cohort, selected = cohort_window(range_key="7d", now=NOW, records=records)
    assert cohort.applications == 0
    assert selected == []


def test_an_unknown_range_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown range"):
        cohort_window(range_key="1y", now=NOW, records=[])


# ── the rates ─────────────────────────────────────────────────────────────────


def test_rates_carry_their_counts_and_their_verdict() -> None:
    records = [
        record("a", statuses=("applied", "interview"), score=80.0),
        record("b", statuses=("applied", "rejected"), score=60.0),
    ]
    cohort, selected = cohort_window(range_key="all", now=NOW, records=records)
    cards = {card.key: card for card in compute_rates(selected, cohort=cohort)}

    interview = cards["interviewRate"]
    assert interview.numerator == 1
    assert interview.denominator == 2
    assert interview.rate == pytest.approx(0.5)
    assert interview.sufficient is False, "two applications is not a rate"
    assert interview.interval_low < 0.5 < interview.interval_high

    assert cards["responseRate"].rate == pytest.approx(1.0)
    assert cards["offerRate"].rate == pytest.approx(0.0)
    assert cards["averageMatchScore"].rate == pytest.approx(0.7)
    assert cards["averageMatchScore"].denominator == 2
    for card in cards.values():
        assert card.definition.strip(), f"{card.key} has no stated definition"


def test_an_empty_cohort_reports_no_rate_rather_than_a_zero() -> None:
    cohort, selected = cohort_window(range_key="30d", now=NOW, records=[])
    cards = {card.key: card for card in compute_rates(selected, cohort=cohort)}
    assert cards["interviewRate"].rate is None
    assert cards["interviewRate"].denominator == 0
    assert cards["averageMatchScore"].rate is None
    assert cards["cohortSize"].rate is None


def test_unscored_cards_are_excluded_from_the_match_average_not_counted_as_zero() -> None:
    records = [
        record("scored", statuses=("applied",), score=90.0),
        record("unscored", statuses=("applied",)),
    ]
    cohort, selected = cohort_window(range_key="all", now=NOW, records=records)
    cards = {card.key: card for card in compute_rates(selected, cohort=cohort)}
    assert cards["averageMatchScore"].denominator == 1
    assert cards["averageMatchScore"].rate == pytest.approx(0.9)


def test_a_rate_of_one_from_one_application_is_still_flagged_insufficient() -> None:
    records = [record("a", statuses=("applied", "interview", "offer"))]
    cohort, selected = cohort_window(range_key="all", now=NOW, records=records)
    cards = {card.key: card for card in compute_rates(selected, cohort=cohort)}
    assert cards["offerRate"].rate == pytest.approx(1.0)
    assert cards["offerRate"].sufficient is False
    assert cards["offerRate"].interval_low < 0.3, "the interval admits how little is known"


# ── the correlation ───────────────────────────────────────────────────────────


def test_a_skill_that_helped_and_one_that_did_not() -> None:
    records = []
    # 6 applications requiring STM32, 5 of which reached an interview.
    for index in range(6):
        records.append(
            record(
                f"stm32-{index}",
                statuses=("applied", "interview") if index < 5 else ("applied",),
                skills=("stm32",),
            )
        )
    # 6 applications not requiring it, none of which did.
    for index in range(6):
        records.append(record(f"other-{index}", statuses=("applied",), skills=("python",)))

    rows = {row.skill_id: row for row in skill_correlation(records)}

    stm32 = rows["stm32"]
    assert (stm32.with_skill_total, stm32.with_skill_successes) == (6, 5)
    assert (stm32.without_skill_total, stm32.without_skill_successes) == (6, 0)
    # The payload rounds rates to four decimals so a JSON response is stable; compare at that
    # precision rather than at the exactly representable fraction.
    assert stm32.lift == pytest.approx(5 / 6, abs=1e-4)
    assert stm32.notable is True, "0/6 against 5/6 is a real gap, and the intervals agree"
    assert "因果" in stm32.note, "the note must not let a correlation read as causation"

    # The negative side of the same split: python appears only in the failures.
    python = rows["python"]
    assert python.lift == pytest.approx(-5 / 6, abs=1e-4)
    assert python.notable is True, "the comparison is symmetric; a negative lift is a finding"


def test_a_gap_too_small_to_read_is_not_called_a_finding() -> None:
    """The case the correlation table must not shout about: two groups that look different
    (one interview more) but whose intervals overlap."""
    records = [
        record(
            f"a{index}",
            statuses=("applied", "interview") if index < 3 else ("applied",),
            skills=("stm32",),
        )
        for index in range(6)
    ] + [
        record(
            f"b{index}",
            statuses=("applied", "interview") if index < 2 else ("applied",),
            skills=("python",),
        )
        for index in range(6)
    ]
    rows = {row.skill_id: row for row in skill_correlation(records)}

    stm32 = rows["stm32"]
    assert stm32.with_skill_rate == pytest.approx(0.5, abs=1e-4)
    assert stm32.without_skill_rate == pytest.approx(1 / 3, abs=1e-4)
    assert stm32.sufficient is True, "both groups clear the minimum"
    assert stm32.notable is False, "3/6 against 2/6 does not support a claim"
    assert "重叠" in stm32.note


def test_a_skill_that_splits_the_cohort_into_one_group_is_refused() -> None:
    """Every posting asked for it, so there is no comparison group — and no finding."""
    records = [
        record(f"a{index}", statuses=("applied", "interview"), skills=("stm32",))
        for index in range(6)
    ]
    rows = {row.skill_id: row for row in skill_correlation(records)}
    assert rows["stm32"].without_skill_total == 0
    assert rows["stm32"].sufficient is False
    assert rows["stm32"].notable is False
    assert "样本不足" in rows["stm32"].note


def test_correlation_ignores_cards_that_never_applied() -> None:
    records = [
        record("a", statuses=("applied", "interview"), skills=("stm32",)),
        *[record(f"w{index}", statuses=(), skills=("stm32",)) for index in range(10)],
    ]
    rows = {row.skill_id: row for row in skill_correlation(records)}
    assert rows["stm32"].with_skill_total == 1, "wishlist bookmarks are not evidence of anything"


def test_correlation_needs_a_cohort() -> None:
    assert skill_correlation([]) == []


def test_small_samples_are_never_notable() -> None:
    records = [
        record(f"a{index}", statuses=("applied", "interview"), skills=("stm32",))
        for index in range(MIN_SAMPLE - 1)
    ] + [
        record(f"b{index}", statuses=("applied",), skills=("python",))
        for index in range(MIN_SAMPLE - 1)
    ]
    rows = {row.skill_id: row for row in skill_correlation(records)}
    assert rows["stm32"].notable is False
    assert rows["stm32"].sufficient is False


# ── the categories ────────────────────────────────────────────────────────────


def test_categories_report_their_own_denominator() -> None:
    records = [
        record("a", statuses=("applied", "interview", "offer"), category="embedded", score=80.0),
        record("b", statuses=("applied",), category="embedded", score=60.0),
        record("c", statuses=("applied", "interview"), category="backend", score=70.0),
        record("d", statuses=("applied",), category=None),
    ]
    rows = {row.category: row for row in category_performance(records)}
    assert rows["embedded"].applications == 2
    assert rows["embedded"].interviews == 1
    assert rows["embedded"].interview_rate == pytest.approx(0.5)
    assert rows["embedded"].average_match_score == pytest.approx(70.0)
    assert rows["embedded"].sufficient is False
    # An unclassified card is reported, not dropped: dropping it would make the categories
    # add up to fewer applications than the funnel counted.
    assert rows["unknown"].applications == 1


def test_categories_are_ordered_by_how_much_they_rest_on() -> None:
    records = [
        record(f"a{index}", statuses=("applied",), category="embedded") for index in range(3)
    ] + [record("b", statuses=("applied",), category="backend")]
    assert [row.category for row in category_performance(records)] == ["embedded", "backend"]


# ── the timeline ──────────────────────────────────────────────────────────────


def entry(kind: str, *, days_ago: int, title: str = "x") -> TimelineEntry:
    return TimelineEntry(kind=kind, title=title, occurred_at=NOW - timedelta(days=days_ago))


def test_the_trend_fills_empty_months_so_distance_stays_honest() -> None:
    entries = [entry("application", days_ago=1), entry("interview", days_ago=40)]
    buckets = monthly_buckets(entries, range_key="all", now=NOW, months=3)
    assert [bucket.month for bucket in buckets] == ["2026-01", "2026-02", "2026-03"]
    assert buckets[-1].applications == 1
    assert buckets[-2].interviews == 1
    assert buckets[0].applications == 0, "an idle month is shown as an idle month"


def test_the_trend_extends_back_to_cover_older_data() -> None:
    buckets = monthly_buckets(
        [entry("application", days_ago=200)], range_key="all", now=NOW, months=3
    )
    assert buckets[0].month < "2026-01"
    assert sum(bucket.applications for bucket in buckets) == 1


def test_the_feed_filters_by_when_things_happened_not_by_cohort() -> None:
    entries = [entry("application", days_ago=1), entry("interview", days_ago=40)]
    recent = recent_entries(entries, range_key="7d", now=NOW)
    assert len(recent) == 1, "a milestone reached this week belongs in this week's view"
    assert len(recent_entries(entries, range_key="all", now=NOW)) == 2


def test_month_key_normalises_naive_timestamps() -> None:
    assert month_key(datetime(2026, 3, 15, 12, 0)) == "2026-03"


# ── the interval primitive ────────────────────────────────────────────────────


def test_wilson_interval_stays_inside_zero_and_one() -> None:
    for successes, total in ((0, 1), (1, 1), (0, 5), (5, 5), (3, 5), (0, 0)):
        low, high = wilson_interval(successes, total)
        assert 0.0 <= low <= high <= 1.0, (successes, total, low, high)


def test_wilson_interval_narrows_as_evidence_accumulates() -> None:
    narrow = wilson_interval(50, 100)
    wide = wilson_interval(1, 2)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_wilson_interval_refuses_impossible_counts() -> None:
    with pytest.raises(ValueError):
        wilson_interval(3, 2)
