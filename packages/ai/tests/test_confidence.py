"""Tests for the evidence confidence engine.

The most important assertion in this file is
:func:`test_matches_database_check_constraint_formula`: the same arithmetic is
written in SQL as a ``CHECK`` constraint, and if the two ever disagree the
product's core promise ("this number is auditable") quietly breaks.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from careerforge_ai.schemas.common import ClaimStatus, EvidenceKind, SourceAuthority, utcnow
from careerforge_ai.schemas.evidence import EvidenceLocator
from careerforge_ai.scoring.confidence import (
    AUTHORITY_SCORES,
    CONFIDENCE_FORMULA_VERSION,
    DEFAULT_WEIGHTS,
    authority_for_kind,
    authority_score,
    classify_claim_status,
    compute_confidence,
    corroboration_score,
    extraction_quality_score,
    quantified_claim_allowed,
    recency_score,
    specificity_score,
)


class TestWeights:
    def test_weights_sum_to_one(self) -> None:
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9

    def test_all_weights_non_negative(self) -> None:
        assert all(weight >= 0 for weight in DEFAULT_WEIGHTS.values())


class TestAuthority:
    def test_tier_ordering_is_strict(self) -> None:
        # Code must outrank prose, and prose must outrank a model's inference.
        assert (
            AUTHORITY_SCORES[SourceAuthority.CODE_OR_COMMIT]
            > AUTHORITY_SCORES[SourceAuthority.README]
            > AUTHORITY_SCORES[SourceAuthority.UPLOADED_DOCUMENT]
            > AUTHORITY_SCORES[SourceAuthority.RESUME_SELF_REPORT]
            > AUTHORITY_SCORES[SourceAuthority.LLM_INFERENCE]
        )

    @pytest.mark.parametrize(
        ("kind", "expected"),
        [
            (EvidenceKind.REPO_FILE, SourceAuthority.CODE_OR_COMMIT),
            (EvidenceKind.COMMIT, SourceAuthority.CODE_OR_COMMIT),
            (EvidenceKind.README, SourceAuthority.README),
            (EvidenceKind.DOCUMENT_CHUNK, SourceAuthority.UPLOADED_DOCUMENT),
            (EvidenceKind.LLM_INFERENCE, SourceAuthority.LLM_INFERENCE),
        ],
    )
    def test_kind_maps_to_expected_tier(
        self, kind: EvidenceKind, expected: SourceAuthority
    ) -> None:
        assert authority_for_kind(kind) is expected

    def test_unknown_authority_string_degrades_to_weakest(self) -> None:
        # Ingestion must never fail because a novel source string appeared.
        assert authority_score("something_new") == AUTHORITY_SCORES[SourceAuthority.LLM_INFERENCE]

    def test_none_defaults_to_self_report(self) -> None:
        assert authority_score(None) == AUTHORITY_SCORES[SourceAuthority.RESUME_SELF_REPORT]


class TestRecency:
    def test_unknown_date_uses_documented_default(self) -> None:
        assert recency_score(None) == pytest.approx(0.6)

    def test_fresh_evidence_scores_one(self) -> None:
        assert recency_score(utcnow()) == pytest.approx(1.0)

    def test_future_timestamp_is_clamped(self) -> None:
        assert recency_score(utcnow() + timedelta(days=10)) == 1.0

    def test_decays_by_one_over_e_after_scale_days(self) -> None:
        value = recency_score(utcnow() - timedelta(days=540))
        assert value == pytest.approx(0.3679, abs=1e-3)

    def test_naive_timestamp_does_not_raise(self) -> None:
        # GitHub and PDF parsers both hand back naive datetimes in practice.
        naive = (utcnow() - timedelta(days=30)).replace(tzinfo=None)
        assert 0.0 < recency_score(naive) < 1.0


class TestSpecificity:
    def test_line_level_beats_repo_level(self) -> None:
        assert specificity_score(EvidenceLocator(path="a.c", line=42)) > specificity_score(
            EvidenceLocator(path="a.c")
        )

    def test_specificity_decreases_without_a_locator(self) -> None:
        assert specificity_score(EvidenceLocator(path="a.c", line=1)) == 1.0
        assert specificity_score(EvidenceLocator(path="a.c")) == 0.85
        assert specificity_score(EvidenceLocator(section="Projects")) == 0.6
        assert specificity_score(None) == 0.45
        assert specificity_score(EvidenceLocator()) == 0.45


class TestCorroboration:
    @pytest.mark.parametrize(
        ("sources", "expected"),
        [(0, 0.4), (1, 0.6), (2, 0.8), (3, 1.0), (9, 1.0)],
    )
    def test_saturates_at_one(self, sources: int, expected: float) -> None:
        assert corroboration_score(sources) == pytest.approx(expected)

    def test_negative_input_is_clamped(self) -> None:
        assert corroboration_score(-5) == pytest.approx(0.4)


class TestExtractionQuality:
    def test_tiers(self) -> None:
        assert extraction_quality_score("deterministic") == 1.0
        assert extraction_quality_score("llm") == 0.7
        assert extraction_quality_score("heuristic") == 0.5

    def test_unknown_method_is_treated_as_heuristic(self) -> None:
        assert extraction_quality_score("mystery") == 0.5


class TestComputeConfidence:
    def test_worked_example_file_level_one_source(self) -> None:
        breakdown = compute_confidence(
            kind=EvidenceKind.REPO_FILE,
            locator=EvidenceLocator(path="Core/Src/motor_control.c", line=42),
            independent_sources=1,
        )
        # 0.30·1.00 + 0.15·0.60 + 0.20·1.00 + 0.20·0.60 + 0.15·1.00 = 0.86
        assert breakdown.score == pytest.approx(0.86, abs=1e-6)
        assert breakdown.formula_version == CONFIDENCE_FORMULA_VERSION

    def test_matches_database_check_constraint_formula(self) -> None:
        """Mirror of ``ck_evidence_confidence_formula`` in docs/DATABASE.md.

        Written out longhand on purpose: if someone changes the engine without
        changing the constraint, this test fails instead of the database
        rejecting production writes.
        """
        cases = [
            {
                "kind": EvidenceKind.REPO_FILE,
                "sources": 1,
                "locator": EvidenceLocator(path="a.c", line=3),
                "age_days": 0,
            },
            {
                "kind": EvidenceKind.README,
                "sources": 2,
                "locator": EvidenceLocator(path="README.md"),
                "age_days": 200,
            },
            {
                "kind": EvidenceKind.DOCUMENT_CHUNK,
                "sources": 3,
                "locator": EvidenceLocator(page=4),
                "age_days": 900,
            },
            {"kind": EvidenceKind.LLM_INFERENCE, "sources": 0, "locator": None, "age_days": 10},
        ]
        for case in cases:
            breakdown = compute_confidence(
                kind=case["kind"],
                locator=case["locator"],
                independent_sources=case["sources"],
                occurred_at=utcnow() - timedelta(days=case["age_days"]),
            )
            inputs = breakdown.inputs
            sql_equivalent = (
                0.30 * inputs.source_authority
                + 0.15 * inputs.recency
                + 0.20 * inputs.specificity
                + 0.20 * min(1.0, 0.4 + 0.2 * inputs.corroboration_sources)
                + 0.15 * inputs.extraction_quality
            )
            assert abs(breakdown.score - sql_equivalent) < 0.002, case

    def test_contributions_sum_to_score(self) -> None:
        breakdown = compute_confidence(
            kind=EvidenceKind.COMMIT,
            locator=EvidenceLocator(sha="abc123"),
            independent_sources=2,
            occurred_at=utcnow() - timedelta(days=45),
        )
        assert sum(breakdown.contributions.values()) == pytest.approx(breakdown.score, abs=1e-6)

    def test_explanation_is_ordered_by_impact(self) -> None:
        breakdown = compute_confidence(kind=EvidenceKind.REPO_FILE, independent_sources=1)
        rows = breakdown.explanation()
        contributions = [row[2] for row in rows]
        assert contributions == sorted(contributions, reverse=True)

    def test_score_always_within_unit_interval(self) -> None:
        for sources in range(0, 8):
            for method in ("deterministic", "llm", "heuristic"):
                breakdown = compute_confidence(
                    kind=EvidenceKind.REPO_FILE,
                    locator=EvidenceLocator(path="x.c", line=1),
                    independent_sources=sources,
                    extraction_method=method,
                )
                assert 0.0 <= breakdown.score <= 1.0

    def test_llm_inference_with_no_sources_is_weak(self) -> None:
        breakdown = compute_confidence(
            kind=EvidenceKind.LLM_INFERENCE,
            locator=None,
            independent_sources=0,
            extraction_method="llm",
        )
        # 0.30·0.35 + 0.15·0.60 + 0.20·0.45 + 0.20·0.40 + 0.15·0.70 = 0.47
        assert breakdown.score == pytest.approx(0.47, abs=1e-6)
        assert breakdown.score < 0.75  # cannot carry a claim alone

    def test_custom_weights_are_honoured(self) -> None:
        breakdown = compute_confidence(
            kind=EvidenceKind.REPO_FILE,
            locator=EvidenceLocator(path="a.c", line=1),
            independent_sources=1,
            weights={
                "authority": 1.0,
                "recency": 0.0,
                "specificity": 0.0,
                "corroboration": 0.0,
                "extraction": 0.0,
            },
        )
        assert breakdown.score == pytest.approx(1.0, abs=1e-6)


class TestClaimGate:
    def test_high_confidence_with_two_sources_is_supported(self) -> None:
        assert classify_claim_status(0.90, 2) is ClaimStatus.SUPPORTED

    def test_high_confidence_but_one_source_is_only_partial(self) -> None:
        # One confident source is still one source — this is the rule that stops
        # a single README from carrying an entire resume line.
        assert classify_claim_status(0.95, 1) is ClaimStatus.PARTIALLY_SUPPORTED

    def test_mid_range_is_partial(self) -> None:
        assert classify_claim_status(0.60, 3) is ClaimStatus.PARTIALLY_SUPPORTED

    def test_low_range_is_unsupported(self) -> None:
        assert classify_claim_status(0.30, 5) is ClaimStatus.UNSUPPORTED

    def test_contradiction_overrides_everything(self) -> None:
        assert classify_claim_status(0.99, 9, contradicted=True) is ClaimStatus.CONTRADICTED

    def test_thresholds_are_configurable(self) -> None:
        assert (
            classify_claim_status(0.60, 1, supported_threshold=0.5, min_sources=1)
            is ClaimStatus.SUPPORTED
        )

    def test_status_helpers(self) -> None:
        assert ClaimStatus.SUPPORTED.allows_resume_inclusion is True
        assert ClaimStatus.PARTIALLY_SUPPORTED.allows_resume_inclusion is True
        assert ClaimStatus.UNSUPPORTED.allows_resume_inclusion is False
        assert ClaimStatus.UNSUPPORTED.is_blocking is True
        assert ClaimStatus.CONTRADICTED.is_blocking is True
        assert ClaimStatus.SUPPORTED.is_blocking is False


class TestQuantifiedClaims:
    def test_plain_claim_is_allowed(self) -> None:
        assert quantified_claim_allowed([], supported_sources=0, confidence=0.0) is True

    def test_quantified_claim_without_support_is_blocked(self) -> None:
        assert quantified_claim_allowed(["70%"], supported_sources=0, confidence=0.9) is False

    def test_quantified_claim_with_weak_confidence_is_blocked(self) -> None:
        assert quantified_claim_allowed(["2x"], supported_sources=1, confidence=0.30) is False

    def test_quantified_claim_with_support_and_confidence_is_allowed(self) -> None:
        assert quantified_claim_allowed(["70%"], supported_sources=2, confidence=0.80) is True
