"""Profile Strength — the dashboard's headline number, and how to raise it.

The score is deliberately decomposed into five weighted dimensions, each of
which emits a concrete next action. A single opaque number tells a user nothing
they can act on; a breakdown tells them exactly which gap to close first.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from careerforge_ai.schemas.profile import (
    CandidateProfile,
    ProfileStrength,
    ProfileStrengthDimension,
)

__all__ = ["STRENGTH_ALGORITHM_VERSION", "EvidenceStats", "compute_profile_strength"]

STRENGTH_ALGORITHM_VERSION = "strength@1.0.0"

_DIMENSION_WEIGHTS: dict[str, float] = {
    "completeness": 0.30,
    "evidence_coverage": 0.25,
    "evidence_quality": 0.20,
    "github_signal": 0.15,
    "achievement_bonus": 0.10,
}

_LABELS: dict[str, str] = {
    "completeness": "资料完整度",
    "evidence_coverage": "证据覆盖率",
    "evidence_quality": "证据质量",
    "github_signal": "GitHub 信号",
    "achievement_bonus": "成果加分",
}


@dataclass(slots=True)
class EvidenceStats:
    """Aggregate evidence statistics needed by the strength engine.

    Passed in rather than queried so this module stays a pure function
    (ADR-022) and can be unit-tested without a database.
    """

    total_evidence: int = 0
    mean_confidence: float = 0.0
    high_confidence_count: int = 0
    distinct_kinds: int = 0
    repository_count: int = 0
    significant_file_count: int = 0
    significant_commit_count: int = 0
    language_count: int = 0
    starred_repo_count: int = 0
    has_readme: bool = False
    commits_sampled: int = 0
    extra: dict[str, float] = field(default_factory=dict)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _completeness(profile: CandidateProfile) -> float:
    """Weighted presence of the sections a complete profile needs."""
    checks = (
        (0.18, bool(profile.headline.strip())),
        (0.14, len(profile.summary.strip()) >= 40),
        (0.12, bool(profile.target_roles)),
        (0.14, bool(profile.educations)),
        (0.18, bool(profile.experiences)),
        (0.18, bool(profile.projects)),
        (0.06, profile.years_experience is not None),
    )
    return _clamp01(sum(weight for weight, present in checks if present))


def _evidence_coverage(profile: CandidateProfile) -> float:
    claimed = profile.claimed_skill_ids
    if not claimed:
        return 0.0
    evidenced = profile.evidenced_skill_ids & claimed
    return _clamp01(len(evidenced) / len(claimed))


def _evidence_quality(stats: EvidenceStats) -> float:
    if stats.total_evidence <= 0:
        return 0.0
    # Mean confidence dominates; breadth of source kinds and a healthy share of
    # strong evidence both add, so a single kind cannot carry the whole score.
    breadth = _clamp01(stats.distinct_kinds / 5.0)
    strong_share = _clamp01(stats.high_confidence_count / stats.total_evidence)
    volume = _clamp01(stats.total_evidence / 40.0)
    return _clamp01(
        0.55 * _clamp01(stats.mean_confidence)
        + 0.20 * breadth
        + 0.15 * strong_share
        + 0.10 * volume
    )


def _github_signal(stats: EvidenceStats) -> float:
    if stats.repository_count <= 0:
        return 0.0
    repos = _clamp01(stats.repository_count / 4.0)
    files = _clamp01(stats.significant_file_count / 20.0)
    commits = _clamp01(stats.significant_commit_count / 15.0)
    languages = _clamp01(stats.language_count / 4.0)
    readme = 1.0 if stats.has_readme else 0.0
    stars = _clamp01(stats.starred_repo_count / 3.0)
    return _clamp01(
        0.30 * repos
        + 0.22 * files
        + 0.18 * commits
        + 0.12 * languages
        + 0.10 * readme
        + 0.08 * stars
    )


def _achievement_bonus(profile: CandidateProfile) -> float:
    count = len(profile.achievements)
    if count == 0:
        return 0.0
    # Strongly-evidenced achievements count double: an award you can point at is
    # worth more than one you merely list.
    weighted = sum(
        1.0 + achievement.evidence_strength.numeric for achievement in profile.achievements
    )
    return _clamp01(weighted / 6.0)


def _suggestions(
    profile: CandidateProfile,
    stats: EvidenceStats,
    raw_scores: dict[str, float],
) -> list[dict[str, object]]:
    """Concrete, ordered next actions with an estimated point impact."""
    suggestions: list[dict[str, object]] = []

    unevidenced = sorted(profile.claimed_skill_ids - profile.evidenced_skill_ids)
    if unevidenced:
        suggestions.append(
            {
                "action": f"为 {len(unevidenced)} 个声明的技能补充证据",
                "skills": unevidenced[:5],
                "dimension": "evidence_coverage",
                "impact": round(_DIMENSION_WEIGHTS["evidence_coverage"] * 100 * 0.25, 1),
                "how": "把相关代码推到 GitHub、补充项目文档，或在项目中说明使用场景",
            }
        )

    if not profile.experiences:
        suggestions.append(
            {
                "action": "补充实习或科研经历",
                "dimension": "completeness",
                "impact": round(_DIMENSION_WEIGHTS["completeness"] * 100 * 0.18, 1),
                "how": "上传含实习经历的简历，或在 Profile 页手动添加",
            }
        )

    if stats.repository_count == 0:
        suggestions.append(
            {
                "action": "绑定 GitHub 账号",
                "dimension": "github_signal",
                "impact": round(_DIMENSION_WEIGHTS["github_signal"] * 100 * 0.60, 1),
                "how": "在 GitHub Intelligence 页输入用户名，系统会自动提取代码级证据",
            }
        )
    elif stats.significant_file_count < 10:
        suggestions.append(
            {
                "action": "提高仓库的可分析程度",
                "dimension": "github_signal",
                "impact": round(_DIMENSION_WEIGHTS["github_signal"] * 100 * 0.22, 1),
                "how": "确保核心源码已提交（非仅 README），关键文件包含清晰的函数与注释",
            }
        )

    if stats.total_evidence > 0 and stats.mean_confidence < 0.70:
        suggestions.append(
            {
                "action": "提升现有证据的置信度",
                "dimension": "evidence_quality",
                "impact": round(_DIMENSION_WEIGHTS["evidence_quality"] * 100 * 0.30, 1),
                "how": "证据强度取决于来源权威性与可定位性：补充 commit、精确到文件与行号、多来源交叉印证",
            }
        )

    suggestions.append(
        {
            "action": "针对目标岗位生成一次匹配分析",
            "dimension": "completeness",
            "impact": 0.0,
            "how": "岗位匹配会指出最值得补齐的技能，是提升 Profile Strength 的最快路径",
        }
    )

    suggestions.sort(key=_impact_of, reverse=True)
    return suggestions


def _impact_of(row: dict[str, object]) -> float:
    """Sort key for a suggestion row.

    Rows carry mixed value types (strings, a list of skills, a float impact), so the
    key is narrowed rather than converted blindly. A row without a usable ``impact``
    sorts last instead of raising, because advice without an estimate is still advice.
    """
    value = row.get("impact", 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def compute_profile_strength(
    *,
    profile: CandidateProfile,
    stats: EvidenceStats | None = None,
) -> ProfileStrength:
    """Compute the 0–100 Profile Strength score with a full breakdown."""
    evidence_stats = stats or EvidenceStats()

    raw_scores = {
        "completeness": _completeness(profile),
        "evidence_coverage": _evidence_coverage(profile),
        "evidence_quality": _evidence_quality(evidence_stats),
        "github_signal": _github_signal(evidence_stats),
        "achievement_bonus": _achievement_bonus(profile),
    }

    dimensions: list[ProfileStrengthDimension] = []
    total = 0.0
    for key, weight in _DIMENSION_WEIGHTS.items():
        raw = _clamp01(raw_scores[key])
        weighted = round(raw * weight * 100.0, 2)
        total += weighted
        dimensions.append(
            ProfileStrengthDimension(
                key=key,
                label=_LABELS[key],
                raw=round(raw, 4),
                weight=weight,
                weighted=weighted,
                hint=None,
            )
        )

    return ProfileStrength(
        score=round(min(100.0, total), 1),
        dimensions=dimensions,
        suggestions=_suggestions(profile, evidence_stats, raw_scores),
        formula_version=STRENGTH_ALGORITHM_VERSION,
    )
