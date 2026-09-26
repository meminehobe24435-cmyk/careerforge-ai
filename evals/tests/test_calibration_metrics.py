"""Calibration numbers must be *comparable*, not merely published.

`reports/confidence-calibration.md` reported ECE and Brier for several phases while nothing put them
in `reports/eval-report.json`, so `evals/compare.py` never saw them: the tool declared explicit
lower-is-better rules for the names `ece` and `brier` that no metric matched, and a calibration
regression could not appear in a diff or fail a gate. These tests pin the wiring, not the numbers —
the values themselves come from `test_metrics.py`, which checks the arithmetic by hand.
"""

from __future__ import annotations

from evals.compare import direction_of
from evals.config import thresholds_for
from evals.report import calibration_metrics

PAYLOAD = {
    "suite": "evidence_validation",
    "expected_calibration_error": 0.031555,
    "brier_score": 0.090405,
}


def test_calibration_metrics_are_named_so_compare_reads_them_as_errors() -> None:
    """The direction has to come out ``lower``; otherwise a worse calibration reads as an improvement."""
    metrics = calibration_metrics(PAYLOAD)

    assert set(metrics) == {"evidence.ece", "evidence.brier"}
    for name, value in metrics.items():
        assert direction_of(name) == "lower", (
            f"{name} is a calibration error: compare must treat a smaller value as better, and it "
            "derives that from the metric name"
        )
        assert isinstance(value, float)


def test_both_calibration_metrics_have_a_declared_threshold() -> None:
    """A compared metric with no threshold is invisible in the report's own gate table."""
    declared = {threshold.metric for threshold in thresholds_for("evidence_validation")}

    for name in calibration_metrics(PAYLOAD):
        assert name in declared, (
            f"{name} is emitted by the evidence suite but has no entry in evals/config.py, so the "
            "report would print it without saying what value is acceptable"
        )


def test_calibration_thresholds_do_not_gate() -> None:
    """Report-only on purpose.

    At 60 cases a calibration figure moves on a single reclassified example, and a gate that fires on
    that gets switched off. The gate that matters for this suite is `evidence.unsafe_support_rate`,
    which is about letting an invented claim through — a calibration drift is a different, smaller
    statement, and it belongs in the report where it can be argued about.
    """
    calibration = {
        threshold.metric: threshold
        for threshold in thresholds_for("evidence_validation")
        if threshold.metric in {"evidence.ece", "evidence.brier"}
    }

    assert calibration, "the metrics must be declared"
    for name, threshold in calibration.items():
        assert threshold.severity == "report", f"{name} must not gate"
        assert threshold.maximum is not None and threshold.maximum > 0
        # `to_dict` is what the report and the comparison both read.
        row = threshold.to_dict(PAYLOAD["expected_calibration_error"])
        assert row["status"] in {"pass", "miss"}
        assert row["direction"] == "max"
