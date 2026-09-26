#!/usr/bin/env python
"""Guard the README's numbers against the artefacts they claim to come from.

The README says, in its own words, that "every number in this README comes from a real build/test/eval
artifact — never from an estimate". That is a claim, and until this script existed nothing checked it:
PHASE 14 found the README, INTERVIEW, QUALITY and DEMO all quoting a previous phase's measurements,
and every stale figure understated the project while being presented as measured.

So the numbers with an artefact behind them are checked mechanically. Each expected string is *derived*
from the artefact at run time and then searched for in the README — if a metric moves, the README stops
containing the derived value and this fails. Values that no artefact holds (the test counts, which come
from running the suites; the commit count, which git knows) are listed as unchecked rather than
silently passing, because a guard that pretends to cover everything covers nothing.

Usage::

    python scripts/check_readme_metrics.py
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
EVAL_REPORT = REPO_ROOT / "reports" / "eval-report.json"
CALIBRATION = REPO_ROOT / "reports" / "confidence-calibration.json"
COVERAGE = REPO_ROOT / "reports" / "coverage-summary.md"
PROOF = REPO_ROOT / "reports" / "release-proof.json"

#: (what it is, the README's formatting of it) for every value an artefact holds.
#: Three decimals for fractions, one for percentages — matching how the README writes them.
EVAL_METRICS = {
    "jd.required_skill_f1": ("JD required-skill F1", "{:.3f}"),
    "jd.evidence_grounding_rate": ("JD evidence grounding", "{:.3f}"),
    "jd.distractor_leakage_rate": ("JD distractor leakage", "{:.3f}"),
    "evidence.accuracy": ("evidence accuracy", "{:.3f}"),
    "evidence.macro_f1": ("evidence macro F1", "{:.3f}"),
    "evidence.unsupported_recall": ("unsupported recall", "{:.3f}"),
    "evidence.support_recall": ("support recall", "{:.3f}"),
    "evidence.unsafe_support_rate": ("unsafe support rate", "{:.3f}"),
    "evidence.unsafe_numeric_support_rate": ("fabricated-number acceptance", "{:.3f}"),
    "retrieval.hit_at_1": ("retrieval Hit@1", "{:.3f}"),
    "retrieval.hit_at_3": ("retrieval Hit@3", "{:.3f}"),
    "retrieval.hit_at_5": ("retrieval Hit@5", "{:.3f}"),
    "retrieval.mrr": ("retrieval MRR", "{:.3f}"),
    "interview.required_skill_coverage": ("interview skill coverage", "{:.3f}"),
    "interview.duplicate_rate": ("interview duplicate rate", "{:.3f}"),
    "interview.forbidden_leakage_rate": ("interview cross-role leakage", "{:.3f}"),
}


def _renderings(value: float) -> list[str]:
    """How the artefact's value is written at three decimals: rendered once, from the stored number.

    The list has one element, and it is a list only so the checking loop reads the same for prose forms
    that legitimately have alternatives. The single-element rule is the point: `retrieval.hit_at_1` is
    50/59 = 0.847457…, which is `0.847`. Writing `0.848` means rounding to `0.8475` first and then
    rounding again — a real, if small, drift away from the number the report states, and exactly the
    kind this guard exists to catch. (It did catch it: the README said 0.848 until this check ran.)
    """
    return [f"{value:.3f}"]


def _metrics() -> dict[str, float]:
    report = json.loads(EVAL_REPORT.read_text(encoding="utf-8"))
    out: dict[str, float] = {}
    for suite in report["suites"].values():
        for name, value in suite.get("metrics", {}).items():
            out[name] = float(value)
    return out, report["summary"]  # type: ignore[return-value]


def main() -> int:
    if not README.exists():
        print("README.md is missing", file=sys.stderr)
        return 1
    text = README.read_text(encoding="utf-8")

    metrics, summary = _metrics()
    calibration = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    coverage = COVERAGE.read_text(encoding="utf-8")
    proof = json.loads(PROOF.read_text(encoding="utf-8"))

    # `**core domain: 92.5%** (1556/1683 statements)` — the emphasis markers sit between the figure and
    # the counts, so they are part of the pattern rather than an accident to strip first.
    core = re.search(r"core domain:\s*\*{0,2}([\d.]+)%\*{0,2}\s*\((\d+)\s*/\s*(\d+)", coverage)
    if core is None:
        print(
            "could not read core-domain coverage from reports/coverage-summary.md", file=sys.stderr
        )
        return 1

    checks: list[tuple[str, list[str]]] = []
    for name, (label, _fmt) in EVAL_METRICS.items():
        if name not in metrics:
            print(
                f"{name} is not in the evaluation report — the metric was renamed", file=sys.stderr
            )
            return 1
        checks.append((label, _renderings(metrics[name])))

    checks += [
        ("unsafe support rate (prose form)", [f"{metrics['evidence.unsafe_support_rate']:.4f}"]),
        ("calibration ECE", _renderings(calibration["expected_calibration_error"])),
        ("calibration Brier", _renderings(calibration["brier_score"])),
        ("core-domain coverage", [f"{core.group(1)}%"]),
        ("coverage statement count", [f"{int(core.group(3)):,}"]),
        ("evaluation cases", [f"{summary['cases']} cases"]),
        ("release proof", [f"{proof['summary']['passed']}/{proof['summary']['total']} steps"]),
    ]

    # Structural counts, checked as bare numbers because the prose around them varies legitimately
    # ("four evaluation suites" in one sentence, "4/4 suites" in another). A changed count changes the
    # digits, which is what this catches.
    presence: list[tuple[str, str]] = [
        ("evaluation suites", str(summary["suites_executed"])),
        ("evaluation metrics", str(summary["metrics"])),
    ]

    missing: list[tuple[str, str]] = []
    for label, forms in checks:
        hit = next((form for form in forms if form in text), None)
        shown = " or ".join(forms)
        if hit is None:
            missing.append((label, shown))
            print(f"  MISS {label:38s} {shown}")
        else:
            print(f"  ok   {label:38s} {hit}")
    for label, value in presence:
        if value not in text:
            missing.append((label, value))
            print(f"  MISS {label:38s} {value} (as a bare number)")
        else:
            print(f"  ok   {label:38s} {value} (as a bare number)")

    print()
    if missing:
        print(f"{len(missing)} README figure(s) do not match the artefacts:", file=sys.stderr)
        for label, value in missing:
            print(f"  {label}: the report says {value}", file=sys.stderr)
        print(
            "\nUpdate README.md (and any document quoting the same figure) or explain the difference. "
            "A stale number presented as measured is the defect this guard exists for.",
            file=sys.stderr,
        )
        return 2

    total = len(checks) + len(presence)
    print(f"README figures match the artefacts ({total} checked)")
    print(
        "not covered by an artefact, so not checked here: the test counts (553/400/365/45/22 — they "
        "come from running the suites, and reports/ does not persist them) and the commit count."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
