"""ProfileAgent — resume/document text → structured candidate profile (WF-01).

Ingestion is where a product like this either earns trust or loses it. Three
decisions follow from that.

**Nothing is inferred.** The extraction prompt is written to leave fields empty
rather than guess, and this agent does not fill the gaps afterwards either: a
missing graduation year stays missing. An empty field costs the candidate nothing;
an invented one contaminates every match score, gap analysis and interview question
downstream.

**Skills are normalised, not invented.** The model reports skill names as written;
the taxonomy decides what they are. Names the taxonomy cannot resolve are returned
to the caller as ``unmapped_skills`` so a human can extend the vocabulary, rather
than being silently dropped or guessed at.

**Claimed level is deliberately neutral.** Ingestion cannot know whether someone is
strong in Rust — only their evidence can show that. Every extracted skill is
recorded at a neutral claimed level, and the evidence factor in the match engine is
what turns a claim into a score. A profile that overstates itself therefore scores
*worse*, not better.
"""

from __future__ import annotations

from datetime import date
import re
from typing import Any

from careerforge_ai.agents.base import (
    AgentOutcome,
    merge_workflow_warnings,
    normalise_whitespace,
    strip_markup,
    truncate_for_prompt,
)
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.parsing.skill_taxonomy import SKILLS, normalize_skill
from careerforge_ai.schemas.common import EvidenceStrength, Origin, SkillLevel
from careerforge_ai.schemas.profile import (
    Achievement,
    CandidateProfile,
    Education,
    Experience,
    ExtractedProfile,
    ProfileImportResult,
    ProfileSkill,
    Project,
    SkillRef,
)

__all__ = ["PROFILE_AGENT", "ProfileAgent", "build_workflow", "import_profile"]

PROFILE_AGENT = "profile"

#: Neutral level applied to every extracted skill. See the module docstring: the
#: evidence factor, not this number, decides what a skill is worth.
_CLAIMED_LEVEL = SkillLevel.MODERATE

_KNOWN_SKILLS_HINT = ", ".join(skill.display_name for skill in SKILLS)

#: Tolerant ISO-ish date parsing. Sources range from "2025-07-01" to "2025-07" to
#: "2025"; anything else is left unset rather than guessed.
_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})$"),
    re.compile(r"^(?P<year>\d{4})-(?P<month>\d{1,2})$"),
    re.compile(r"^(?P<year>\d{4})$"),
    re.compile(r"^(?P<year>\d{4})[/.](?P<month>\d{1,2})[/.](?P<day>\d{1,2})$"),
    re.compile(r"^(?P<year>\d{4})[/.](?P<month>\d{1,2})$"),
)


def _parse_date(value: str | None) -> date | None:
    """Parse a partial date, defaulting missing components to the first of them."""
    if not value:
        return None
    text = value.strip()
    for pattern in _DATE_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        groups = match.groupdict()
        try:
            return date(
                int(groups["year"]),
                int(groups.get("month") or 1),
                int(groups.get("day") or 1),
            )
        except ValueError:
            return None
    return None


def build_workflow() -> Workflow:
    """The WF-01 graph up to (but not including) evidence and embedding."""
    return Workflow(
        name="profile_ingest",
        agent=PROFILE_AGENT,
        trigger="api",
        description="Turn resume or project-document text into a structured profile",
        steps=(
            Step(
                name="clean",
                fn=_clean,
                agent=PROFILE_AGENT,
                description="Strip markup, normalise whitespace, enforce a prompt budget",
            ),
            Step(
                name="extract",
                fn=_extract,
                depends_on=("clean",),
                agent=PROFILE_AGENT,
                description="Structured extraction bounded by the ExtractedProfile schema",
            ),
            Step(
                name="normalise",
                fn=_normalise,
                depends_on=("extract",),
                agent=PROFILE_AGENT,
                description="Resolve skill names against the taxonomy",
            ),
            Step(
                name="assemble",
                fn=_assemble,
                depends_on=("clean", "extract", "normalise"),
                agent=PROFILE_AGENT,
                description="Build the CandidateProfile and report what could not be resolved",
            ),
        ),
    )


# ── steps ────────────────────────────────────────────────────────────────────


async def _clean(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    raw = str(context.metadata.get("source_text") or "")
    text = normalise_whitespace(strip_markup(raw))
    clipped, truncated = truncate_for_prompt(text)
    if truncated:
        context.metadata.setdefault("warnings", []).append(
            "文档过长，仅前 70% 与后 30% 参与解析（建议拆分后分次导入）"
        )
    return {"text": clipped, "truncated": truncated, "original_length": len(raw)}


async def _extract(context: RunContext, inputs: dict[str, Any]) -> ExtractedProfile:
    text = str(inputs["clean"]["text"])
    return await context.structured(
        "profile_extractor",
        ExtractedProfile,
        context={"source_text": text},
        source_text=text,
        source_kind=str(context.metadata.get("source_kind") or "resume"),
        known_skills=_KNOWN_SKILLS_HINT,
    )


async def _normalise(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    extracted: ExtractedProfile = inputs["extract"]
    skills: list[ProfileSkill] = []
    unmapped: list[str] = []
    mapping: dict[str, str] = {}
    seen: set[str] = set()

    for name in extracted.skills:
        skill = normalize_skill(name)
        if skill is None:
            unmapped.append(name)
            continue
        if skill.canonical_id in seen:
            continue
        seen.add(skill.canonical_id)
        mapping[name] = skill.canonical_id
        skills.append(
            ProfileSkill(
                skill=SkillRef(
                    canonical_id=skill.canonical_id,
                    display_name=skill.display_name,
                    category=skill.category,
                    aliases=list(skill.aliases),
                ),
                level=_CLAIMED_LEVEL,
                evidence_count=0,
                evidence_score=0.0,
                origin=Origin.LLM,
            )
        )

    if unmapped:
        context.metadata.setdefault("warnings", []).append(
            f"{len(unmapped)} 个技能未在分类学中找到：{'、'.join(unmapped[:8])}"
        )

    return {"skills": skills, "unmapped": unmapped, "mapping": mapping}


async def _assemble(context: RunContext, inputs: dict[str, Any]) -> ProfileImportResult:
    extracted: ExtractedProfile = inputs["extract"]
    normalised = inputs["normalise"]

    educations = [
        Education(
            school=item.school,
            degree=item.degree,
            major=item.major,
            start_date=_parse_date(item.start_date),
            end_date=_parse_date(item.end_date),
            gpa=item.gpa,
            highlights=list(item.highlights),
            evidence_strength=EvidenceStrength.LOW,
            origin=Origin.LLM,
        )
        for item in extracted.educations
        if item.school.strip()
    ]

    experiences = [
        Experience(
            kind=item.kind
            if item.kind in {"internship", "fulltime", "parttime", "research", "campus"}
            else "internship",
            company=item.company,
            title=item.title,
            location=item.location,
            start_date=_parse_date(item.start_date),
            end_date=_parse_date(item.end_date),
            is_current=item.is_current,
            description=item.description,
            highlights=list(item.highlights),
            evidence_strength=EvidenceStrength.LOW,
            origin=Origin.LLM,
        )
        for item in extracted.experiences
        if item.company.strip() and item.title.strip()
    ]

    projects = [
        Project(
            name=item.name,
            role=item.role,
            summary=item.summary,
            description=item.description,
            tech_stack=list(item.tech_stack),
            start_date=_parse_date(item.start_date),
            end_date=_parse_date(item.end_date),
            key_challenges=list(item.key_challenges),
            technical_decisions=list(item.technical_decisions),
            evidence_strength=EvidenceStrength.LOW,
            origin=Origin.LLM,
        )
        for item in extracted.projects
        if item.name.strip()
    ]

    achievements = [
        Achievement(
            kind=item.kind
            if item.kind in {"award", "cert", "competition", "publication", "other"}
            else "award",
            title=item.title,
            issuer=item.issuer,
            awarded_on=_parse_date(item.date),
            level=item.level,
            description=item.description,
            evidence_strength=EvidenceStrength.LOW,
            origin=Origin.LLM,
        )
        for item in extracted.achievements
        if item.title.strip()
    ]

    profile = CandidateProfile(
        user_id=context.user_id,
        slug=str(context.metadata.get("slug") or "") or None,
        headline=extracted.headline,
        summary=extracted.summary,
        location=extracted.location,
        target_roles=list(extracted.target_roles),
        years_experience=extracted.years_experience,
        educations=educations,
        experiences=experiences,
        projects=projects,
        achievements=achievements,
        skills=normalised["skills"],
    )

    warnings: list[str] = list(context.metadata.get("warnings", []))
    if not any((educations, experiences, projects, achievements)):
        warnings.append("未能从文档中抽取到任何经历或项目，请确认上传的是简历或项目文档")
    if inputs["clean"]["truncated"]:
        warnings.append("文档被截断，部分内容未参与解析")

    context.metadata["warnings"] = warnings
    context.metadata["input_ref"] = {
        "length": inputs["clean"]["original_length"],
        "source_kind": context.metadata.get("source_kind"),
    }
    context.metadata["output_ref"] = {
        "projects": len(projects),
        "experiences": len(experiences),
        "skills": len(normalised["skills"]),
        "unmapped": len(normalised["unmapped"]),
    }

    return ProfileImportResult(
        profile=profile,
        skills_created=len(normalised["skills"]),
        skills_normalised=dict(normalised["mapping"]),
        unmapped_skills=list(normalised["unmapped"]),
        warnings=warnings,
        degraded=context.degraded,
    )


# ── agent ────────────────────────────────────────────────────────────────────


class ProfileAgent:
    """Parses resume and project documents. Stateless."""

    name = PROFILE_AGENT

    def workflow(self) -> Workflow:
        return build_workflow()

    async def run(
        self,
        executor: WorkflowExecutor,
        *,
        source_text: str,
        source_kind: str = "resume",
        slug: str | None = None,
    ) -> AgentOutcome:
        output = await executor.run(
            self.workflow(),
            trigger="api",
            metadata={"source_text": source_text, "source_kind": source_kind, "slug": slug or ""},
        )
        result: ProfileImportResult | None = output.get("assemble")
        warnings = merge_workflow_warnings(output)
        warnings.extend(str(item) for item in output.metadata.get("warnings", []))

        if result is not None and warnings:
            # De-duplicate: the assemble step already folds step warnings into the
            # result, and the caller sees both paths. ``dict.fromkeys`` keeps the
            # original order and does not need a side-effecting comprehension.
            result.warnings = list(dict.fromkeys(warnings))

        return AgentOutcome(
            value=result,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=output.degradation_reason,
            warnings=warnings,
        )


async def import_profile(
    executor: WorkflowExecutor, source_text: str, **kwargs: Any
) -> tuple[ProfileImportResult | None, AgentOutcome]:
    """Convenience wrapper returning both the import result and its trace."""
    outcome = await ProfileAgent().run(executor, source_text=source_text, **kwargs)
    return outcome.value, outcome
