"""Metric primitives for the evaluation suites.

Every number the eval report prints is computed here, and every function here has a unit
test with a hand-checked value (``evals/tests/test_metrics.py``). That rule exists because
of how these numbers are used: "Evidence F1 = 0.94" ends up in a README and in an interview,
and a metric with an inverted precision/recall or a mis-ordered confusion matrix produces a
plausible-looking wrong number that nobody would question.

Four families:

* **classification** — precision/recall/F1 for one class, and a full multiclass report with a
  confusion matrix. Used by evidence validation, where the interesting error is not the total
  accuracy but *which* label gets confused with which.
* **retrieval** — Hit@k, Recall@k and MRR. Hit@k asks "is a relevant document in the top k",
  Recall@k asks "how much of the relevant set is in the top k", and the two disagree exactly
  when a query has several relevant documents — which is the normal case for evidence.
* **calibration** — reliability buckets, Expected Calibration Error and the Brier score. These
  answer a question accuracy cannot: *when the system says 0.8, is it right 80% of the time?*
* **rates** — the small guarded divisions that everything else is built from, so a zero
  denominator is a documented `0.0` rather than a `ZeroDivisionError` or a `nan`.

Nothing here imports the AI core: metrics are arithmetic, and keeping them free of the thing
being measured is what lets them be tested against hand-computed values.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

__all__ = [
    "Bucket",
    "ClassificationReport",
    "PRF",
    "brier_score",
    "classification_report",
    "expected_calibration_error",
    "hit_at_k",
    "mean_reciprocal_rank",
    "prf",
    "rate",
    "recall_at_k",
    "reciprocal_rank",
    "reliability_buckets",
]


def rate(numerator: int | float, denominator: int | float) -> float:
    """A guarded division: an empty denominator is `0.0`, never `nan` or an exception.

    Reported as a documented zero because every caller prints the sample size next to the
    number: "0.0 over 0 cases" is visibly not a measurement, while `nan` propagates silently
    into a mean and poisons a whole suite.
    """
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


# ── classification ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PRF:
    """Precision, recall and F1 for one class, with the counts they came from."""

    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float

    @property
    def support(self) -> int:
        """How many gold items carry this label — the number that makes the rest readable."""
        return self.tp + self.fn


def prf(tp: int, fp: int, fn: int) -> PRF:
    """Precision/recall/F1 from raw counts.

    F1 is the harmonic mean, defined as 0.0 when precision and recall are both 0 rather than
    raising: a class the system never predicts and that never occurs is a real (if boring)
    outcome, and it must not crash a report.
    """
    precision = rate(tp, tp + fp)
    recall = rate(tp, tp + fn)
    if precision + recall == 0:
        return PRF(tp=tp, fp=fp, fn=fn, precision=precision, recall=recall, f1=0.0)
    return PRF(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=2 * precision * recall / (precision + recall),
    )


@dataclass
class ClassificationReport:
    """Multiclass results: per-class PRF, macro/micro aggregates, and the confusion matrix."""

    labels: list[str]
    per_class: dict[str, PRF] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    accuracy: float = 0.0
    macro_precision: float = 0.0
    macro_recall: float = 0.0
    macro_f1: float = 0.0
    micro_precision: float = 0.0
    micro_recall: float = 0.0
    micro_f1: float = 0.0
    cases: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "cases": self.cases,
            "accuracy": round(self.accuracy, 6),
            "macro_precision": round(self.macro_precision, 6),
            "macro_recall": round(self.macro_recall, 6),
            "macro_f1": round(self.macro_f1, 6),
            "micro_precision": round(self.micro_precision, 6),
            "micro_recall": round(self.micro_recall, 6),
            "micro_f1": round(self.micro_f1, 6),
            "per_class": {
                label: {
                    "support": stats.support,
                    "precision": round(stats.precision, 6),
                    "recall": round(stats.recall, 6),
                    "f1": round(stats.f1, 6),
                    "tp": stats.tp,
                    "fp": stats.fp,
                    "fn": stats.fn,
                }
                for label, stats in self.per_class.items()
            },
            "confusion": self.confusion,
        }


def classification_report(
    gold: Sequence[str], predicted: Sequence[str], labels: Sequence[str]
) -> ClassificationReport:
    """Build the full report from parallel gold/predicted label sequences.

    Macro averages are computed over **every** declared label, including ones with zero gold
    support. That is deliberate for this project: a label that never occurs in the dataset but
    exists in the schema (say `contradicted`) should pull the macro average down to show that
    the suite does not exercise it, rather than being silently dropped from the average and
    leaving the impression of coverage.
    """
    if len(gold) != len(predicted):
        raise ValueError(f"gold and predicted differ in length: {len(gold)} vs {len(predicted)}")

    confusion = {label: dict.fromkeys(labels, 0) for label in labels}
    # Filled in one pass, before the per-label loop. An earlier version incremented inside that
    # loop, which counted every pair once per declared label: a three-label suite reported a
    # cell of 3 for a single case, and the matrix rows no longer summed to the case count.
    # The test that sums the matrix is what caught it.
    for gold_label, predicted_label in zip(gold, predicted, strict=True):
        if predicted_label not in confusion[gold_label]:
            raise ValueError(
                f"predicted label {predicted_label!r} is not in the declared labels {list(labels)}"
            )
        confusion[gold_label][predicted_label] += 1

    per_class: dict[str, PRF] = {}
    for label in labels:
        tp = fp = fn = 0
        for gold_label, predicted_label in zip(gold, predicted, strict=True):
            if gold_label == label and predicted_label == label:
                tp += 1
            elif predicted_label == label:
                fp += 1
            elif gold_label == label:
                fn += 1
        per_class[label] = prf(tp, fp, fn)

    cases = len(gold)
    correct = sum(1 for g, p in zip(gold, predicted, strict=True) if g == p)
    tp_total = sum(stats.tp for stats in per_class.values())
    fp_total = sum(stats.fp for stats in per_class.values())
    fn_total = sum(stats.fn for stats in per_class.values())

    return ClassificationReport(
        labels=list(labels),
        per_class=per_class,
        confusion=confusion,
        accuracy=rate(correct, cases),
        macro_precision=rate(sum(s.precision for s in per_class.values()), len(labels)),
        macro_recall=rate(sum(s.recall for s in per_class.values()), len(labels)),
        macro_f1=rate(sum(s.f1 for s in per_class.values()), len(labels)),
        micro_precision=rate(tp_total, tp_total + fp_total),
        micro_recall=rate(tp_total, tp_total + fn_total),
        micro_f1=prf(tp_total, fp_total, fn_total).f1,
        cases=cases,
    )


# ── retrieval ────────────────────────────────────────────────────────────────


def hit_at_k(ranked_ids: Sequence[str], relevant: Iterable[str], k: int) -> bool:
    """True when at least one relevant id appears in the first ``k`` results.

    ``hit_at_1`` is a strictly harder question than ``recall_at_5``: an engine can return every
    relevant document and still fail Hit@1 by ordering them badly, which is why both are
    reported instead of one blended "retrieval quality" number.
    """
    relevant_set = set(relevant)
    return any(doc_id in relevant_set for doc_id in list(ranked_ids)[:k])


def recall_at_k(ranked_ids: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Share of the relevant documents that appear in the first ``k`` results."""
    relevant_set = set(relevant)
    if not relevant_set:
        return 0.0
    found = len(relevant_set & set(list(ranked_ids)[:k]))
    return found / len(relevant_set)


def reciprocal_rank(ranked_ids: Sequence[str], relevant: Iterable[str]) -> float:
    """``1 / rank`` of the first relevant result, or ``0.0`` when none is found."""
    relevant_set = set(relevant)
    for index, doc_id in enumerate(ranked_ids):
        if doc_id in relevant_set:
            return 1.0 / (index + 1)
    return 0.0


def mean_reciprocal_rank(per_query: Sequence[float]) -> float:
    """Average of per-query reciprocal ranks; ``0.0`` for no queries."""
    return rate(sum(per_query), len(per_query))


# ── calibration ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Bucket:
    """One reliability bucket: what the system claimed, and what actually happened."""

    low: float
    high: float
    count: int
    mean_confidence: float
    accuracy: float

    @property
    def gap(self) -> float:
        """Signed calibration gap. Positive means over-confident (claimed more than delivered)."""
        return self.mean_confidence - self.accuracy

    @property
    def label(self) -> str:
        return f"{self.low:.1f}–{self.high:.1f}"


def reliability_buckets(
    confidences: Sequence[float], correct: Sequence[bool], bins: int = 10
) -> list[Bucket]:
    """Group predictions by confidence and compare the claim with the outcome.

    Buckets are half-open ``[low, high)`` except the last, which includes 1.0 — otherwise a
    confidence of exactly 1.0 would fall outside every bucket and vanish from the report,
    which is precisely the bucket a resume system most needs to see.
    """
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct differ in length")
    if bins <= 0:
        raise ValueError("bins must be positive")

    width = 1.0 / bins
    buckets: list[Bucket] = []
    for index in range(bins):
        low = index * width
        high = low + width
        members = [
            (confidence, hit)
            for confidence, hit in zip(confidences, correct, strict=True)
            if (low <= confidence < high) or (index == bins - 1 and confidence == high)
        ]
        if not members:
            buckets.append(Bucket(low=low, high=high, count=0, mean_confidence=0.0, accuracy=0.0))
            continue
        buckets.append(
            Bucket(
                low=low,
                high=high,
                count=len(members),
                mean_confidence=sum(confidence for confidence, _ in members) / len(members),
                accuracy=sum(1 for _, hit in members if hit) / len(members),
            )
        )
    return buckets


def expected_calibration_error(buckets: Sequence[Bucket]) -> float:
    """Sample-weighted mean absolute gap between confidence and accuracy.

    Empty buckets contribute nothing: an ECE that counted ten empty buckets as perfectly
    calibrated would reward a model for making only confident predictions.
    """
    total = sum(bucket.count for bucket in buckets)
    if total == 0:
        return 0.0
    return sum(bucket.count * abs(bucket.gap) for bucket in buckets) / total


def brier_score(confidences: Sequence[float], correct: Sequence[bool]) -> float:
    """Mean squared error of the confidence against the outcome (lower is better).

    Reported beside ECE because the two disagree in a useful way: Brier punishes a single
    confident mistake heavily, while ECE describes the average gap. A system can have a good
    ECE and a bad Brier score, and for a resume gate that combination means "usually honest,
    occasionally certain and wrong" — the failure this product exists to prevent.
    """
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct differ in length")
    if not confidences:
        return 0.0
    return sum(
        (confidence - (1.0 if hit else 0.0)) ** 2
        for confidence, hit in zip(confidences, correct, strict=True)
    ) / len(confidences)
