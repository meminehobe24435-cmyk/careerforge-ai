"""Does having a skill correlate with getting interviews? And which role families work out?

This is the module where a career product most easily starts lying. With a handful of
applications, *every* skill correlates with something, and the difference between "this is
worth learning" and "this is noise" is entirely in the sample sizes — which is why both groups
are always reported, the comparison is refused below the minimum, and the note explaining what
the number is worth is part of the payload rather than a disclaimer in a footnote.

The questions the two functions answer:

* :func:`skill_correlation` — among the applications in the cohort, do the ones whose posting
  *required* this skill reach interviews more often than the ones whose posting did not? The
  comparison group is what makes it a finding instead of a number.
* :func:`category_performance` — how did each role family do? A category comes from the
  posting's required skills (their taxonomy category, weighted), so it is derived from data
  rather than from a label somebody typed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence

from careerforge_ai.analytics.funnel import ApplicationRecord
from careerforge_ai.analytics.stats import (
    MIN_SAMPLE,
    compare_groups,
    sample_is_sufficient,
)
from careerforge_ai.schemas.analytics import CategoryPerformance, SkillCorrelation

__all__ = ["category_performance", "skill_correlation"]

_INTERVIEW_STATUSES: tuple[str, ...] = ("interview", "final", "offer")


def skill_correlation(
    records: Sequence[ApplicationRecord],
    *,
    display_names: dict[str, str] | None = None,
    minimum: int = MIN_SAMPLE,
    limit: int = 12,
) -> list[SkillCorrelation]:
    """Per-skill interview comparison across the cohort, strongest lift first.

    Only skills that appear on *both* sides of the split can produce a comparison. A skill
    every posting asked for has no "without" group, and reporting its rate against an empty
    group would manufacture a difference out of nothing — those rows are returned with zeros
    and ``sufficient=False`` so the UI can say why they are not usable.
    """
    applied = [record for record in records if record.was_applied]
    if not applied:
        return []

    names = display_names or {}
    totals: Counter[str] = Counter()
    with_skill: Counter[str] = Counter()
    without_skill: Counter[str] = Counter()
    interviews_with: Counter[str] = Counter()
    interviews_without: Counter[str] = Counter()

    for record in applied:
        interviewed = record.reached(_INTERVIEW_STATUSES)
        for skill in set(record.required_skills):
            totals[skill] += 1
            if interviewed:
                interviews_with[skill] += 1
    total_interviewed = sum(1 for record in applied if record.reached(_INTERVIEW_STATUSES))
    for skill in totals:
        with_skill[skill] = totals[skill]
        without_skill[skill] = len(applied) - totals[skill]
        interviews_without[skill] = total_interviewed - interviews_with[skill]

    rows: list[SkillCorrelation] = []
    for skill in totals:
        comparison = compare_groups(
            successes_a=interviews_with[skill],
            total_a=with_skill[skill],
            successes_b=interviews_without[skill],
            total_b=without_skill[skill],
            minimum=minimum,
        )
        rows.append(
            SkillCorrelation(
                skill_id=skill,
                display_name=names.get(skill, skill),
                with_skill_total=with_skill[skill],
                with_skill_successes=interviews_with[skill],
                with_skill_rate=round(comparison.rate_a, 4),
                without_skill_total=without_skill[skill],
                without_skill_successes=interviews_without[skill],
                without_skill_rate=round(comparison.rate_b, 4),
                lift=round(comparison.lift, 4),
                sufficient=comparison.sufficient,
                notable=comparison.notable,
                note=comparison.note,
            )
        )

    # Notable findings first, then by how much evidence sits behind them, then by lift:
    # a page that leads with the most surprising number regardless of sample size is a page
    # that leads with noise.
    rows.sort(
        key=lambda row: (
            not row.notable,
            -min(row.with_skill_total, row.without_skill_total),
            -abs(row.lift),
            row.skill_id,
        )
    )
    return rows[:limit]


def category_performance(
    records: Sequence[ApplicationRecord], *, minimum: int = MIN_SAMPLE
) -> list[CategoryPerformance]:
    """Per role-family record, most applications first.

    A card with no category (no linked posting, or a posting whose skills the taxonomy could
    not resolve) is reported as ``unknown`` rather than dropped: quietly excluding it would
    make the categories add up to more applications than the funnel counted.
    """
    applied = [record for record in records if record.was_applied]
    grouped: dict[str, list[ApplicationRecord]] = defaultdict(list)
    for record in applied:
        grouped[record.category or "unknown"].append(record)

    rows: list[CategoryPerformance] = []
    for category, members in grouped.items():
        interviews = sum(1 for record in members if record.reached(_INTERVIEW_STATUSES))
        offers = sum(1 for record in members if "offer" in record.statuses_seen)
        scores = [record.match_score for record in members if record.match_score is not None]
        average = (sum(scores) / len(scores)) if scores else None
        rows.append(
            CategoryPerformance(
                category=category,
                applications=len(members),
                interviews=interviews,
                offers=offers,
                interview_rate=(interviews / len(members)) if members else 0.0,
                average_match_score=round(average, 2) if average is not None else None,
                sufficient=sample_is_sufficient(len(members), minimum=minimum),
            )
        )

    rows.sort(key=lambda row: (-row.applications, row.category))
    return rows
