"""Deterministic, explainable job-match scoring (``match@1.0.0``).

Five weighted dimensions::

    score = 0.40·skill + 0.25·experience + 0.20·project + 0.05·education + 0.10·evidence

Two design decisions carry most of the weight here.

**Claimed skill ≠ proven skill.** A skill the candidate lists but that has no
evidence is scored at 40% of its nominal level. This is what makes the Evidence
Strength dimension meaningful rather than decorative: padding a resume with
familiar-sounding keywords actively lowers your score.

**``gap`` and ``unknown`` are different facts.** "Your resume never mentions
CAN" is not the same as "you cannot do CAN". The classifier below only reports a
gap when there is a positive reason to believe the skill is absent, and
otherwise asks the user — see :func:`_classify_requirement`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from careerforge_ai.schemas.common import (
    GapLevel,
    RequirementLevel,
    SkillCategory,
    SkillLevel,
)
from careerforge_ai.schemas.job import JDAnalysis, JDSkill
from careerforge_ai.schemas.match import (
    JobMatchResult,
    MatchDimension,
    MatchDimensionKey,
    MatchedSkill,
    MatchWhy,
    MissedSkill,
    UnknownSkill,
)
from careerforge_ai.schemas.profile import CandidateProfile, ProfileSkill
from careerforge_ai.scoring.education import contains_skill, education_dimension
from careerforge_ai.scoring.weights import MATCH_FORMULA, MATCH_WEIGHTS

__all__ = [
    "DEFAULT_MATCH_WEIGHTS",
    "MATCH_ALGORITHM_VERSION",
    "MATCH_FORMULA",
    "UNPROVEN_SKILL_FACTOR",
    "compute_job_match",
]

MATCH_ALGORITHM_VERSION = "match@1.0.0"
#: Weights and the formula string live in :mod:`careerforge_ai.scoring.weights`,
#: so the API, the docs and this module cannot drift apart. The alias below is
#: kept because callers and tests refer to it by this name.
DEFAULT_MATCH_WEIGHTS: Mapping[str, float] = MATCH_WEIGHTS

#: A claimed-but-unproven skill counts for this share of its nominal level.
UNPROVEN_SKILL_FACTOR = 0.40

#: Evidence count at which a skill is considered fully evidenced.
_EVIDENCE_SATURATION = 3


def _round2(value: float) -> float:
    return round(float(value), 2)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _evidence_factor(evidence_count: int) -> float:
    """How much of a skill's nominal level its evidence actually supports.

    Zero pieces of evidence is not zero skill — the candidate may genuinely know
    it, they simply cannot prove it here. It is scored at
    :data:`UNPROVEN_SKILL_FACTOR` of the claimed level, which is a real penalty
    without pretending the skill is absent.
    """
    if evidence_count <= 0:
        return UNPROVEN_SKILL_FACTOR
    return min(1.0, 0.60 + 0.40 * min(1.0, evidence_count / _EVIDENCE_SATURATION))


def _effective_level(skill: ProfileSkill) -> float:
    return _clamp01(skill.level.numeric * _evidence_factor(skill.evidence_count))


def _classify_requirement(
    jd_skill: JDSkill,
    profile_skill: ProfileSkill | None,
    *,
    domain_active: bool,
) -> str:
    """Decide whether an unmet requirement is a ``gap`` or ``unknown``.

    Returns one of ``"met"``, ``"gap"`` or ``"unknown"``.

    The rules, in order:

    1. The candidate claims the skill **and** has evidence for it → ``met``.
    2. The candidate claims the skill but has no evidence → ``gap``. The claim
       is unproven, and that is a real risk in an interview.
    3. The candidate explicitly records level ``none`` → ``gap``. They told us.
    4. The candidate has evidenced skills in the same taxonomy category →
       ``gap``. They are demonstrably active in this domain and this specific
       item is missing.
    5. Otherwise → ``unknown``. There is no positive evidence either way, so the
       system asks instead of guessing.
    """
    if profile_skill is not None:
        if profile_skill.level is not SkillLevel.NONE:
            if profile_skill.evidence_count > 0:
                return "met"
            return "gap"
        return "gap"
    return "gap" if domain_active else "unknown"


def _severity(requirement: RequirementLevel) -> GapLevel:
    return {
        RequirementLevel.REQUIRED: GapLevel.HIGH,
        RequirementLevel.PREFERRED: GapLevel.MEDIUM,
        RequirementLevel.BONUS: GapLevel.LOW,
    }[requirement]


def _skill_dimension(
    job: JDAnalysis,
    profile: CandidateProfile,
    skill_evidence: Mapping[str, Sequence[UUID]],
    skill_confidence: Mapping[str, float],
    skill_categories: Mapping[str, SkillCategory],
) -> tuple[
    MatchDimension, list[MatchedSkill], list[MissedSkill], list[UnknownSkill], list[MatchedSkill]
]:
    """Score the skill dimension.

    Returns ``(dimension, advertised, gaps, unknowns, met)``. ``advertised`` holds the
    requirements strong enough to lead with (effective level ≥ 0.5); ``met`` holds every
    requirement the candidate satisfies, which is what the evidence dimension measures.
    """
    skills_by_id = {item.skill.canonical_id.lower(): item for item in profile.skills}
    evidenced_categories = {
        item.skill.category for item in profile.skills if item.evidence_count > 0
    }

    weighted_total = 0.0
    weight_sum = 0.0
    matched: list[MatchedSkill] = []
    met: list[MatchedSkill] = []
    gaps: list[MissedSkill] = []
    unknowns: list[UnknownSkill] = []
    evidence_ids: list[UUID] = []

    for jd_skill in job.all_skills:
        canonical = (jd_skill.canonical_id or "").lower()

        if not canonical:
            # Un-normalised skill: it cannot be scored, so it is excluded from
            # both numerator and denominator. Counting it as a miss would
            # penalise the candidate for the taxonomy's blind spot.
            continue

        requirement = jd_skill.requirement
        weight = requirement.weight * max(0.1, jd_skill.weight)
        weight_sum += weight

        profile_skill = skills_by_id.get(canonical)
        evidence = list(skill_evidence.get(canonical, ()))
        confidence = float(skill_confidence.get(canonical, 0.0))

        # "Domain-adjacent absence": the candidate is demonstrably active in this
        # taxonomy category, so an unseen item in the same category is a real gap
        # rather than an unknown. See _classify_requirement rule 4.
        domain_active = False
        if profile_skill is None:
            category = skill_categories.get(canonical)
            domain_active = category is not None and category in evidenced_categories

        verdict = _classify_requirement(jd_skill, profile_skill, domain_active=domain_active)
        effective = _effective_level(profile_skill) if profile_skill else 0.0

        if verdict == "met":
            weighted_total += weight * effective
            evidence_ids.extend(evidence)
            # Every met requirement is recorded, with its evidence — the evidence dimension
            # measures the requirements the candidate actually satisfies.
            met.append(
                MatchedSkill(
                    canonical_id=canonical,
                    display_name=profile_skill.skill.display_name if profile_skill else canonical,
                    requirement=requirement,
                    user_level=profile_skill.level if profile_skill else SkillLevel.NONE,
                    evidence_count=profile_skill.evidence_count if profile_skill else 0,
                    confidence=confidence,
                    reason=(f"{profile_skill.evidence_count} 条证据，置信度 {confidence:.2f}")
                    if profile_skill
                    else "",
                )
            )
            if effective >= 0.5:
                assert profile_skill is not None  # "met" implies the candidate has it
                matched.append(
                    MatchedSkill(
                        canonical_id=canonical,
                        display_name=profile_skill.skill.display_name,
                        requirement=requirement,
                        user_level=profile_skill.level,
                        evidence_count=profile_skill.evidence_count,
                        confidence=confidence,
                        reason=(f"{profile_skill.evidence_count} 条证据，置信度 {confidence:.2f}"),
                    )
                )
        elif verdict == "gap":
            gaps.append(
                MissedSkill(
                    canonical_id=canonical,
                    display_name=jd_skill.raw_text,
                    requirement=requirement,
                    severity=_severity(requirement),
                    jd_evidence=jd_skill.jd_evidence,
                )
            )
        else:
            unknowns.append(
                UnknownSkill(
                    canonical_id=canonical,
                    display_name=jd_skill.raw_text,
                    requirement=requirement,
                    reason="简历与证据图谱中均无相关信息",
                    ask_user=f"你是否接触过 {jd_skill.raw_text}？如有请补充证据。",
                )
            )

    if weight_sum > 0:
        coverage = weighted_total / weight_sum
    else:
        coverage = 1.0 if not job.all_skills else 0.0
    score = _round2(coverage * 100.0)

    dimension = MatchDimension(
        key=MatchDimensionKey.SKILL,
        label=MatchDimensionKey.LABELS[MatchDimensionKey.SKILL],
        score=score,
        weight=DEFAULT_MATCH_WEIGHTS[MatchDimensionKey.SKILL],
        weighted=_round2(score * DEFAULT_MATCH_WEIGHTS[MatchDimensionKey.SKILL]),
        formula="Σ(requirement_weight × effective_level) / Σ(requirement_weight)",
        notes=[
            f"required={RequirementLevel.REQUIRED.weight} / preferred={RequirementLevel.PREFERRED.weight}"
            f" / bonus={RequirementLevel.BONUS.weight}",
            f"无证据的技能按 {int(UNPROVEN_SKILL_FACTOR * 100)}% 计入",
        ],
        evidence_ids=evidence_ids[:200],
    )
    return dimension, matched, gaps, unknowns, met


def _experience_dimension(job: JDAnalysis, profile: CandidateProfile) -> MatchDimension:
    required_years = job.years_experience_min or 0.0
    actual_years = profile.years_experience or 0.0

    if required_years <= 0:
        years_ratio = 1.0
    else:
        years_ratio = min(1.0, actual_years / required_years)

    required_ids = {cid.lower() for cid in job.required_canonical_ids}
    relevant = 0
    for experience in profile.experiences:
        blob = " ".join([experience.title, experience.description, *experience.highlights])
        if any(contains_skill(blob, cid) for cid in required_ids if cid):
            relevant += 1
    relevance = min(1.0, relevant / 2.0) if profile.experiences else 0.0

    raw = 0.60 * years_ratio + 0.40 * relevance
    score = _round2(raw * 100.0)

    return MatchDimension(
        key=MatchDimensionKey.EXPERIENCE,
        label=MatchDimensionKey.LABELS[MatchDimensionKey.EXPERIENCE],
        score=score,
        weight=DEFAULT_MATCH_WEIGHTS[MatchDimensionKey.EXPERIENCE],
        weighted=_round2(score * DEFAULT_MATCH_WEIGHTS[MatchDimensionKey.EXPERIENCE]),
        formula="100 × (0.60 × min(1, years/required) + 0.40 × min(1, relevant_roles/2))",
        notes=[
            f"要求年限 {required_years:g}，候选人 {actual_years:g}",
            f"命中岗位技能的岗位相关经历数 {relevant}",
        ],
    )


def _project_dimension(job: JDAnalysis, profile: CandidateProfile) -> MatchDimension:
    required_ids = {cid.lower() for cid in job.required_canonical_ids if cid}
    if not required_ids:
        coverage = 1.0
    else:
        covered: set[str] = set()
        for project in profile.projects:
            blob = " ".join(
                [project.name, project.summary, project.description, *project.tech_stack]
            )
            for cid in required_ids:
                if contains_skill(blob, cid):
                    covered.add(cid)
        coverage = len(covered) / len(required_ids)

    strength_values = [project.evidence_strength.numeric for project in profile.projects]
    strength = sum(strength_values) / len(strength_values) if strength_values else 0.0

    raw = 0.60 * coverage + 0.40 * strength
    score = _round2(raw * 100.0)

    return MatchDimension(
        key=MatchDimensionKey.PROJECT,
        label=MatchDimensionKey.LABELS[MatchDimensionKey.PROJECT],
        score=score,
        weight=DEFAULT_MATCH_WEIGHTS[MatchDimensionKey.PROJECT],
        weighted=_round2(score * DEFAULT_MATCH_WEIGHTS[MatchDimensionKey.PROJECT]),
        formula="100 × (0.60 × 项目技能覆盖率 + 0.40 × 项目平均证据强度)",
        notes=[f"项目数 {len(profile.projects)}", f"平均证据强度 {strength:.2f}"],
    )


def _evidence_dimension(
    matched: Sequence[MatchedSkill],
    skill_confidence: Mapping[str, float],
) -> tuple[MatchDimension, float]:
    confidences = [float(skill_confidence.get(item.canonical_id.lower(), 0.0)) for item in matched]
    if confidences:
        mean_confidence = sum(confidences) / len(confidences)
    else:
        mean_confidence = 0.0

    # Coverage penalises "required but unevidenced" requirements, which is the
    # dimension's entire reason for existing.
    coverage = (
        sum(1 for item in matched if item.evidence_count > 0) / len(matched) if matched else 0.0
    )
    raw = 0.65 * mean_confidence + 0.35 * coverage
    score = _round2(_clamp01(raw) * 100.0)

    dimension = MatchDimension(
        key=MatchDimensionKey.EVIDENCE,
        label=MatchDimensionKey.LABELS[MatchDimensionKey.EVIDENCE],
        score=score,
        weight=DEFAULT_MATCH_WEIGHTS[MatchDimensionKey.EVIDENCE],
        weighted=_round2(score * DEFAULT_MATCH_WEIGHTS[MatchDimensionKey.EVIDENCE]),
        formula="100 × (0.65 × 命中技能平均置信度 + 0.35 × 有证据的命中比例)",
        notes=[f"命中技能 {len(matched)} 个，平均置信度 {mean_confidence:.2f}"],
    )
    return dimension, coverage


def compute_job_match(
    *,
    job: JDAnalysis,
    profile: CandidateProfile,
    skill_evidence: Mapping[str, Sequence[UUID]] | None = None,
    skill_confidence: Mapping[str, float] | None = None,
    skill_categories: Mapping[str, SkillCategory] | None = None,
    weights: Mapping[str, float] | None = None,
) -> JobMatchResult:
    """Score a candidate against a job description, deterministically.

    Args:
        job: structured job analysis.
        profile: structured candidate profile, with per-skill evidence counts.
        skill_evidence: canonical skill id → evidence ids backing it.
        skill_confidence: canonical skill id → mean evidence confidence.
        skill_categories: canonical skill id → taxonomy category, used only to
            distinguish a genuine gap from an unknown (see
            :func:`_classify_requirement`).
        weights: optional weight override across the five dimension keys.

    Returns:
        A :class:`JobMatchResult` carrying the score *and* its full derivation.
    """
    evidence_map = skill_evidence or {}
    confidence_map = {k.lower(): v for k, v in (skill_confidence or {}).items()}
    category_map = {k.lower(): v for k, v in (skill_categories or {}).items()}

    skill_dim, matched, gaps, unknowns, met = _skill_dimension(
        job, profile, evidence_map, confidence_map, category_map
    )
    experience_dim = _experience_dimension(job, profile)
    project_dim = _project_dimension(job, profile)
    education_dim = education_dimension(job, profile)
    # Measured over *met* requirements, not over the highlighted ones. ``matched`` is
    # filtered to the skills strong enough to advertise (effective level ≥ 0.5), and using
    # that list here made the dimension read 0.00 for a candidate who satisfies five
    # requirements with real evidence behind them.
    evidence_dim, evidence_coverage = _evidence_dimension(met, confidence_map)

    dimensions = {
        MatchDimensionKey.SKILL: skill_dim,
        MatchDimensionKey.EXPERIENCE: experience_dim,
        MatchDimensionKey.PROJECT: project_dim,
        MatchDimensionKey.EDUCATION: education_dim,
        MatchDimensionKey.EVIDENCE: evidence_dim,
    }

    total = _round2(sum(dim.weighted for dim in dimensions.values()))

    strongest = sorted(matched, key=lambda item: item.confidence, reverse=True)[:6]
    top_gaps = sorted(
        gaps,
        key=lambda gap: {GapLevel.HIGH: 0, GapLevel.MEDIUM: 1, GapLevel.LOW: 2, GapLevel.NONE: 3}[
            gap.severity
        ],
    )[:8]

    notes = [
        f"命中要求技能 {len(matched)} 个，缺口 {len(gaps)} 个，待确认 {len(unknowns)} 个",
    ]
    if any(gap.requirement is RequirementLevel.REQUIRED for gap in gaps):
        notes.append("存在必备技能缺口，证据强度维度已相应扣分")

    evidence_used: list[UUID] = []
    for dim in dimensions.values():
        evidence_used.extend(dim.evidence_ids)
    deduped_evidence = list(dict.fromkeys(evidence_used))

    why = MatchWhy(
        formula=MATCH_FORMULA,
        dimensions=list(dimensions.values()),
        evidence_used=deduped_evidence,
        notes=notes,
        algorithm_version=MATCH_ALGORITHM_VERSION,
        explanation=(
            f"技能维度 {skill_dim.score:.0f} 分（权重 {skill_dim.weight:.0%}）"
            f"，证据强度 {evidence_dim.score:.0f} 分，"
            f"加权合计 {total:.1f} 分。"
        ),
    )

    return JobMatchResult(
        score=total,
        dimensions=dimensions,
        strengths=strongest,
        gaps=top_gaps,
        unknowns=unknowns,
        why=why,
        evidence_coverage=_round2(evidence_coverage),
        confidence=_round2(
            sum(item.confidence for item in matched) / len(matched) if matched else 0.0
        ),
    )
