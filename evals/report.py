"""The evaluation report: one schema, two renderings, no hand-written numbers.

Every suite returns a :class:`SuiteOutcome`; this module turns the collection into
``reports/eval-report.json`` (machine-readable, stable, diffable) and
``reports/eval-report.md`` (the same content for a human on GitHub). Both come from the same
objects, so the prose and the JSON can never disagree — which is the failure mode of a
hand-written results table, and the reason the project does not have one.

The JSON carries a ``schema_version`` because the report is compared across commits
(``evals/compare.py``): without it, a comparison between two differently-shaped reports would
produce confident nonsense instead of an error.

Calibration lives here rather than in a suite because it is a *view* of evidence validation's
per-case confidence, not a separate measurement: the same run produces
``reports/confidence-calibration.json`` and ``.md``, so a calibration claim is always traceable
to the cases it came from.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from evals.config import DEFAULT_BINS, thresholds_for
from evals.metrics import (
    Bucket,
    brier_score,
    expected_calibration_error,
    reliability_buckets,
)

__all__ = [
    "SCHEMA_VERSION",
    "SuiteOutcome",
    "build_report",
    "calibration_artifacts",
    "calibration_metrics",
    "render_markdown",
]

SCHEMA_VERSION = "1.0"

#: Confidence at or above which a wrong verdict is reported explicitly. 0.75 is the same
#: threshold the gate itself uses to call a claim supported, so "confident and wrong" here means
#: the same thing it means inside the product.
_HIGH_CONFIDENCE = 0.75


@dataclass
class SuiteOutcome:
    """What one suite measured, with the raw material a reader might want to check."""

    name: str
    dataset: str
    dataset_version: str
    cases: int
    metrics: dict[str, float] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)
    skipped: str | None = None
    duration_ms: int = 0
    #: ``{case_id, confidence, predicted, gold, correct, unsafe}`` — the rows the calibration
    #: artefact is computed from, kept in the report so the buckets can be re-derived.
    confidence_rows: list[dict[str, Any]] = field(default_factory=list)

    def threshold_entries(self) -> dict[str, dict[str, Any]]:
        """Apply the configured thresholds to the measured metrics."""
        entries: dict[str, dict[str, Any]] = {}
        for threshold in thresholds_for(self.name):
            value = self.metrics.get(threshold.metric)
            if value is None:
                entries[threshold.metric] = {
                    "value": None,
                    "threshold": threshold.bound,
                    "direction": threshold.direction,
                    "severity": threshold.severity,
                    "status": "not_measured",
                    "rationale": threshold.rationale,
                }
                continue
            entries[threshold.metric] = threshold.to_dict(value)
        return entries

    def gate_failures(self) -> list[str]:
        return [
            metric
            for metric, entry in self.threshold_entries().items()
            if entry["severity"] == "gate" and entry["status"] == "miss"
        ]

    def reported_misses(self) -> list[str]:
        return [
            metric
            for metric, entry in self.threshold_entries().items()
            if entry["severity"] == "report" and entry["status"] == "miss"
        ]

    @property
    def passed(self) -> bool:
        """A suite passes when no *gate* threshold is missed and it was not skipped."""
        return self.skipped is None and not self.gate_failures()

    def to_dict(self) -> dict[str, Any]:
        entry = self.threshold_entries()
        return {
            "dataset": self.dataset,
            "dataset_version": self.dataset_version,
            "cases": self.cases,
            "duration_ms": self.duration_ms,
            "skipped": self.skipped,
            "passed": self.passed,
            "metrics": {key: round(value, 6) for key, value in sorted(self.metrics.items())},
            "thresholds": {key: entry[key] for key in sorted(entry)},
            "counters": dict(sorted(self.counters.items())),
            "breakdown": self.breakdown,
            "failures": self.failures,
            "confidence_rows": self.confidence_rows,
            "gate_failures": self.gate_failures(),
            "reported_misses": self.reported_misses(),
        }


def build_report(
    *,
    outcomes: Sequence[SuiteOutcome],
    provider: str,
    provider_chain: Sequence[str],
    model: str | None,
    git_commit: str,
    git_dirty: bool,
    datasets: dict[str, Any],
    dataset_caveat: str,
    versions: dict[str, str],
    started_at: datetime | None = None,
    duration_ms: int = 0,
) -> dict[str, Any]:
    """Assemble the report document. Every field is measured or absent — never guessed."""
    suites = {outcome.name: outcome.to_dict() for outcome in outcomes}
    cases = sum(outcome.cases for outcome in outcomes if outcome.skipped is None)
    gated = [outcome for outcome in outcomes if outcome.skipped is None]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": (started_at or datetime.now(UTC)).isoformat(),
        "git_commit": git_commit,
        "git_dirty": git_dirty,
        "provider": provider,
        "provider_chain": list(provider_chain),
        "model": model,
        "versions": versions,
        "datasets": datasets,
        "dataset_caveat": dataset_caveat,
        "summary": {
            "suites": len(outcomes),
            "suites_executed": len(gated),
            "suites_skipped": len(outcomes) - len(gated),
            "cases": cases,
            "metrics": sum(len(outcome.metrics) for outcome in outcomes),
            "gated_passed": sum(1 for outcome in gated if outcome.passed),
            "gated_failed": sum(1 for outcome in gated if not outcome.passed),
            "reported_misses": sum(len(outcome.reported_misses()) for outcome in gated),
            "duration_ms": duration_ms,
        },
        "suites": suites,
    }


def _threshold_cells(entry: dict[str, Any] | None) -> tuple[str, str]:
    """(bound, status) as two table cells, so the markdown stays a plain table."""
    if entry is None:
        return "—", "measured, no threshold"
    if entry["status"] == "not_measured":
        return "—", "not measured"
    sign = "≥" if entry["direction"] == "min" else "≤"
    mark = "**PASS**" if entry["status"] == "pass" else "**MISS**"
    scope = "" if entry["severity"] == "gate" else " (report only)"
    return f"{sign} {entry['threshold']:.2f}", f"{mark}{scope}"


def render_markdown(report: dict[str, Any]) -> str:
    """Render the report for GitHub. Generated — never edited by hand."""
    summary = report["summary"]
    lines: list[str] = [
        "# Evaluation report",
        "",
        f"- schema `{report['schema_version']}` · generated `{report['generated_at']}`",
        f"- commit `{report['git_commit']}`"
        + (" (working tree dirty)" if report.get("git_dirty") else ""),
        f"- provider `{report['provider']}` × chain {', '.join(report['provider_chain']) or '—'}"
        + (f" · model `{report['model']}`" if report.get("model") else ""),
        f"- suites {summary['suites_executed']}/{summary['suites']} executed · "
        f"cases **{summary['cases']}** · "
        f"gated pass **{summary['gated_passed']}** / fail **{summary['gated_failed']}** · "
        f"reported misses {summary['reported_misses']}",
        "",
    ]

    if report.get("dataset_caveat"):
        lines += [f"> {report['dataset_caveat']}", ""]

    lines += [
        "| suite | cases | gated | reported misses | duration |",
        "| --- | ---: | --- | --- | ---: |",
    ]
    for name, suite in report["suites"].items():
        if suite["skipped"]:
            lines.append(f"| `{name}` | — | skipped | — | — |")
            continue
        gates = "PASS" if suite["passed"] else "FAIL"
        misses = ", ".join(f"`{metric}`" for metric in suite["reported_misses"]) or "—"
        lines.append(
            f"| `{name}` | {suite['cases']} | {gates} | {misses} | {suite['duration_ms']} ms |"
        )
    lines.append("")

    for name, suite in report["suites"].items():
        lines += [f"## {name}", ""]
        if suite["skipped"]:
            lines += [f"Skipped: {suite['skipped']}", ""]
            continue
        lines += [
            f"Dataset `{suite['dataset']}` @ `{suite['dataset_version']}` · "
            f"{suite['cases']} cases · {suite['duration_ms']} ms",
            "",
            "| metric | value | threshold | status |",
            "| --- | ---: | --- | --- |",
        ]
        for metric, value in suite["metrics"].items():
            bound, status = _threshold_cells(suite["thresholds"].get(metric))
            lines.append(f"| `{metric}` | {value:.4f} | {bound} | {status} |")
        lines.append("")

        if suite["counters"]:
            lines += [
                "Counters: "
                + ", ".join(f"`{key}`={value}" for key, value in suite["counters"].items()),
                "",
            ]

        for group, rows in suite["breakdown"].items():
            lines += [f"### {group}", "", "| key | metrics |", "| --- | --- |"]
            for key, values in rows.items():
                rendered = ", ".join(f"{k}={v}" for k, v in values.items())
                lines.append(f"| `{key}` | {rendered} |")
            lines.append("")

        if suite["failures"]:
            lines += [f"### Recorded failures ({len(suite['failures'])})", "", "```json"]
            for failure in suite["failures"][:8]:
                lines.append(_compact_json(failure))
            lines.append("```")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _compact_json(payload: Any, limit: int = 240) -> str:
    import json

    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def calibration_metrics(payload: Mapping[str, Any]) -> dict[str, float]:
    """Calibration numbers as **compared metrics**, for the suite's ``metrics`` mapping.

    ECE and Brier used to exist only inside ``reports/confidence-calibration.json``/``.md``, which
    made them un-comparable: ``evals/compare.py`` declares lower-is-better rules for the names
    ``ece`` and ``brier``, so the tool expected these metrics in the report and nothing emitted them.
    A calibration change could not appear in a diff and could not fail a gate; the number was
    published and invisible to every automated check. PHASE 14 wires them in here.

    The names are spelled in full rather than derived from ``payload["suite"]`` because the metric
    prefix convention in this project is the short one (``evidence.``, ``jd.``, ``retrieval.``) and
    the suite key is ``evidence_validation``; deriving it would produce a name no threshold in
    ``evals/config.py`` is keyed by.
    """
    return {
        "evidence.ece": float(payload["expected_calibration_error"]),
        "evidence.brier": float(payload["brier_score"]),
    }


def calibration_artifacts(
    outcome: SuiteOutcome, bins: int = DEFAULT_BINS
) -> tuple[dict[str, Any], str]:
    """Reliability diagram data, ECE and Brier score for one suite's confidence rows.

    Returns ``(json_payload, markdown)``. The markdown is a table a reviewer can read without
    parsing JSON, and it states the sample size per bucket: a bucket holding one case is noise,
    and showing it without its count would invite treating it as a finding.
    """
    rows = [row for row in outcome.confidence_rows if "confidence" in row]
    confidences = [float(row["confidence"]) for row in rows]
    correct = [bool(row["correct"]) for row in rows]
    buckets: list[Bucket] = reliability_buckets(confidences, correct, bins=bins)
    ece = expected_calibration_error(buckets)
    brier = brier_score(confidences, correct)

    unsafe = [row for row in rows if row.get("unsafe")]
    confident_wrong = [
        row for row in rows if not row["correct"] and float(row["confidence"]) >= _HIGH_CONFIDENCE
    ]

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "suite": outcome.name,
        "generated_from": {
            "cases": len(rows),
            "dataset": outcome.dataset,
            "dataset_version": outcome.dataset_version,
        },
        "bins": bins,
        "expected_calibration_error": round(ece, 6),
        "brier_score": round(brier, 6),
        "accuracy": round(sum(1 for hit in correct if hit) / len(correct), 6) if correct else None,
        "mean_confidence": round(sum(confidences) / len(confidences), 6) if confidences else None,
        "buckets": [
            {
                "low": round(bucket.low, 3),
                "high": round(bucket.high, 3),
                "count": bucket.count,
                "mean_confidence": round(bucket.mean_confidence, 6),
                "accuracy": round(bucket.accuracy, 6),
                "gap": round(bucket.gap, 6),
            }
            for bucket in buckets
        ],
        "unsafe_support_cases": len(unsafe),
        "confident_wrong_cases": len(confident_wrong),
    }

    lines = [
        f"# Confidence calibration — {outcome.name}",
        "",
        f"- cases {len(rows)} (dataset `{outcome.dataset}` @ `{outcome.dataset_version}`), "
        f"{bins} bins",
        f"- **ECE** {ece:.4f} · **Brier** {brier:.4f}"
        + (
            f" · accuracy {payload['accuracy']:.4f} · mean confidence "
            f"{payload['mean_confidence']:.4f}"
            if payload["accuracy"] is not None and payload["mean_confidence"] is not None
            else ""
        ),
        f"- high-confidence mistakes (confidence ≥ {_HIGH_CONFIDENCE}): {len(confident_wrong)}"
        f" · unsafe supports: {len(unsafe)}",
        "",
        "| bucket | cases | mean confidence | actual accuracy | gap |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for bucket in buckets:
        if bucket.count == 0:
            lines.append(f"| {bucket.label} | 0 | — | — | — |")
            continue
        lines.append(
            f"| {bucket.label} | {bucket.count} | {bucket.mean_confidence:.4f} | "
            f"{bucket.accuracy:.4f} | {bucket.gap:+.4f} |"
        )
    lines += [
        "",
        "A positive gap means over-confidence: the system claimed more than it delivered. "
        "ECE is the case-weighted mean absolute gap; Brier is the mean squared error, which "
        "punishes a single confident mistake more than ECE does.",
        "",
    ]
    if confident_wrong:
        lines += [
            "## High-confidence mistakes",
            "",
            "| case | claim | confidence | gold | predicted |",
            "| --- | --- | ---: | --- | --- |",
        ]
        for row in confident_wrong[:10]:
            lines.append(
                f"| `{row.get('case_id', '?')}` | {_compact_json(row.get('claim', ''), 60)} | "
                f"{float(row['confidence']):.4f} | `{row.get('gold')}` | `{row.get('predicted')}` |"
            )
        lines.append("")

    return payload, "\n".join(lines).rstrip() + "\n"
