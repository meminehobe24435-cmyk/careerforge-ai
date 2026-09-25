"""Compare two evaluation reports and say what moved.

The point of a benchmark is not the number, it is the *diff*: a metric that went from 0.88 to 0.83
between two commits is a regression somebody must explain, and one that went the other way is worth
knowing about before claiming an improvement.

Usage::

    python evals/compare.py reports/baseline-eval-report.json reports/eval-report.json
    python evals/compare.py baseline.json current.json --tolerance 0.02 --json

Rules:

* **Direction is declared, not assumed.** For most metrics higher is better; for rates that describe
  an error (``unsafe_support_rate``, ``leakage_rate``, ``over_support_rate``) and for calibration
  error (``ECE``, ``Brier``) lower is better. Guessing "higher is better" would report a fix as a
  regression, so the direction is derived from the metric name and can be overridden.
* **A missing metric is not a zero.** It is reported as ``missing`` and never counted as a
  regression: a suite that stopped running is a different problem from a metric that fell.
* **Tolerance is explicit** so float noise does not read as a finding.
* A metric that regressed in a **gated** direction exits non-zero, so a scheduled job can fail on
  it; reported-only metrics are printed and do not.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Metrics where a *lower* value is better. Matched as substrings of the metric name, so
#: `jd.distractor_leakage_rate` and `interview.forbidden_leakage_rate` are both covered.
LOWER_IS_BETTER = (
    "_rate",
    "_leakage",
    "error",
    "ece",
    "brier",
    "latency",
    "duration",
)
#: Exceptions to the rule above: these are *good* rates despite the name.
HIGHER_IS_BETTER_EXCEPTIONS = ("rejection_rate", "recall", "hit_rate", "coverage", "accuracy")


@dataclass
class Comparison:
    suite: str
    metric: str
    baseline: float | None
    current: float | None
    delta: float | None
    direction: str
    verdict: str
    severity: str = "report"

    def line(self) -> str:
        if self.verdict == "missing":
            return f"  {self.metric:44s} {'—':>10s} {'—':>10s}  {self.verdict}"
        assert self.baseline is not None and self.current is not None and self.delta is not None
        arrow = "+" if self.delta > 0 else ""
        return (
            f"  {self.metric:44s} {self.baseline:>10.4f} {self.current:>10.4f}  "
            f"{arrow}{self.delta:.4f}  {self.verdict.upper()}"
            + ("  (gate)" if self.severity == "gate" else "")
        )


def direction_of(metric: str) -> str:
    """``"lower"`` when a smaller value is a better system, else ``"higher"``."""
    name = metric.lower()
    if any(token in name for token in HIGHER_IS_BETTER_EXCEPTIONS):
        return "higher"
    if any(token in name for token in LOWER_IS_BETTER):
        return "lower"
    return "higher"


def compare(
    baseline: dict[str, Any], current: dict[str, Any], *, tolerance: float = 0.0
) -> list[Comparison]:
    if baseline.get("schema_version") != current.get("schema_version"):
        raise SystemExit(
            "refusing to compare reports with different schema versions "
            f"({baseline.get('schema_version')} vs {current.get('schema_version')}): the field "
            "names may mean different things, and a confident wrong diff is worse than none"
        )

    rows: list[Comparison] = []
    suites = sorted(set(baseline.get("suites", {})) | set(current.get("suites", {})))
    for suite in suites:
        before = baseline.get("suites", {}).get(suite, {})
        after = current.get("suites", {}).get(suite, {})
        metrics = sorted(set(before.get("metrics", {})) | set(after.get("metrics", {})))
        for metric in metrics:
            old = before.get("metrics", {}).get(metric)
            new = after.get("metrics", {}).get(metric)
            if old is None or new is None:
                rows.append(
                    Comparison(suite, metric, old, new, None, direction_of(metric), "missing")
                )
                continue
            delta = round(new - old, 6)
            direction = direction_of(metric)
            if abs(delta) <= tolerance:
                verdict = "same"
            elif (delta > 0) == (direction == "higher"):
                verdict = "improved"
            else:
                verdict = "regressed"
            severity = "report"
            thresholds = after.get("thresholds", {})
            if metric in thresholds:
                severity = str(thresholds[metric].get("severity", "report"))
            rows.append(Comparison(suite, metric, old, new, delta, direction, verdict, severity))
    return rows


def _render(rows: list[Comparison], baseline_commit: str, current_commit: str) -> str:
    lines = [
        f"baseline {baseline_commit} → current {current_commit}",
        "",
        f"  {'metric':44s} {'baseline':>10s} {'current':>10s}  change  verdict",
        "  " + "-" * 86,
    ]
    by_suite: dict[str, list[Comparison]] = {}
    for row in rows:
        by_suite.setdefault(row.suite, []).append(row)
    for suite, entries in by_suite.items():
        lines.append(f"[{suite}]")
        lines.extend(entry.line() for entry in entries)
        lines.append("")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.verdict] = counts.get(row.verdict, 0) + 1
    lines.append(
        "summary: " + ", ".join(f"{name}={count}" for name, count in sorted(counts.items())) + ""
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument(
        "--tolerance", type=float, default=0.0, help="ignore deltas at or below this"
    )
    parser.add_argument("--json", action="store_true", help="print the comparison as JSON")
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="exit 2 when a *gated* metric regressed (default: report only)",
    )
    args = parser.parse_args()

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    current = json.loads(args.current.read_text(encoding="utf-8"))
    rows = compare(baseline, current, tolerance=args.tolerance)

    if args.json:
        print(
            json.dumps(
                {
                    "baseline": str(args.baseline),
                    "current": str(args.current),
                    "baseline_commit": baseline.get("git_commit"),
                    "current_commit": current.get("git_commit"),
                    "comparisons": [row.__dict__ for row in rows],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        sys.stdout.write(
            _render(rows, str(baseline.get("git_commit")), str(current.get("git_commit")))
        )

    gated_regressions = [
        row for row in rows if row.verdict == "regressed" and row.severity == "gate"
    ]
    if gated_regressions:
        print("\nGATED REGRESSIONS", file=sys.stderr)
        for row in gated_regressions:
            print(f"  {row.suite}: {row.metric} {row.delta:+.4f}", file=sys.stderr)
        if args.fail_on_regression:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
