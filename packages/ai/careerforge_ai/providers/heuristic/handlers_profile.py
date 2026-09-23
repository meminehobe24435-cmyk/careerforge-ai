"""Profile extraction without a language model.

Section-header heuristics over resume-like text. Intentionally conservative: it
extracts what is unmistakably present and leaves the rest empty, because an empty
field costs the candidate nothing while an invented one corrupts every score
downstream.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from careerforge_ai.parsing.skill_taxonomy import extract_skill_mentions
from careerforge_ai.providers.heuristic.registry import handles
from careerforge_ai.providers.heuristic.text import first_date, split_sections
from careerforge_ai.schemas.profile import (
    ExtractedEducation,
    ExtractedExperience,
    ExtractedProfile,
    ExtractedProject,
)

__all__ = ["extract_profile"]

_SCHOOL_RE = re.compile(
    r"[\u4e00-\u9fff]{2,20}大学|[\u4e00-\u9fff]{2,20}学院|[A-Z][A-Za-z\s]{4,40}University"
)
_COMPANY_RE = re.compile(
    r"[\u4e00-\u9fff]{2,20}(?:公司|集团|研究院|研究所|实验室)|"
    r"[A-Z][A-Za-z\s]{3,30}(?:Inc|Ltd|Corp|Technologies)"
)
_TITLE_RE = re.compile(r"(实习生|工程师|开发|研究员|助理|intern|engineer|developer)", re.IGNORECASE)
_MAJOR_RE = re.compile(r"(?:专业|major)\s*[:：]?\s*([^\n，,。;；]{2,20})", re.IGNORECASE)
_PROJECT_NAME_RE = re.compile(r"^([^：:，,。;；\-–—]{2,30})")

_DEGREE_TOKENS = ("本科", "硕士", "博士", "大专", "专科", "bachelor", "master", "phd")


@handles(ExtractedProfile)
def extract_profile(text: str, context: Mapping[str, Any]) -> ExtractedProfile:
    """Extract a structured profile from resume or project-document text."""
    sections = split_sections(text)

    educations: list[ExtractedEducation] = []
    for line in sections["education"][:4]:
        school_match = _SCHOOL_RE.search(line)
        degree = next((token for token in _DEGREE_TOKENS if token in line.lower()), None)
        major_match = _MAJOR_RE.search(line)
        educations.append(
            ExtractedEducation(
                school=school_match.group(0) if school_match else line[:40],
                degree=degree,
                major=major_match.group(1).strip() if major_match else None,
                start_date=first_date(line),
                end_date=None,
                gpa=None,
                highlights=[],
            )
        )

    experiences: list[ExtractedExperience] = []
    for line in sections["experience"][:6]:
        company_match = _COMPANY_RE.search(line)
        title_match = _TITLE_RE.search(line)
        if not company_match and not title_match:
            continue
        experiences.append(
            ExtractedExperience(
                kind="internship" if "实习" in line or "intern" in line.lower() else "fulltime",
                company=company_match.group(0) if company_match else line[:30],
                title=title_match.group(0) if title_match else "工程师",
                start_date=first_date(line),
                end_date=None,
                description=line,
                highlights=[],
            )
        )

    projects: list[ExtractedProject] = []
    for line in sections["project"][:8]:
        name_match = _PROJECT_NAME_RE.search(line)
        tech = [skill.display_name for skill, _, _ in extract_skill_mentions(line)]
        projects.append(
            ExtractedProject(
                name=name_match.group(1).strip() if name_match else line[:24],
                summary=line[:120],
                description=line,
                tech_stack=tech[:10],
            )
        )

    skills: list[str] = []
    for line in sections["skill"]:
        for skill, _, _ in extract_skill_mentions(line):
            if skill.display_name not in skills:
                skills.append(skill.display_name)
    if not skills:
        skills = [skill.display_name for skill, _, _ in extract_skill_mentions(text)[:30]]

    return ExtractedProfile(
        headline="",
        summary="",
        location=None,
        target_roles=[],
        years_experience=None,
        educations=educations,
        experiences=experiences,
        projects=projects,
        achievements=[],
        skills=skills,
    )
