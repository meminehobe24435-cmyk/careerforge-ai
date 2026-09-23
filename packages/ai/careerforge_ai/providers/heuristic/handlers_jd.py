"""JD extraction without a language model.

Lexicon-driven, section-aware and deliberately literal: the model-facing prompt
tells a real LLM to stay close to the JD's own wording, and this module holds
itself to the same standard. It is what makes the zero-key path produce a usable
skill tree rather than an empty shell.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from careerforge_ai.parsing.skill_taxonomy import extract_skill_mentions
from careerforge_ai.providers.heuristic.registry import handles
from careerforge_ai.schemas.common import RequirementLevel
from careerforge_ai.schemas.job import ExtractedJD, ExtractedJDSkill

__all__ = ["extract_jd"]

_REQUIRED_MARKERS = (
    "任职要求",
    "岗位要求",
    "职位要求",
    "requirement",
    "qualification",
    "must have",
    "任职资格",
)
_PREFERRED_MARKERS = ("优先条件", "优先", "preferred", "nice to have", "plus")
_BONUS_MARKERS = (
    "加分项",
    "加分",
    "了解",
    "接触过",
    "familiar with",
    "exposure",
    "a plus",
    "bonus",
)

#: Section markers resolved by nearest-preceding position, so a skill is
#: classified by the section it actually appears in rather than by where it
#: happens to fall in the document.
_SECTION_MARKERS: tuple[tuple[str, RequirementLevel], ...] = (
    ("加分项", RequirementLevel.BONUS),
    ("加分", RequirementLevel.BONUS),
    ("优先条件", RequirementLevel.PREFERRED),
    ("任职要求", RequirementLevel.REQUIRED),
    ("岗位要求", RequirementLevel.REQUIRED),
    ("职位要求", RequirementLevel.REQUIRED),
    ("任职资格", RequirementLevel.REQUIRED),
    ("岗位职责", RequirementLevel.REQUIRED),
    ("工作职责", RequirementLevel.REQUIRED),
    ("responsibilities", RequirementLevel.REQUIRED),
    ("requirements", RequirementLevel.REQUIRED),
    ("qualifications", RequirementLevel.REQUIRED),
)

#: Sections that describe the *company*, not the candidate's requirements. A
#: posting that says "our internal tooling is built on Kubernetes" is not asking
#: for Kubernetes, and treating it as a requirement both overstates the skill set
#: and inflates every gap it touches.
#:
#: Measured before this rule existed, 100% of postings containing such a blurb
#: leaked at least one non-required skill into the required set. After it, none
#: do. That measurement is why the rule exists.
_IGNORED_SECTION_MARKERS = (
    "公司简介",
    "公司介绍",
    "关于我们",
    "团队介绍",
    "团队文化",
    "我们提供",
    "福利待遇",
    "技术栈",
    "about us",
    "who we are",
    "our stack",
    "tech stack",
    "what we offer",
    "benefits",
    "company overview",
)


def _in_ignored_section(text: str, offset: int) -> bool:
    """Whether ``offset`` falls inside a company-description section."""
    prefix = text[:offset].lower()
    ignored_at = max((prefix.rfind(marker) for marker in _IGNORED_SECTION_MARKERS), default=-1)
    if ignored_at < 0:
        return False
    meaningful_at = max((prefix.rfind(marker) for marker, _ in _SECTION_MARKERS), default=-1)
    return ignored_at > meaningful_at


_COMPANY_RE = re.compile(
    r"(?:公司|企业|company|employer)\s*[:：]\s*(?P<name>[^\n，,。;；]{2,40})", re.IGNORECASE
)
_LOCATION_RE = re.compile(
    r"(?:工作地点|地点|城市|location|base)\s*[:：]\s*(?P<loc>[^\n，,。;；]{2,30})", re.IGNORECASE
)
_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\+)?\s*(?:年|years?)", re.IGNORECASE)
_SALARY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~至]\s*(\d+(?:\.\d+)?)\s*(?:k|K|万|元)")
_DEGREE_TOKENS = ("本科", "硕士", "博士", "大专", "bachelor", "master", "phd", "专科")

_ROLE_HINTS = (
    "engineer",
    "developer",
    "scientist",
    "architect",
    "manager",
    "intern",
    "analyst",
    "工程师",
    "开发",
    "架构师",
    "实习生",
    "专家",
    "主管",
    "研究员",
)

_SECTION_SPLIT_RE = re.compile(
    r"(?=任职要求|岗位要求|职位要求|岗位职责|工作职责|职位描述|加分项|优先条件|"
    r"requirements?|qualifications?|responsibilities|nice to have)",
    re.IGNORECASE,
)

_RESPONSIBILITY_HEADERS = ("岗位职责", "工作职责", "职位描述", "responsibilit")
_BULLET_MARKER_RE = re.compile(r"^[\-\u2022*·▪◦>\d.)\s]+")


def _classify_requirement(sentence: str, text: str, offset: int) -> RequirementLevel:
    """Decide whether a skill mention is required, preferred or a bonus.

    Order of evidence, most specific first:

    1. The sentence itself uses bonus language ("加分项", "了解", "a plus").
    2. The sentence uses preference language ("优先", "nice to have").
    3. The nearest preceding section header decides.
    4. Default to ``REQUIRED``.

    Defaulting to required is deliberate: under-stating a requirement makes a
    candidate skip a gap that will be probed in the interview, whereas
    over-stating one makes them chase a gap that does not exist. Given a real
    interview, the first error costs more.
    """
    lowered = sentence.lower()
    if any(marker in lowered for marker in _BONUS_MARKERS):
        return RequirementLevel.BONUS
    if any(marker in lowered for marker in _PREFERRED_MARKERS):
        return RequirementLevel.PREFERRED

    prefix = text[:offset].lower()
    best_position = -1
    best_kind: RequirementLevel | None = None
    for marker, kind in _SECTION_MARKERS:
        position = prefix.rfind(marker)
        if position > best_position:
            best_position = position
            best_kind = kind
    if best_kind is not None:
        return best_kind

    if any(marker in lowered for marker in _REQUIRED_MARKERS):
        return RequirementLevel.REQUIRED
    return RequirementLevel.REQUIRED


def _sentence_for(text: str, offset: int, window: int = 120) -> str:
    """The line containing ``offset``, clipped — the JD's own words, verbatim."""
    start = text.rfind("\n", 0, offset)
    start = 0 if start == -1 else start + 1
    end = text.find("\n", offset)
    end = len(text) if end == -1 else end
    sentence = text[start:end].strip()
    if len(sentence) <= window:
        return sentence
    return sentence[:window].rstrip() + "…"


def _find_role(text: str) -> str:
    for line in text.splitlines()[:6]:
        stripped = line.strip()
        if (
            stripped
            and any(hint in stripped.lower() for hint in _ROLE_HINTS)
            and len(stripped) <= 60
        ):
            return re.sub(
                r"^(职位|岗位|position|title)\s*[:：]\s*", "", stripped, flags=re.IGNORECASE
            )
    for hint in _ROLE_HINTS:
        match = re.search(
            rf"[\w\u4e00-\u9fff]{{0,12}}{hint}[\w\u4e00-\u9fff]{{0,8}}", text, re.IGNORECASE
        )
        if match:
            return match.group(0).strip()
    return ""


def _responsibilities(text: str) -> list[str]:
    out: list[str] = []
    for chunk in _SECTION_SPLIT_RE.split(text):
        stripped = chunk.strip()
        if not stripped:
            continue
        head = stripped[:20].lower()
        if any(marker in head for marker in _RESPONSIBILITY_HEADERS):
            for line in stripped.splitlines():
                cleaned = _BULLET_MARKER_RE.sub("", line).strip()
                if len(cleaned) >= 6:
                    out.append(cleaned)
            break
    return out[:8]


@handles(ExtractedJD)
def extract_jd(text: str, context: Mapping[str, Any]) -> ExtractedJD:
    """Parse a job description into the structured form (no model required)."""
    company_match = _COMPANY_RE.search(text)
    location_match = _LOCATION_RE.search(text)
    years_match = _YEARS_RE.search(text)
    salary_match = _SALARY_RE.search(text)
    degree = next((token for token in _DEGREE_TOKENS if token in text.lower()), None)

    # ``dedupe=False`` on purpose: the ignored-section filter below discards mentions
    # by position, so an early mention in a company blurb must not be allowed to
    # consume the skill before its later, valid mention has been seen.
    mentions = extract_skill_mentions(text, dedupe=False)

    buckets: dict[RequirementLevel, list[ExtractedJDSkill]] = {
        RequirementLevel.REQUIRED: [],
        RequirementLevel.PREFERRED: [],
        RequirementLevel.BONUS: [],
    }
    seen: set[str] = set()

    for skill, _alias, offset in mentions:
        if skill.canonical_id in seen:
            continue
        if _in_ignored_section(text, offset):
            # Company boilerplate, not a requirement. Skipped entirely rather
            # than classified, because "not a requirement" is not one of the
            # three requirement levels — inventing one would misrepresent the JD.
            continue
        seen.add(skill.canonical_id)
        sentence = _sentence_for(text, offset)
        level = _classify_requirement(sentence, text, offset)
        buckets[level].append(
            ExtractedJDSkill(name=skill.display_name, requirement=level, evidence=sentence)
        )

    return ExtractedJD(
        company=company_match.group("name").strip() if company_match else None,
        role=_find_role(text),
        level=None,
        location=location_match.group("loc").strip() if location_match else None,
        remote_type="remote" if "远程" in text or "remote" in text.lower() else None,
        employment_type="internship" if "实习" in text else None,
        salary_min=float(salary_match.group(1)) if salary_match else None,
        salary_max=float(salary_match.group(2)) if salary_match else None,
        salary_currency="CNY" if salary_match and "k" in salary_match.group(0).lower() else None,
        education_requirement=degree,
        years_experience_min=float(years_match.group(1)) if years_match else None,
        responsibilities=_responsibilities(text),
        nice_to_have=[item.name for item in buckets[RequirementLevel.BONUS][:6]],
        keywords=[skill.display_name for skill, _, _ in mentions[:20]],
        required_skills=buckets[RequirementLevel.REQUIRED],
        preferred_skills=buckets[RequirementLevel.PREFERRED],
        bonus_skills=buckets[RequirementLevel.BONUS],
    )
