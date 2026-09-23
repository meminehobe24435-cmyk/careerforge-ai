"""Tests for the deterministic scoring engines.

Two properties are non-negotiable and are therefore tested explicitly:

1. **Reproducibility** — the same inputs must always produce the same score.
   A match percentage that drifts between runs destroys user trust and makes
   regression testing impossible.
2. **Gaps are not unknowns** — "your resume does not mention it" and "you cannot
   do it" are different facts, and conflating them is exactly the kind of
   automated judgement this product exists to avoid.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from careerforge_ai.schemas.common import GapLevel, RequirementLevel, SkillCategory
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.match import MatchDimensionKey
from careerforge_ai.schemas.profile import CandidateProfile
from careerforge_ai.scoring.match import DEFAULT_MATCH_WEIGHTS, compute_job_match
from careerforge_ai.scoring.profile_strength import EvidenceStats, compute_profile_strength
from careerforge_ai.scoring.skill_gap import compute_skill_gap_matrix

_SKILL_CATEGORIES = {
    "can": SkillCategory.EMBEDDED,
    "kubernetes": SkillCategory.DEVOPS,
    "autosar": SkillCategory.EMBEDDED,
    "python": SkillCategory.LANGUAGE,
    "stm32": SkillCategory.EMBEDDED,
    "free_rtos": SkillCategory.EMBEDDED,
    "c": SkillCategory.LANGUAGE,
}

_SKILL_CONFIDENCE = {"stm32": 0.95, "free_rtos": 0.90, "c": 0.88}


class TestMatchWeights:
    def test_weights_sum_to_one(self) -> None:
        assert abs(sum(DEFAULT_MATCH_WEIGHTS.values()) - 1.0) < 1e-9

    def test_skill_match_is_the_heaviest_dimension(self) -> None:
        assert DEFAULT_MATCH_WEIGHTS[MatchDimensionKey.SKILL] == max(DEFAULT_MATCH_WEIGHTS.values())


class TestJobMatch:
    @pytest.fixture
    def result(self, candidate_profile: CandidateProfile, embedding_jd: JDAnalysis):
        return compute_job_match(
            job=embedding_jd,
            profile=candidate_profile,
            skill_confidence=_SKILL_CONFIDENCE,
            skill_categories=_SKILL_CATEGORIES,
        )

    def test_is_reproducible(
        self, candidate_profile: CandidateProfile, embedding_jd: JDAnalysis
    ) -> None:
        first = compute_job_match(
            job=embedding_jd, profile=candidate_profile, skill_categories=_SKILL_CATEGORIES
        )
        second = compute_job_match(
            job=embedding_jd, profile=candidate_profile, skill_categories=_SKILL_CATEGORIES
        )
        assert first.score == second.score
        assert [d.score for d in first.dimensions.values()] == [
            d.score for d in second.dimensions.values()
        ]

    def test_weighted_dimensions_sum_to_the_total(self, result) -> None:
        assert sum(dim.weighted for dim in result.dimensions.values()) == pytest.approx(
            result.score, abs=0.01
        )

    def test_why_payload_is_complete(self, result) -> None:
        assert result.why.formula
        assert len(result.why.dimensions) == 5
        assert result.why.explanation
        assert result.why.algorithm_version == "match@1.0.0"
        for dimension in result.why.dimensions:
            assert dimension.formula
            assert dimension.label

    def test_evidenced_required_skills_become_strengths(self, result) -> None:
        strengths = {item.canonical_id for item in result.strengths}
        assert {"stm32", "free_rtos", "c"} <= strengths

    def test_absent_required_skill_in_an_active_domain_is_a_gap(self, result) -> None:
        # CAN is embedded; the candidate demonstrably has embedded evidence, so
        # the absence is a real gap rather than an unknown.
        gaps = {item.canonical_id for item in result.gaps}
        assert "can" in gaps
        assert "kubernetes" not in gaps

    def test_absent_required_skill_in_an_inactive_domain_is_unknown(self, result) -> None:
        # The candidate has no DevOps evidence at all, so the system must ask
        # rather than assume incompetence.
        unknowns = {item.canonical_id for item in result.unknowns}
        assert "kubernetes" in unknowns
        unknown = next(item for item in result.unknowns if item.canonical_id == "kubernetes")
        assert unknown.ask_user
        assert "Kubernetes" in unknown.ask_user

    def test_gaps_and_unknowns_are_disjoint(self, result) -> None:
        gap_ids = {item.canonical_id for item in result.gaps}
        unknown_ids = {item.canonical_id for item in result.unknowns}
        assert gap_ids.isdisjoint(unknown_ids)

    def test_claimed_but_unevidenced_skill_is_penalised_and_reported(self, result) -> None:
        # Python is claimed at moderate level with zero evidence. It must not
        # count as a strength, and it must be surfaced as an unproven claim.
        strengths = {item.canonical_id for item in result.strengths}
        assert "python" not in strengths
        python_gap = next((gap for gap in result.gaps if gap.canonical_id == "python"), None)
        assert python_gap is not None

    def test_evidence_dimension_reflects_missing_evidence(self, result) -> None:
        evidence_dim = result.dimensions[MatchDimensionKey.EVIDENCE]
        assert 0 < evidence_dim.score < 100
        assert "平均置信度" in " ".join(evidence_dim.notes)

    def test_unproven_skill_lowers_the_score_versus_a_proven_one(
        self, candidate_profile: CandidateProfile, embedding_jd: JDAnalysis
    ) -> None:
        from careerforge_ai.schemas.common import SkillLevel

        proven = compute_job_match(
            job=embedding_jd, profile=candidate_profile, skill_categories=_SKILL_CATEGORIES
        )

        # Give Python a strong claim with evidence and it should score higher.
        python_skill = candidate_profile.skill_by_canonical_id("python")
        assert python_skill is not None
        python_skill.level = SkillLevel.STRONG
        python_skill.evidence_count = 4
        python_skill.evidence_score = 0.9

        improved = compute_job_match(
            job=embedding_jd, profile=candidate_profile, skill_categories=_SKILL_CATEGORIES
        )
        assert improved.score > proven.score

    def test_rejects_an_absurd_score(self, candidate_profile: CandidateProfile) -> None:
        empty_job = JDAnalysis(role="Unknown Role")
        result = compute_job_match(job=empty_job, profile=candidate_profile)
        assert 0.0 <= result.score <= 100.0

    def test_education_dimension_handles_chinese_requirements(
        self, candidate_profile: CandidateProfile, embedding_jd: JDAnalysis
    ) -> None:
        result = compute_job_match(job=embedding_jd, profile=candidate_profile)
        # 本科 requirement vs a Bachelor's degree must be recognised as met.
        assert result.dimensions[MatchDimensionKey.EDUCATION].score == 100.0


class TestSkillGapMatrix:
    @pytest.fixture
    def matrix(self, candidate_profile: CandidateProfile, embedding_jd: JDAnalysis):
        evidence_ids = {"stm32": [uuid4(), uuid4()]}
        return compute_skill_gap_matrix(
            job=embedding_jd,
            profile=candidate_profile,
            skill_categories=_SKILL_CATEGORIES,
            evidence_by_skill=evidence_ids,
            skill_confidence=_SKILL_CONFIDENCE,
            market_frequency={"can": 0.8, "autosar": 0.4},
        )

    def test_rows_are_ordered_by_priority_descending(self, matrix) -> None:
        priorities = [row.priority for row in matrix.rows]
        assert priorities == sorted(priorities, reverse=True)

    def test_high_requirement_gaps_outrank_bonus_gaps(self, matrix) -> None:
        by_id = {row.canonical_id: row for row in matrix.rows}
        assert by_id["can"].priority > by_id["autosar"].priority
        assert by_id["can"].gap_level is GapLevel.HIGH

    def test_market_frequency_raises_priority(
        self, candidate_profile: CandidateProfile, embedding_jd: JDAnalysis
    ) -> None:
        without = compute_skill_gap_matrix(
            job=embedding_jd, profile=candidate_profile, skill_categories=_SKILL_CATEGORIES
        )
        with_market = compute_skill_gap_matrix(
            job=embedding_jd,
            profile=candidate_profile,
            skill_categories=_SKILL_CATEGORIES,
            market_frequency={"can": 1.0},
        )
        can_without = next(row for row in without.rows if row.canonical_id == "can")
        can_with = next(row for row in with_market.rows if row.canonical_id == "can")
        assert can_with.priority > can_without.priority

    def test_met_requirement_has_no_gap(self, matrix) -> None:
        stm32 = next(row for row in matrix.rows if row.canonical_id == "stm32")
        assert stm32.gap_level is GapLevel.NONE
        assert "满足" in stm32.rationale

    def test_unproven_claim_is_explained(self, matrix) -> None:
        python_row = next(row for row in matrix.rows if row.canonical_id == "python")
        assert python_row.gap_level is not GapLevel.NONE
        assert "没有" in python_row.rationale or "证据" in python_row.rationale

    def test_duplicate_requirement_rows_are_collapsed(
        self, candidate_profile: CandidateProfile
    ) -> None:
        from careerforge_ai.schemas.job import JDSkill

        job = JDAnalysis(
            role="dup",
            required_skills=[
                JDSkill(canonical_id="can", raw_text="CAN", requirement=RequirementLevel.REQUIRED),
                JDSkill(
                    canonical_id="can", raw_text="CAN 总线", requirement=RequirementLevel.REQUIRED
                ),
            ],
        )
        matrix = compute_skill_gap_matrix(job=job, profile=candidate_profile)
        assert len([row for row in matrix.rows if row.canonical_id == "can"]) == 1


class TestProfileStrength:
    def test_score_is_within_bounds(self, candidate_profile: CandidateProfile) -> None:
        strength = compute_profile_strength(
            profile=candidate_profile,
            stats=EvidenceStats(
                total_evidence=180, mean_confidence=0.82, high_confidence_count=90, distinct_kinds=5
            ),
        )
        assert 0.0 <= strength.score <= 100.0

    def test_dimensions_sum_to_the_score(self, candidate_profile: CandidateProfile) -> None:
        strength = compute_profile_strength(profile=candidate_profile, stats=EvidenceStats())
        assert sum(dim.weighted for dim in strength.dimensions) == pytest.approx(
            strength.score, abs=0.05
        )

    def test_weights_sum_to_one(self, candidate_profile: CandidateProfile) -> None:
        strength = compute_profile_strength(profile=candidate_profile)
        assert sum(dim.weight for dim in strength.dimensions) == pytest.approx(1.0)

    def test_evidence_raises_the_score(self, candidate_profile: CandidateProfile) -> None:
        low = compute_profile_strength(profile=candidate_profile, stats=EvidenceStats())
        high = compute_profile_strength(
            profile=candidate_profile,
            stats=EvidenceStats(
                total_evidence=200,
                mean_confidence=0.9,
                high_confidence_count=150,
                distinct_kinds=6,
                repository_count=4,
                significant_file_count=30,
                significant_commit_count=40,
                language_count=4,
                has_readme=True,
            ),
        )
        assert high.score > low.score

    def test_empty_profile_scores_low_but_does_not_crash(self) -> None:
        strength = compute_profile_strength(profile=CandidateProfile())
        assert 0.0 <= strength.score < 40.0

    def test_suggestions_are_ordered_by_impact(self, candidate_profile: CandidateProfile) -> None:
        strength = compute_profile_strength(profile=candidate_profile, stats=EvidenceStats())
        impacts = [float(item.get("impact", 0.0)) for item in strength.suggestions]
        assert impacts == sorted(impacts, reverse=True)

    def test_unevidenced_skills_produce_a_suggestion(
        self, candidate_profile: CandidateProfile
    ) -> None:
        strength = compute_profile_strength(profile=candidate_profile, stats=EvidenceStats())
        assert any("证据" in str(item.get("action", "")) for item in strength.suggestions)

    def test_missing_github_produces_a_suggestion(
        self, candidate_profile: CandidateProfile
    ) -> None:
        strength = compute_profile_strength(profile=candidate_profile, stats=EvidenceStats())
        assert any("GitHub" in str(item.get("action", "")) for item in strength.suggestions)

    def test_evidence_coverage_counts_only_claimed_skills(
        self, candidate_profile: CandidateProfile
    ) -> None:
        strength = compute_profile_strength(profile=candidate_profile, stats=EvidenceStats())
        coverage = strength.dimension("evidence_coverage")
        assert coverage is not None
        # 3 of 4 claimed skills carry evidence.
        assert coverage.raw == pytest.approx(0.75)
