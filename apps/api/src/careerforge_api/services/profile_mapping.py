"""Row → schema mapping for the career entities.

Pure functions with no database access, split out of ``profile_service`` when that module
reached the 500-line guard. The split is by responsibility rather than by size: this module
knows *how a stored row becomes a value object*, and the service knows *when rows are written
and read*. A mapping bug and a transaction bug are different bugs, found by different tests.

Keeping the mapping here also gives the AI-core schemas one place to change when they do, which
matters because ``CandidateProfile`` is what the graph builder, the match engine and the
dashboard all consume.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from careerforge_ai.schemas.common import EvidenceStrength, Origin, SkillCategory, SkillLevel
from careerforge_ai.schemas.profile import (
    Achievement,
    CandidateProfile,
    Education,
    Experience,
    ProfileSkill,
    Project,
    SkillRef,
)
from careerforge_api.models.profile_entity import (
    Achievement as AchievementRow,
    Education as EducationRow,
    Experience as ExperienceRow,
    ProfileSkillRow,
    Project as ProjectRow,
)

__all__ = [
    "ACHIEVEMENT_KINDS",
    "EXPERIENCE_KINDS",
    "achievement_from_row",
    "education_from_row",
    "experience_from_row",
    "project_from_row",
    "skill_from_row",
    "strength_tier",
]

#: The vocabularies the database CHECK constraints enforce, mirrored here so the service can
#: fall back on a valid value rather than let a constraint violation reach the caller.
EXPERIENCE_KINDS = frozenset({"internship", "fulltime", "parttime", "research", "campus"})
ACHIEVEMENT_KINDS = frozenset({"award", "cert", "competition", "publication", "other"})

#: Ordered weakest to strongest, so the nearest tier is a linear scan.
_STRENGTH_TIERS = (
    EvidenceStrength.NONE,
    EvidenceStrength.LOW,
    EvidenceStrength.MEDIUM,
    EvidenceStrength.HIGH,
)


def merge_skills_with_evidence(
    profile: CandidateProfile, evidence_counts: Mapping[str, int]
) -> CandidateProfile:
    """Overlay the evidence graph onto the profile's skills, and add what it evidences.

    This is the difference between a true statement and a false one. A declared skill whose
    ``evidence_count`` is still zero — because the declaration was extracted from a résumé and
    nobody has counted the evidence since — reads to the match engine as *claimed but unproven*
    and is reported as a **gap**. When the graph holds three pieces of evidence for it, that gap
    tells a candidate they are missing something they demonstrably have.

    The merge is a union, not an overwrite, and it keeps the declared level:

    * declared **and** evidenced → the declaration's level, with a real evidence count;
    * declared, no evidence → unchanged, and correctly a gap;
    * evidenced but never declared → added at a moderate level, because evidence that exists
      must count even when the candidate did not list it.

    Args:
        profile: the assembled profile.
        evidence_counts: canonical skill id → number of independent evidence items.
    """
    merged: dict[str, ProfileSkill] = {item.skill.canonical_id: item for item in profile.skills}
    for canonical, count in evidence_counts.items():
        if not canonical or count <= 0:
            continue
        existing = merged.get(canonical)
        if existing is None:
            merged[canonical] = ProfileSkill(
                skill=SkillRef(
                    canonical_id=canonical,
                    display_name=canonical.replace("_", " ").title(),
                    category=SkillCategory.TOOL,
                ),
                level=SkillLevel.MODERATE,
                evidence_count=count,
            )
            continue
        existing.evidence_count = max(existing.evidence_count, count)
    profile.skills = [merged[key] for key in sorted(merged)]
    return profile


def strength_tier(value: float) -> EvidenceStrength:
    """Nearest stored strength tier for a 0..1 score.

    The score is the persisted fact; the tier is the vocabulary the schemas speak. Rounding to
    the closest tier rather than truncating keeps a 0.99 from reading as "medium".
    """
    return min(_STRENGTH_TIERS, key=lambda tier: abs(tier.numeric - float(value)))


def education_from_row(row: EducationRow) -> Education:
    return Education(
        id=row.id,
        school=row.school,
        degree=row.degree,
        major=row.major,
        start_date=row.start_date,
        end_date=row.end_date,
        gpa=float(row.gpa) if row.gpa is not None else None,
        highlights=[str(item) for item in row.highlights or []],
        evidence_strength=strength_tier(float(row.evidence_strength)),
        origin=Origin(row.origin),
    )


def experience_from_row(row: ExperienceRow) -> Experience:
    return Experience(
        id=row.id,
        kind=row.kind,
        company=row.company,
        title=row.title,
        location=row.location,
        start_date=row.start_date,
        end_date=row.end_date,
        is_current=row.is_current,
        description=row.description,
        highlights=[str(item) for item in row.highlights or []],
        evidence_strength=strength_tier(float(row.evidence_strength)),
        origin=Origin(row.origin),
        source_document_id=row.source_document_id,
    )


def project_from_row(row: ProjectRow) -> Project:
    return Project(
        id=row.id,
        name=row.name,
        role=row.role,
        summary=row.summary,
        description=row.description,
        tech_stack=[str(item) for item in row.tech_stack or []],
        start_date=row.start_date,
        end_date=row.end_date,
        repository_id=row.repository_id,
        links={str(key): str(value) for key, value in (row.links or {}).items()},
        architecture_mermaid=row.architecture_mermaid,
        key_challenges=[str(item) for item in row.key_challenges or []],
        technical_decisions=[str(item) for item in row.technical_decisions or []],
        tradeoffs=[str(item) for item in row.tradeoffs or []],
        debugging_stories=[str(item) for item in row.debugging_stories or []],
        evidence_strength=strength_tier(float(row.evidence_strength)),
        origin=Origin(row.origin),
    )


def achievement_from_row(row: AchievementRow) -> Achievement:
    return Achievement(
        id=row.id,
        kind=row.kind,
        title=row.title,
        issuer=row.issuer,
        awarded_on=row.awarded_on,
        level=row.level,
        description=row.description,
        evidence_strength=strength_tier(float(row.evidence_strength)),
        origin=Origin(row.origin),
    )


def skill_from_row(row: ProfileSkillRow, dictionary_entry: Any | None) -> ProfileSkill:
    """One declared skill, with the dictionary's display name when the taxonomy knows it.

    ``canonical_id`` is denormalised on the row precisely so this works when the dictionary
    lookup misses: a declaration whose taxonomy entry was deactivated is still a declaration.
    """
    canonical = row.canonical_id
    return ProfileSkill(
        skill=SkillRef(
            canonical_id=canonical,
            display_name=(
                dictionary_entry.display_name
                if dictionary_entry is not None
                else canonical.replace("_", " ").title()
            ),
            category=(
                SkillCategory(dictionary_entry.category)
                if dictionary_entry is not None
                else SkillCategory.TOOL
            ),
        ),
        level=SkillLevel(row.level),
        evidence_score=float(row.evidence_score),
        evidence_count=row.evidence_count,
        is_target=row.is_target,
        origin=Origin(row.origin),
    )


def node_id_for_row(model: Any, row: Any) -> UUID | None:
    """The graph node id the builder derived for one entity row, or `None` if unknowable.

    Mirrors `ProfileService.graph_nodes` exactly, because the two must agree: this one is used
    to remove an entity's edges, and a mismatch would leave the orphan it was meant to prevent.
    """
    from careerforge_ai.graph import node_id
    from careerforge_ai.schemas.common import GraphNodeType

    if model is EducationRow:
        return node_id(GraphNodeType.EDUCATION, row.school)
    if model is ExperienceRow:
        return node_id(GraphNodeType.EXPERIENCE, f"{row.company}:{row.title}")
    if model is ProjectRow:
        return node_id(GraphNodeType.PROJECT, str(row.id))
    if model is AchievementRow:
        return node_id(GraphNodeType.ACHIEVEMENT, row.title)
    return None
