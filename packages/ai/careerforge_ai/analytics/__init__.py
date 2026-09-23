"""Deterministic career analytics: the funnel, the rates and the correlation.

**No model produces a number in this package.** Every figure here is arithmetic over rows the
candidate's own activity created (``applications``, ``application_events``, ``career_events``,
``job_skills``), which is the same rule the match score and the evidence confidence follow: an
LLM may narrate a number it was given, never invent one.

The package is pure — no I/O, no ORM, no framework (ADR-022) — so the statistics can be tested
at their boundaries (empty cohort, one application, every card rejected) and reused by the API,
the eval harness and the test suite without a second implementation.

Two habits run through it:

* **a rate never travels alone** — it carries its counts, its 95% interval and whether the
  sample clears the documented minimum;
* **the basis of every stage is in the response** — a number whose definition is implicit is a
  number nobody can check, which is the failure this whole project exists to argue against.
"""

from __future__ import annotations

from careerforge_ai.analytics.correlation import category_performance, skill_correlation
from careerforge_ai.analytics.funnel import (
    RANGE_DAYS,
    ApplicationRecord,
    build_funnel,
    cohort_window,
    compute_rates,
)
from careerforge_ai.analytics.stats import MIN_SAMPLE, Comparison, compare_groups, wilson_interval
from careerforge_ai.analytics.timeline import month_key, monthly_buckets, recent_entries

__all__ = [
    "MIN_SAMPLE",
    "RANGE_DAYS",
    "ApplicationRecord",
    "Comparison",
    "build_funnel",
    "category_performance",
    "cohort_window",
    "compare_groups",
    "compute_rates",
    "month_key",
    "monthly_buckets",
    "recent_entries",
    "skill_correlation",
    "wilson_interval",
]
