"""The activity trend and the milestone feed.

Two different questions, one window each — and the difference matters enough to state in both
responses:

* the **funnel** filters applications by creation time (a cohort: "of what I started in this
  period, how far did it get");
* the **timeline** filters *events* by when they happened ("what did I do in this period").

Using one window for both would mean a milestone reached today is invisible in the 7-day view
because the application it belongs to is three months old.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime, timedelta

from careerforge_ai.analytics.funnel import RANGE_DAYS
from careerforge_ai.schemas.analytics import TimelineBucket, TimelineEntry

__all__ = ["month_key", "monthly_buckets", "recent_entries"]


def month_key(moment: datetime) -> str:
    """``YYYY-MM`` in UTC — the trend chart's x-axis unit."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m")


def monthly_buckets(
    entries: Iterable[TimelineEntry], *, range_key: str, now: datetime, months: int = 12
) -> list[TimelineBucket]:
    """Applications / interviews / offers per month, oldest first, gaps filled with zeros.

    Empty months are included: a line chart that skips them compresses three idle months into
    no distance at all, which is the opposite of what a trend is for.
    """
    days = RANGE_DAYS.get(range_key) if range_key in RANGE_DAYS else None
    from_at = None if range_key == "all" else now - timedelta(days=days or 90)

    counts: dict[str, dict[str, int]] = {}
    for entry in entries:
        if from_at is not None and _as_utc(entry.occurred_at) < from_at:
            continue
        bucket = counts.setdefault(
            month_key(entry.occurred_at), {"applications": 0, "interviews": 0, "offers": 0}
        )
        if entry.kind == "application":
            bucket["applications"] += 1
        elif entry.kind == "interview":
            bucket["interviews"] += 1
        elif entry.kind == "offer":
            bucket["offers"] += 1

    keys = _month_span(now=now, months=months, extra=counts.keys())
    return [
        TimelineBucket(
            month=key, **counts.get(key, {"applications": 0, "interviews": 0, "offers": 0})
        )
        for key in keys
    ]


def recent_entries(
    entries: Sequence[TimelineEntry], *, range_key: str, now: datetime, limit: int = 50
) -> list[TimelineEntry]:
    """Newest first, filtered by when each milestone happened."""
    days = RANGE_DAYS.get(range_key) if range_key in RANGE_DAYS else None
    from_at = None if range_key == "all" else now - timedelta(days=days or 90)
    selected = [
        entry for entry in entries if from_at is None or _as_utc(entry.occurred_at) >= from_at
    ]
    selected.sort(key=lambda entry: _as_utc(entry.occurred_at), reverse=True)
    return selected[:limit]


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _month_span(*, now: datetime, months: int, extra: Iterable[str]) -> list[str]:
    """The last ``months`` month keys, extended backwards to cover the data.

    The extension walks **forwards** from the earliest month present up to the start of the
    default window. Walking backwards from the earliest month — the obvious way to write it —
    never terminates, because every earlier month is also less than the window's first key;
    that version spun until the process was killed. ``max_extension`` bounds it as a second
    line of defence: a decade of history is not a chart, and a loop with no exit is worse than
    a chart with a clipped range.
    """
    keys: list[str] = []
    year, month = now.astimezone(UTC).year, now.astimezone(UTC).month
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    keys.reverse()

    earliest = min(extra, default=keys[0])
    if earliest >= keys[0]:
        return keys

    max_extension = 60
    extension: list[str] = []
    year, month = int(earliest[:4]), int(earliest[5:7])
    while f"{year:04d}-{month:02d}" < keys[0] and len(extension) < max_extension:
        extension.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return extension + keys
