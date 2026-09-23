"""RecruiterAgent — the public, evidence-backed candidate profile (WF-10).

This is the surface a stranger sees, and the second thing that makes the product
different: a recruiter can click any skill and read the file, commit or document
behind it. An interactive résumé instead of a PDF.

Three rules shape it.

**Publishing is per-section and defaults to closed.** Contact details are hidden
unless the candidate opts in. Defaulting to visible would make the difference
invisible until someone scraped it.

**Incidental PII is redacted; published contact is not.** A phone number that leaked
into a project description gets removed. An email the candidate deliberately
published stays. Conflating the two would either leak or break the feature.

**Nothing is asserted that the evidence cannot carry.** Every skill in the payload
carries its evidence ids and confidence, so the page can show *why* it believes
something rather than presenting an unbacked claim with a confident tone.
"""

from __future__ import annotations

from typing import Any

from careerforge_ai.agents.base import AgentOutcome, merge_workflow_warnings, render_bullets
from careerforge_ai.graph import GraphBuildResult
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.parsing.pii import redact_pii
from careerforge_ai.schemas.common import EvidenceKind
from careerforge_ai.schemas.evidence import EvidenceItem
from careerforge_ai.schemas.profile import CandidateProfile
from careerforge_ai.schemas.public import (
    ExtractedRecruiterSummary,
    PublicEvidenceLink,
    PublicProfileSummary,
    PublicProject,
    PublicSectionVisibility,
    PublicSkill,
)
from careerforge_ai.scoring.profile_strength import EvidenceStats, compute_profile_strength

__all__ = ["RECRUITER_AGENT", "RecruiterAgent", "build_workflow", "publish_profile"]

RECRUITER_AGENT = "recruiter"

#: Evidence kinds whose locator is a URL a stranger can actually open.
_LINKABLE_KINDS = frozenset(
    {
        EvidenceKind.REPO_FILE,
        EvidenceKind.COMMIT,
        EvidenceKind.README,
    }
)

#: Evidence shown per skill on the public page. Enough to demonstrate, not so many
#: that the page becomes a file listing.
_MAX_EVIDENCE_PER_SKILL = 4

#: Characters of candidate material placed in the prompt.
_MATERIAL_BUDGET = 4000


def build_workflow() -> Workflow:
    """The WF-10 graph: gather → summarise → redact → assemble."""
    return Workflow(
        name="recruiter_publish",
        agent=RECRUITER_AGENT,
        trigger="api",
        description="Build the public, evidence-backed candidate profile",
        steps=(
            Step(
                name="gather",
                fn=_gather,
                agent=RECRUITER_AGENT,
                description="Collect publishable facts",
            ),
            Step(
                name="summarise",
                fn=_summarise,
                depends_on=("gather",),
                agent=RECRUITER_AGENT,
                optional=True,
                description="Model-written summary, grounded in the material",
            ),
            Step(
                name="redact",
                fn=_redact,
                depends_on=("gather", "summarise"),
                agent=RECRUITER_AGENT,
                description="Remove incidental PII from everything about to be published",
            ),
            Step(
                name="assemble",
                fn=_assemble,
                depends_on=("gather", "summarise", "redact"),
                agent=RECRUITER_AGENT,
                description="Apply section visibility and build the payload",
            ),
        ),
    )


# ── steps ────────────────────────────────────────────────────────────────────


def _evidence_links(graph: GraphBuildResult, canonical_id: str) -> list[PublicEvidenceLink]:
    by_id: dict[Any, EvidenceItem] = {
        item.id: item for item in graph.evidence if item.id is not None
    }
    links: list[PublicEvidenceLink] = []
    for evidence_id in graph.skill_evidence.get(canonical_id, [])[:_MAX_EVIDENCE_PER_SKILL]:
        item = by_id.get(evidence_id)
        if item is None or item.kind not in _LINKABLE_KINDS:
            # Only material a stranger can open is linked. A document chunk behind a
            # private upload is not public evidence, however strong it is.
            continue
        links.append(
            PublicEvidenceLink(
                evidence_id=item.id,  # type: ignore[arg-type]
                title=item.title,
                kind=item.kind.value,
                locator_display=item.locator.display,
                url=item.locator.url,
                confidence=item.confidence,
            )
        )
    return links


async def _gather(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    profile = context.maybe_service("profile")
    graph = context.maybe_service("graph")
    if not isinstance(profile, CandidateProfile):
        raise ValueError("recruiter_publish requires a CandidateProfile in services['profile']")

    visibility: PublicSectionVisibility = (
        context.maybe_service("visibility") or PublicSectionVisibility()
    )
    slug = str(context.metadata.get("slug") or profile.slug or "").strip()
    if not slug:
        raise ValueError("a public profile requires a slug")

    skills: list[PublicSkill] = []
    if visibility.skills:
        for item in profile.skills:
            canonical = item.skill.canonical_id
            links = (
                _evidence_links(graph, canonical)
                if isinstance(graph, GraphBuildResult) and visibility.evidence
                else []
            )
            skills.append(
                PublicSkill(
                    canonical_id=canonical,
                    display_name=item.skill.display_name,
                    category=item.skill.category.value,
                    confidence=(
                        graph.skill_confidence.get(canonical, 0.0)
                        if isinstance(graph, GraphBuildResult)
                        else 0.0
                    ),
                    evidence_count=(
                        len(graph.skill_evidence.get(canonical, []))
                        if isinstance(graph, GraphBuildResult)
                        else 0
                    ),
                    corroboration=(
                        graph.skill_corroboration.get(canonical, 0)
                        if isinstance(graph, GraphBuildResult)
                        else 0
                    ),
                    evidence=links,
                )
            )
        skills.sort(key=lambda skill: (-skill.confidence, skill.display_name))

    projects: list[PublicProject] = []
    if visibility.projects:
        for project in profile.projects:
            projects.append(
                PublicProject(
                    name=project.name,
                    role=project.role,
                    summary=project.summary,
                    tech_stack=list(project.tech_stack),
                    repository_url=project.links.get("github"),
                    highlights=list(project.key_challenges),
                )
            )

    material_lines: list[str] = []
    if profile.summary:
        material_lines.append(f"自我总结：{profile.summary}")
    for project in profile.projects:
        material_lines.append(
            f"项目：{project.name} — {project.summary or project.description}"
            f"（技术栈：{'、'.join(project.tech_stack)}）"
        )
    for experience in profile.experiences:
        material_lines.append(
            f"经历：{experience.company} · {experience.title} — {experience.description}"
        )
    material = "\n".join(material_lines)[:_MATERIAL_BUDGET]

    context.metadata["input_ref"] = {
        "slug": slug,
        "skills": len(skills),
        "projects": len(projects),
        "sections_visible": visibility.visible_count,
    }
    return {
        "profile": profile,
        "graph": graph if isinstance(graph, GraphBuildResult) else None,
        "visibility": visibility,
        "slug": slug,
        "skills": skills,
        "projects": projects,
        "material": material,
    }


async def _summarise(
    context: RunContext, inputs: dict[str, Any]
) -> ExtractedRecruiterSummary | None:
    prepared = inputs["gather"]
    if not prepared["material"].strip():
        return None

    graph: GraphBuildResult | None = prepared["graph"]
    evidence_summary = (
        f"{len(graph.evidence)} 条证据，平均置信度 {graph.mean_confidence:.2f}，"
        f"覆盖 {len(graph.skill_evidence)} 项技能"
        if graph
        else "（未提供证据图谱）"
    )

    return await context.structured(
        "recruiter_summary",
        ExtractedRecruiterSummary,
        context={"source_text": prepared["material"]},
        candidate_material=prepared["material"],
        evidence_summary=evidence_summary,
        projects=render_bullets([f"{p.name} — {p.summary}" for p in prepared["projects"]]),
        target_roles=render_bullets(list(prepared["profile"].target_roles)),
    )


async def _redact(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    """Strip incidental PII from everything about to become public."""
    prepared = inputs["gather"]
    summary: ExtractedRecruiterSummary | None = inputs.get("summarise")

    findings: list[dict[str, str]] = []

    def clean(text: str, *, where: str) -> str:
        redacted, hits = redact_pii(text)
        for hit in hits:
            findings.append({"where": where, "kind": hit.kind.value, "masked": hit.masked})
        return redacted

    cleaned_material = clean(str(prepared["material"]), where="material")
    cleaned_summary = clean(summary.summary, where="summary") if summary else ""
    cleaned_highlights = (
        [clean(item, where="highlights") for item in summary.highlights] if summary else []
    )
    cleaned_topics = (
        [clean(item, where="interview_topics") for item in summary.interview_topics]
        if summary
        else []
    )
    cleaned_projects = [
        project.model_copy(
            update={
                "summary": clean(project.summary, where="projects"),
                "highlights": [clean(item, where="projects") for item in project.highlights],
            }
        )
        for project in prepared["projects"]
    ]

    if findings:
        context.metadata.setdefault("warnings", []).append(
            f"公开页中脱敏了 {len(findings)} 处联系方式或证件号码"
        )

    return {
        "material": cleaned_material,
        "summary": cleaned_summary,
        "highlights": cleaned_highlights,
        "interview_topics": cleaned_topics,
        "projects": cleaned_projects,
        "findings": findings,
    }


async def _assemble(context: RunContext, inputs: dict[str, Any]) -> PublicProfileSummary:
    prepared = inputs["gather"]
    cleaned = inputs["redact"]
    profile: CandidateProfile = prepared["profile"]
    graph: GraphBuildResult | None = prepared["graph"]
    visibility: PublicSectionVisibility = prepared["visibility"]

    skills: list[PublicSkill] = prepared["skills"] if visibility.skills else []
    backed = [skill for skill in skills if skill.is_backed]
    coverage = round(len(backed) / len(skills), 4) if skills else 0.0

    stats = (
        EvidenceStats(
            total_evidence=len(graph.evidence) if graph else 0,
            mean_confidence=graph.mean_confidence if graph else 0.0,
            high_confidence_count=(
                sum(1 for item in graph.evidence if item.confidence >= 0.75) if graph else 0
            ),
            distinct_kinds=len({item.kind.value for item in graph.evidence}) if graph else 0,
            repository_count=len(
                {
                    str(item.metadata.get("repository"))
                    for item in graph.evidence
                    if item.metadata.get("repository")
                }
            )
            if graph
            else 0,
        )
        if graph
        else EvidenceStats()
    )

    strength = compute_profile_strength(profile=profile, stats=stats)

    # Contact is published only on an explicit opt-in, and is never redacted — an
    # address the candidate chose to publish is not incidental PII.
    contact: dict[str, str] = {}
    if visibility.contact:
        if profile.website:
            contact["website"] = profile.website
        if profile.location:
            contact["location"] = profile.location

    context.metadata["output_ref"] = {
        "skills": len(skills),
        "backed_skills": len(backed),
        "redactions": len(cleaned["findings"]),
    }

    return PublicProfileSummary(
        slug=prepared["slug"],
        display_name=profile.headline or "Candidate",
        headline=profile.headline,
        location=profile.location if visibility.contact else None,
        summary=cleaned["summary"] if visibility.summary else "",
        target_roles=list(profile.target_roles) if visibility.summary else [],
        skills=skills,
        projects=cleaned["projects"] if visibility.projects else [],
        highlights=cleaned["highlights"] if visibility.highlights else [],
        interview_topics=cleaned["interview_topics"] if visibility.interview_topics else [],
        github_url=(
            f"https://github.com/{profile.github_username}" if profile.github_username else None
        ),
        website_url=profile.website if visibility.contact else None,
        contact=contact,
        visibility=visibility,
        redactions=cleaned["findings"],
        evidence_coverage=coverage,
        profile_strength=strength.score,
        degraded=context.degraded,
    )


# ── agent ────────────────────────────────────────────────────────────────────


class RecruiterAgent:
    """Builds the public profile. Stateless."""

    name = RECRUITER_AGENT

    def workflow(self) -> Workflow:
        return build_workflow()

    async def run(
        self,
        executor: WorkflowExecutor,
        *,
        profile: CandidateProfile,
        graph: GraphBuildResult | None = None,
        visibility: PublicSectionVisibility | None = None,
        slug: str | None = None,
    ) -> AgentOutcome:
        services: dict[str, Any] = {
            "profile": profile,
            "visibility": visibility or PublicSectionVisibility(),
        }
        if graph is not None:
            services["graph"] = graph

        output = await executor.run(
            self.workflow(),
            trigger="api",
            services=services,
            metadata={"slug": slug or profile.slug or ""},
        )
        result: PublicProfileSummary | None = output.get("assemble")
        warnings = merge_workflow_warnings(output)
        warnings.extend(str(item) for item in output.metadata.get("warnings", []))

        return AgentOutcome(
            value=result,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=output.degradation_reason,
            warnings=warnings,
        )


async def publish_profile(
    executor: WorkflowExecutor, **kwargs: Any
) -> tuple[PublicProfileSummary | None, AgentOutcome]:
    """Convenience wrapper returning both the public payload and its trace."""
    outcome = await RecruiterAgent().run(executor, **kwargs)
    return outcome.value, outcome
