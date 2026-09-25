"""Hand-checked tests for the eval metrics.

Every value below was computed by hand (or from a worked example) before being written down,
so this file is a check on the *implementation*, not a snapshot of its output. If a metric
changes shape, these fail loudly instead of silently re-baselining.
"""

from __future__ import annotations

import math

import pytest

from evals.metrics import (
    brier_score,
    classification_report,
    expected_calibration_error,
    hit_at_k,
    mean_reciprocal_rank,
    prf,
    rate,
    recall_at_k,
    reciprocal_rank,
    reliability_buckets,
)


def test_rate_treats_an_empty_denominator_as_zero() -> None:
    assert rate(3, 4) == 0.75
    assert rate(0, 0) == 0.0
    # Never nan: a nan would propagate into every aggregate that includes it.
    assert not math.isnan(rate(0, 0))


def test_prf_matches_the_worked_example() -> None:
    # tp=3, fp=1, fn=2 → precision 0.75, recall 0.6, f1 = 2*.75*.6/1.35 = 0.6666...
    stats = prf(tp=3, fp=1, fn=2)
    assert stats.precision == pytest.approx(0.75)
    assert stats.recall == pytest.approx(0.6)
    assert stats.f1 == pytest.approx(2 * 0.75 * 0.6 / (0.75 + 0.6))
    assert stats.support == 5


def test_prf_of_a_class_that_never_occurs_is_zero_not_an_error() -> None:
    stats = prf(tp=0, fp=0, fn=0)
    assert (stats.precision, stats.recall, stats.f1) == (0.0, 0.0, 0.0)


def test_prf_when_everything_predicted_is_wrong() -> None:
    # Nothing correct, four false positives and four false negatives.
    stats = prf(tp=0, fp=4, fn=4)
    assert stats.precision == 0.0 and stats.recall == 0.0 and stats.f1 == 0.0


def test_confusion_matrix_counts_every_pair_and_sums_to_the_case_count() -> None:
    gold = ["supported", "unsupported", "partially_supported", "supported"]
    predicted = ["supported", "supported", "partially_supported", "partially_supported"]
    report = classification_report(
        gold, predicted, labels=["supported", "partially_supported", "unsupported"]
    )

    assert report.cases == 4
    assert report.confusion["supported"] == {
        "supported": 1,
        "partially_supported": 1,
        "unsupported": 0,
    }
    # The one dangerous cell: an unsupported claim that came back supported.
    assert report.confusion["unsupported"]["supported"] == 1
    assert sum(sum(row.values()) for row in report.confusion.values()) == 4
    assert report.accuracy == pytest.approx(0.5)


def test_per_class_numbers_are_checkable_by_hand() -> None:
    # supported: 2 gold (one right, one called partial) → P=1.0 (1 tp, 0 fp), R=0.5
    gold = ["supported", "supported"]
    predicted = ["supported", "partially_supported"]
    report = classification_report(
        gold, predicted, labels=["supported", "partially_supported", "unsupported"]
    )
    supported = report.per_class["supported"]
    assert (supported.tp, supported.fp, supported.fn) == (1, 0, 1)
    assert supported.precision == pytest.approx(1.0)
    assert supported.recall == pytest.approx(0.5)
    assert supported.f1 == pytest.approx(2 / 3)


def test_macro_average_includes_labels_with_no_gold_support() -> None:
    # `unsupported` never occurs in the gold labels, so its F1 is 0 and the macro average is
    # dragged down: the suite is not exercising that label and the number must say so.
    report = classification_report(
        ["supported"], ["supported"], labels=["supported", "unsupported"]
    )
    assert report.per_class["unsupported"].support == 0
    assert report.macro_f1 == pytest.approx(0.5)
    assert report.micro_f1 == pytest.approx(1.0)


def test_classification_report_rejects_a_label_it_was_not_told_about() -> None:
    with pytest.raises(ValueError, match="not in the declared labels"):
        classification_report(["supported"], ["invented"], labels=["supported"])
    with pytest.raises(ValueError, match="differ in length"):
        classification_report(["a"], ["a", "b"], labels=["a", "b"])


def test_hit_and_recall_answer_different_questions() -> None:
    ranked = ["a", "b", "c", "d"]
    relevant = {"c", "d"}
    # Nothing relevant in the top 2 …
    assert hit_at_k(ranked, relevant, 1) is False
    assert hit_at_k(ranked, relevant, 3) is True
    # … but the whole relevant set is inside the top 5, so recall is perfect.
    assert recall_at_k(ranked, relevant, 5) == pytest.approx(1.0)
    assert recall_at_k(ranked, relevant, 3) == pytest.approx(0.5)


def test_recall_at_k_with_no_relevant_documents_is_zero() -> None:
    assert recall_at_k(["a"], set(), 5) == 0.0


def test_reciprocal_rank_uses_the_first_relevant_hit_only() -> None:
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == pytest.approx(1.0)
    assert reciprocal_rank(["a", "b", "c"], {"b"}) == pytest.approx(0.5)
    assert reciprocal_rank(["a", "b", "c"], {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(["a", "b"], {"z"}) == 0.0


def test_mrr_is_the_mean_of_the_per_query_ranks() -> None:
    assert mean_reciprocal_rank([1.0, 0.5, 0.0]) == pytest.approx(0.5)
    assert mean_reciprocal_rank([]) == 0.0


def test_buckets_place_a_confidence_of_one_in_the_last_bucket() -> None:
    buckets = reliability_buckets([0.0, 0.55, 1.0], [False, True, True], bins=10)
    assert buckets[0].count == 1
    assert buckets[5].count == 1
    # Exactly 1.0 must be counted, or the most confident predictions would be invisible.
    assert buckets[9].count == 1
    assert sum(bucket.count for bucket in buckets) == 3


def test_a_perfectly_calibrated_system_has_zero_ece() -> None:
    # 10 predictions at 0.8, 8 of them correct → bucket mean 0.8, accuracy 0.8, gap 0.0.
    confidences = [0.8] * 10
    correct = [True] * 8 + [False] * 2
    buckets = reliability_buckets(confidences, correct, bins=10)
    assert expected_calibration_error(buckets) == pytest.approx(0.0, abs=1e-12)


def test_ece_is_the_weighted_mean_gap_not_an_unweighted_one() -> None:
    # Bucket 0.4–0.5: 9 predictions at 0.45, all correct → |0.45 − 1.00| = 0.55.
    # Bucket 0.9–1.0: 1 prediction at 0.95, wrong → |0.95 − 0.00| = 0.95.
    # Unweighted mean would be 0.75; the sample-weighted ECE is (9·0.55 + 1·0.95)/10 = 0.59.
    confidences = [0.45] * 9 + [0.95]
    correct = [True] * 9 + [False]
    buckets = reliability_buckets(confidences, correct, bins=10)
    assert expected_calibration_error(buckets) == pytest.approx((9 * 0.55 + 0.95) / 10)
    unweighted = sum(abs(bucket.gap) for bucket in buckets if bucket.count) / 2
    assert unweighted == pytest.approx(0.75)
    # The two differ, so the weighting is observable rather than incidental.
    assert expected_calibration_error(buckets) != pytest.approx(unweighted)


def test_over_confidence_is_signed_positive() -> None:
    buckets = reliability_buckets([0.9] * 4, [True, False, False, False], bins=10)
    assert buckets[9].gap == pytest.approx(0.9 - 0.25)
    assert buckets[9].gap > 0


def test_empty_buckets_do_not_flatter_the_score() -> None:
    # One confident, correct prediction and nine empty buckets: ECE describes that one
    # prediction, not ten buckets.
    buckets = reliability_buckets([0.95], [True], bins=10)
    assert expected_calibration_error(buckets) == pytest.approx(0.05)


def test_brier_score_textbook_values() -> None:
    # Confidently right four times: (1-0.9)^2 * 4 / 4 = 0.01
    assert brier_score([0.9] * 4, [True] * 4) == pytest.approx(0.01)
    # Confidently wrong: (0.9-0)^2 = 0.81 — the case ECE alone would understate.
    assert brier_score([0.9], [False]) == pytest.approx(0.81)
    # A coin flip is 0.25 either way.
    assert brier_score([0.5, 0.5], [True, False]) == pytest.approx(0.25)
    assert brier_score([], []) == 0.0


def test_length_mismatches_are_rejected_rather_than_truncated() -> None:
    with pytest.raises(ValueError):
        reliability_buckets([0.5], [True, False])
    with pytest.raises(ValueError):
        brier_score([0.5], [True, False])
    with pytest.raises(ValueError):
        reliability_buckets([0.5], [True], bins=0)
