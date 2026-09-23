"""Skill gap analysis and gap prioritisation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from careerforge_ai.schemas.common import (
    EvidenceStrength,
    GapLevel,
    RequirementLevel,
    SkillCategory,
    SkillLevel,
)
from careerforge_ai.schemas.job import JDAnalysis, SkillGapMatrix, SkillGapRow
from careerforge_ai.schemas.profile import CandidateProfile

__all__ = ["GAP_ALGORITHM_VERSION", "compute_skill_gap_matrix"]

GAP_ALGORITHM_VERSION = "gap@1.0.0"

_EVIDENCE_STRENGTH_FROM_CONFIDENCE = (
    (0.80, EvidenceStrength.HIGH),
    (0.60, EvidenceStrength.MEDIUM),
    (0.35, EvidenceStrength.LOW),
)


def _evidence_strength(evidence_count: int, mean_confidence: float) -> EvidenceStrength:
    if evidence_count <= 0:
        return EvidenceStrength.NONE
    for threshold, strength in _EVIDENCE_STRENGTH_FROM_CONFIDENCE:
        if mean_confidence >= threshold:
            return strength
    return EvidenceStrength.LOW


def _gap_level(
    requirement: RequirementLevel,
    level: SkillLevel,
    strength: EvidenceStrength,
    *,
    present: bool,
) -> GapLevel:
    """Gap severity from requirement weight, claimed level and evidence strength.

    Evidence strength dominates: a skill claimed at ``expert`` with no evidence
    is a *bigger* risk than one claimed at ``basic`` with none, because the claim
    invites a harder interview question than the candidate can survive.
    """
    if not present:
        return {
            RequirementLevel.REQUIRED: GapLevel.HIGH,
            RequirementLevel.PREFERRED: GapLevel.MEDIUM,
            RequirementLevel.BONUS: GapLevel.LOW,
        }[requirement]

    if strength is EvidenceStrength.NONE:
        # Claimed but unprovable.
        return GapLevel.HIGH if requirement is RequirementLevel.REQUIRED else GapLevel.MEDIUM

    if requirement is RequirementLevel.REQUIRED:
        if strength is EvidenceStrength.HIGH and level.numeric >= 0.55:
            return GapLevel.NONE
        if level.numeric >= 0.55:
            return GapLevel.LOW
        return GapLevel.MEDIUM

    if requirement is RequirementLevel.PREFERRED:
        return GapLevel.NONE if strength is not EvidenceStrength.LOW else GapLevel.LOW

    return GapLevel.NONE


def compute_skill_gap_matrix(
    *,
    job: JDAnalysis,
    profile: CandidateProfile,
    skill_categories: Mapping[str, SkillCategory] | None = None,
    evidence_by_skill: Mapping[str, Sequence[UUID]] | None = None,
    skill_confidence: Mapping[str, float] | None = None,
    market_frequency: Mapping[str, float] | None = None,
) -> SkillGapMatrix:
    """Build the skill gap matrix for one job.

    Priority blends three things, all deterministic:

    ``priority = 0.50 × requirement_weight + 0.30 × gap_severity + 0.20 × market_frequency``

    ``market_frequency`` is the share of *the user's own tracked jobs* in the same
    category that require the skill. It is real data from their pipeline, not a
    hard-coded guess about the labour market.
    """
    categories = {k.lower(): v for k, v in (skill_categories or {}).items()}
    evidence_map = {k.lower(): list(v) for k, v in (evidence_by_skill or {}).items()}
    confidence_map = {k.lower(): v for k, v in (skill_confidence or {}).items()}
    frequency_map = {k.lower(): v for k, v in (market_frequency or {}).items()}

    skills_by_id = {item.skill.canonical_id.lower(): item for item in profile.skills}
    evidenced_categories = {
        item.skill.category for item in profile.skills if item.evidence_count > 0
    }

    rows: list[SkillGapRow] = []
    seen: set[tuple[str, str]] = set()

    for jd_skill in job.all_skills:
        canonical = (jd_skill.canonical_id or "").lower()
        if not canonical:
            continue
        key = (canonical, jd_skill.requirement.value)
        if key in seen:
            continue
        seen.add(key)

        profile_skill = skills_by_id.get(canonical)
        evidence_ids = evidence_map.get(canonical, [])
        mean_confidence = float(confidence_map.get(canonical, 0.0))

        present = profile_skill is not None and profile_skill.level is not SkillLevel.NONE
        level = profile_skill.level if profile_skill else SkillLevel.NONE
        evidence_count = profile_skill.evidence_count if profile_skill else len(evidence_ids)
        strength = _evidence_strength(evidence_count, mean_confidence)

        # Domain adjacency decides whether an unseen skill is a real gap or
        # something we simply cannot judge. The same rule is used by the match
        # engine so the Match page and the Gap page never contradict each other.
        category = categories.get(canonical)
        domain_active = category is not None and category in evidenced_categories
        unconfirmed = not present and not domain_active

        gap = _gap_level(jd_skill.requirement, level, strength, present=present)
        if unconfirmed:
            # Not confirmed as missing: keep it visible but do not let it top the
            # action list, because we do not yet know that it is a gap at all.
            gap = GapLevel.LOW

        frequency = max(0.0, min(1.0, frequency_map.get(canonical, 0.0)))

        priority = 100.0 * (
            0.50 * jd_skill.requirement.weight + 0.30 * gap.numeric + 0.20 * frequency
        )

        if unconfirmed:
            rationale = (
                f"无法判定：简历与证据图谱中均无 {jd_skill.raw_text} 相关信息，"
                "请先确认是否接触过，再决定是否需要补强"
            )
        elif gap is GapLevel.NONE:
            rationale = "已满足要求且证据充分"
        elif not present:
            rationale = (
                f"岗位要求 {jd_skill.raw_text}，且你在此技术方向已有其他证据，唯独缺少这一项"
            )
        elif strength is EvidenceStrength.NONE:
            rationale = f"简历声明了 {jd_skill.raw_text}，但没有任何证据可证明"
        else:
            rationale = (
                f"已声明 {jd_skill.raw_text}（证据强度 {strength.value}），低于该岗位的期望水平"
            )

        rows.append(
            SkillGapRow(
                canonical_id=canonical,
                display_name=(
                    profile_skill.skill.display_name if profile_skill else jd_skill.raw_text
                ),
                requirement=jd_skill.requirement,
                user_level=level,
                evidence_strength=strength,
                gap_level=gap,
                priority=round(priority, 2),
                rationale=rationale,
                jd_mentions=jd_skill.mentions,
                evidence_ids=evidence_ids[:50],
            )
        )

    rows.sort(key=lambda row: (-row.priority, row.canonical_id))

    return SkillGapMatrix(
        job_id=None,
        company=job.company,
        role=job.role,
        rows=rows,
        algorithm_version=GAP_ALGORITHM_VERSION,
    )
