"""Education matching: degree-level comparison between a job and a candidate.

Extracted from the match engine because it answers a different question from the
rest of the scoring: not "how much of this can you do" but "do you clear the
stated bar". It also carries the degree vocabulary for both English and Chinese
JDs, which is data rather than logic.
"""

from __future__ import annotations

from collections.abc import Mapping
import re

from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.match import MatchDimension, MatchDimensionKey
from careerforge_ai.schemas.profile import CandidateProfile
from careerforge_ai.scoring.weights import MATCH_WEIGHTS

__all__ = ["DEGREE_RANK", "contains_skill", "degree_rank", "education_dimension", "round2"]

#: Ranked degree vocabulary. Chinese JDs state the requirement in Chinese, so the
#: mapping has to cover both languages or every Chinese JD would fall through to
#: the "cannot parse" branch.
DEGREE_RANK: Mapping[str, int] = {
    "associate": 1,
    "diploma": 1,
    "high school": 1,
    "bachelor": 2,
    "bsc": 2,
    "ba": 2,
    "undergraduate": 2,
    "master": 3,
    "msc": 3,
    "ma": 3,
    "graduate": 3,
    "phd": 4,
    "doctorate": 4,
    "大专": 1,
    "专科": 1,
    "中专": 1,
    "本科": 2,
    "学士": 2,
    "硕士": 3,
    "研究生": 3,
    "博士": 4,
}

#: Scores for each outcome of the comparison. Kept as named constants so the
#: rationale strings and the numbers cannot drift apart.
SCORE_NO_REQUIREMENT = 100.0
SCORE_UNPARSEABLE = 85.0
SCORE_MET = 100.0
SCORE_SLIGHTLY_BELOW = 60.0
SCORE_BELOW = 30.0


def round2(value: float) -> float:
    return round(float(value), 2)


def contains_skill(blob: str, canonical_id: str) -> bool:
    """Whether ``blob`` mentions a skill as a whole token.

    Word-boundary matching matters more than it looks: a substring test makes the
    one-letter skill ``c`` match inside "balance", "docker" and "class", quietly
    inflating project coverage. Taxonomy ids are ASCII slugs, so a boundary regex
    is both correct and cheap.
    """
    if not canonical_id:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(canonical_id)}(?![a-z0-9])"
    return re.search(pattern, blob, re.IGNORECASE) is not None


def degree_rank(text: str) -> int:
    """Highest degree level mentioned in ``text``, or 0 when nothing is recognised."""
    lowered = text.lower()
    rank = 0
    for token, value in DEGREE_RANK.items():
        if token in lowered:
            rank = max(rank, value)
    return rank


def education_dimension(job: JDAnalysis, profile: CandidateProfile) -> MatchDimension:
    """Compare stated education requirements. Missing data is never punished."""
    requirement_text = (job.education_requirement or "").strip()

    if not requirement_text:
        score = SCORE_NO_REQUIREMENT
        note = "岗位未提出学历要求，不扣分"
    else:
        required_rank = degree_rank(requirement_text)
        candidate_rank = max(
            (degree_rank(education.degree or "") for education in profile.educations),
            default=0,
        )

        if required_rank == 0:
            score = SCORE_UNPARSEABLE
            note = "学历要求无法解析，按中性处理"
        elif candidate_rank >= required_rank:
            score = SCORE_MET
            note = "学历达到要求"
        elif candidate_rank == required_rank - 1:
            score = SCORE_SLIGHTLY_BELOW
            note = "学历略低于要求"
        else:
            score = SCORE_BELOW
            note = "学历明显低于要求"

    weight = MATCH_WEIGHTS[MatchDimensionKey.EDUCATION]
    return MatchDimension(
        key=MatchDimensionKey.EDUCATION,
        label=MatchDimensionKey.LABELS[MatchDimensionKey.EDUCATION],
        score=score,
        weight=weight,
        weighted=round2(score * weight),
        formula="学历等级比对（缺失不加分也不额外惩罚）",
        notes=[note],
    )
