"""Statistics with the honesty rules built in.

Everything here exists because of one failure mode: a rate printed without its sample size
reads as a fact. "面试成功率 67%" from three applications is noise wearing a number's
clothes, and this project's whole premise is that a number must be checkable.

So the primitives below refuse to produce a bare ratio:

* :func:`wilson_interval` returns the 95% interval beside the point estimate, because with
  small samples the interval is the honest part — at n=5 and 3 successes the interval spans
  roughly 23%–88%, and a reader who sees that will not act on the number alone.
* :func:`sample_is_sufficient` applies the documented minimum (``MIN_SAMPLE``), and every
  caller is expected to pass the verdict on to its response rather than to hide the number.
* :func:`compare_groups` only calls a difference *notable* when both groups clear the minimum
  **and** their intervals do not overlap. Overlap is a weak test — it is not a p-value — and
  that is stated in the returned note rather than implied to be more than it is.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import math

__all__ = [
    "MIN_SAMPLE",
    "Comparison",
    "mean_or_none",
    "sample_is_sufficient",
    "wilson_interval",
    "compare_groups",
]

#: Below this many observations, a rate is reported but marked insufficient.
#: Five is not statistically meaningful — it is the point at which a single outcome stops
#: being able to swing the rate by 20 points, and the UI says "样本不足，仅供参考" below it.
MIN_SAMPLE = 5

#: 95% two-sided normal quantile, for the Wilson score interval.
_Z = 1.959963984540054


def wilson_interval(successes: int, total: int, *, z: float = _Z) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion.

    Wilson rather than the textbook normal approximation because it stays inside [0, 1] and
    remains sane at the sample sizes this product actually sees — the normal interval reports
    impossible bounds (below 0, or above 1) exactly where a small-n product lives.
    """
    if total <= 0:
        return (0.0, 0.0)
    if successes < 0 or successes > total:
        raise ValueError("successes must be within [0, total]")
    phat = successes / total
    denominator = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = (z / denominator) * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total))
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def sample_is_sufficient(total: int, *, minimum: int = MIN_SAMPLE) -> bool:
    """Whether a rate from ``total`` observations may be presented as a rate."""
    return total >= minimum


def mean_or_none(values: Iterable[float | None]) -> float | None:
    """Arithmetic mean over the values that exist; ``None`` when nothing does.

    ``None`` rather than ``0.0``: "we never recorded a match score" and "the average match
    score is zero" are different statements, and only one of them is knowable.
    """
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


class Comparison:
    """Two groups' rates, with the evidence that they differ — or the lack of it."""

    __slots__ = ("notable", "note", "rate_a", "rate_b", "sufficient")

    def __init__(self, *, rate_a: float, rate_b: float, sufficient: bool, notable: bool, note: str):
        self.rate_a = rate_a
        self.rate_b = rate_b
        self.sufficient = sufficient
        self.notable = notable
        self.note = note

    @property
    def lift(self) -> float:
        """Difference in rates (group A minus group B). Signed: a negative lift is a finding."""
        return self.rate_a - self.rate_b


def compare_groups(
    *,
    successes_a: int,
    total_a: int,
    successes_b: int,
    total_b: int,
    minimum: int = MIN_SAMPLE,
) -> Comparison:
    """Compare two proportions and say how much the comparison is worth.

    Returns a :class:`Comparison` whose ``note`` is written to be shown to the candidate
    verbatim, including when the honest answer is "this tells you nothing".
    """
    rate_a = successes_a / total_a if total_a else 0.0
    rate_b = successes_b / total_b if total_b else 0.0
    sufficient = sample_is_sufficient(total_a, minimum=minimum) and sample_is_sufficient(
        total_b, minimum=minimum
    )
    if not sufficient:
        return Comparison(
            rate_a=rate_a,
            rate_b=rate_b,
            sufficient=False,
            notable=False,
            note=(f"样本不足（{total_a} vs {total_b}，各需 ≥ {minimum} 条），差距不可作为结论"),
        )

    low_a, high_a = wilson_interval(successes_a, total_a)
    low_b, high_b = wilson_interval(successes_b, total_b)
    overlaps = low_a <= high_b and low_b <= high_a
    if overlaps:
        return Comparison(
            rate_a=rate_a,
            rate_b=rate_b,
            sufficient=True,
            notable=False,
            note=("两组的 95% 区间重叠，差异不显著——这是提示而非结论"),
        )
    return Comparison(
        rate_a=rate_a,
        rate_b=rate_b,
        sufficient=True,
        notable=True,
        note="两组的 95% 区间不重叠；相关不等于因果，样本仍可能偏小",
    )


def stage_reached(statuses_seen: Sequence[str], targets: Sequence[str]) -> bool:
    """Whether any of ``targets`` appears in a card's observed status history."""
    seen = set(statuses_seen)
    return any(target in seen for target in targets)
