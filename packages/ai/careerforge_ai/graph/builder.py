"""Evidence graph construction.

Turns a structured profile plus a pile of raw material into a connected graph::

    Candidate → Experience/Project → Skill → Evidence → (file · commit · document)

Two properties make this worth a dedicated module rather than a loop in a service.

**Determinism.** Every node id is derived with ``uuid5`` from a stable key
(``project:Balance Robot``, ``skill:stm32``), so the same profile always produces
the same graph. That is what lets the API diff two builds, and what lets a test
assert a specific edge exists.

**Corroboration is computed, not asserted.** A skill's confidence is first scored
per piece of evidence, then re-scored once the number of *independent* sources
supporting it is known. One README mentioning FreeRTOS and five files plus three
commits implementing it are not the same claim, and the second pass is where that
distinction is made.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from uuid import UUID

from careerforge_ai.graph.builder_types import GraphBuildResult
from careerforge_ai.graph.ids import GRAPH_NAMESPACE, node_id
from careerforge_ai.graph.job_layer import attach_job, node_type_for
from careerforge_ai.parsing.skill_taxonomy import extract_skill_mentions
from careerforge_ai.schemas.common import (
    EvidenceKind,
    EvidenceRelation,
    GraphNodeType,
    SourceAuthority,
)
from careerforge_ai.schemas.evidence import (
    EvidenceItem,
    EvidenceLink,
    GraphEdge,
    GraphNode,
)
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile
from careerforge_ai.scoring.confidence import compute_confidence

__all__ = [
    "GRAPH_NAMESPACE",
    "GraphBuildResult",
    "build_evidence_graph",
    "node_id",
]


def _evidence_key(item: EvidenceItem, index: int) -> str:
    if item.content_hash:
        return item.content_hash
    return f"{item.kind.value}:{item.title}:{index}"


#: Evidence kinds that count as an *independent* corroborating source. Two files
#: in the same repository are not independent; a file and a commit are; a document
#: and a README are. Corroboration is the factor that turns "one source says so"
#: into "several different kinds of material agree".
_INDEPENDENT_SOURCE_GROUPS: Mapping[EvidenceKind, str] = {
    EvidenceKind.REPO_FILE: "code",
    EvidenceKind.COMMIT: "commits",
    EvidenceKind.README: "readme",
    EvidenceKind.DOCUMENT_CHUNK: "documents",
    EvidenceKind.EXPERIENCE: "experience",
    EvidenceKind.PROJECT: "project",
    EvidenceKind.ACHIEVEMENT: "achievement",
    EvidenceKind.MANUAL: "manual",
    EvidenceKind.LLM_INFERENCE: "inference",
}


def _source_group(item: EvidenceItem) -> str:
    return _INDEPENDENT_SOURCE_GROUPS.get(item.kind, item.kind.value)


def _evidence_text(item: EvidenceItem) -> str:
    return f"{item.title}\n{item.snippet}"


def _skill_ids_in(item: EvidenceItem) -> set[str]:
    """Skills an evidence item mentions, resolved through the taxonomy.

    Derived from the evidence's own text rather than passed in by the caller, so
    the graph cannot be told something the evidence does not say.
    """
    text = _evidence_text(item)
    return {skill.canonical_id for skill, _, _ in extract_skill_mentions(text)}


def build_evidence_graph(
    *,
    profile: CandidateProfile,
    evidence: Sequence[EvidenceItem],
    job: JDAnalysis | None = None,
    confidence_weights: Mapping[str, float] | None = None,
    extraction_method: Mapping[EvidenceKind, str] | None = None,
) -> GraphBuildResult:
    """Build the evidence graph for one candidate.

    Args:
        profile: structured candidate profile.
        evidence: raw evidence with ``kind``, ``locator`` and ``occurred_at`` set.
            Confidence is computed here, not by the caller.
        job: optional target job, which adds ``REQUIRES`` / ``MATCHES`` / ``GAP``.
        confidence_weights: optional override of the five confidence weights.
        extraction_method: how each evidence kind was extracted, defaulting to
            ``deterministic`` for code and commits and ``heuristic`` for prose.
    """
    result = GraphBuildResult()
    methods = extraction_method or {}

    candidate_node = node_id(GraphNodeType.CANDIDATE, profile.slug or "candidate")
    result.nodes.append(
        GraphNode(
            id=candidate_node,
            type=GraphNodeType.CANDIDATE,
            label=profile.headline or "Candidate",
            meta={"slug": profile.slug or ""},
        )
    )

    # ── profile entities ─────────────────────────────────────────────────────
    project_nodes: dict[str, UUID] = {}
    for project in profile.projects:
        identifier = str(project.id) if project.id else project.name
        pid = node_id(GraphNodeType.PROJECT, identifier)
        project_nodes[identifier] = pid
        project_nodes[project.name] = pid
        result.nodes.append(
            GraphNode(
                id=pid,
                type=GraphNodeType.PROJECT,
                label=project.name,
                group=project.name,
                meta={"role": project.role or "", "tech_stack": project.tech_stack},
            )
        )
        result.edges.append(
            GraphEdge(
                id=f"{candidate_node}:HAS:{pid}",
                source=candidate_node,
                target=pid,
                relation=EvidenceRelation.HAS,
            )
        )
        result.links.append(
            EvidenceLink(
                from_type=GraphNodeType.CANDIDATE,
                from_id=candidate_node,
                to_type=GraphNodeType.PROJECT,
                to_id=pid,
                relation=EvidenceRelation.HAS,
                rationale="候选人拥有该项目",
            )
        )

    for education in profile.educations:
        eid = node_id(GraphNodeType.EDUCATION, education.school)
        result.nodes.append(GraphNode(id=eid, type=GraphNodeType.EDUCATION, label=education.school))
        result.edges.append(
            GraphEdge(
                id=f"{candidate_node}:HAS:{eid}",
                source=candidate_node,
                target=eid,
                relation=EvidenceRelation.HAS,
            )
        )

    for experience in profile.experiences:
        key = f"{experience.company}:{experience.title}"
        xid = node_id(GraphNodeType.EXPERIENCE, key)
        result.nodes.append(
            GraphNode(
                id=xid,
                type=GraphNodeType.EXPERIENCE,
                label=f"{experience.company} · {experience.title}",
                meta={"kind": experience.kind},
            )
        )
        result.edges.append(
            GraphEdge(
                id=f"{candidate_node}:HAS:{xid}",
                source=candidate_node,
                target=xid,
                relation=EvidenceRelation.HAS,
            )
        )

    for achievement in profile.achievements:
        aid = node_id(GraphNodeType.ACHIEVEMENT, achievement.title)
        result.nodes.append(
            GraphNode(id=aid, type=GraphNodeType.ACHIEVEMENT, label=achievement.title)
        )
        result.edges.append(
            GraphEdge(
                id=f"{candidate_node}:HAS:{aid}",
                source=candidate_node,
                target=aid,
                relation=EvidenceRelation.HAS,
            )
        )

    # ── pass 1: score each piece of evidence on its own merits ───────────────
    scored: list[tuple[EvidenceItem, set[str]]] = []
    for index, item in enumerate(evidence):
        if item.id is None:
            item.id = node_id(GraphNodeType.DOCUMENT, _evidence_key(item, index))
        method = methods.get(
            item.kind,
            "deterministic"
            if item.kind in {EvidenceKind.REPO_FILE, EvidenceKind.COMMIT, EvidenceKind.MANUAL}
            else "heuristic"
            if item.kind is EvidenceKind.LLM_INFERENCE
            else "deterministic",
        )
        breakdown = compute_confidence(
            kind=item.kind,
            authority=item.source_authority
            if isinstance(item.source_authority, SourceAuthority)
            else None,
            occurred_at=item.occurred_at,
            locator=item.locator,
            independent_sources=max(1, item.corroboration_count),
            extraction_method=method,
            weights=confidence_weights,
        )
        item.confidence = breakdown.score
        item.breakdown = breakdown
        scored.append((item, _skill_ids_in(item)))

    # ── pass 2: corroboration, computed from the evidence itself ─────────────
    skill_sources: dict[str, set[str]] = defaultdict(set)
    skill_evidence_ids: dict[str, list[UUID]] = defaultdict(list)
    for item, skill_ids in scored:
        for skill_id in skill_ids:
            skill_sources[skill_id].add(_source_group(item))
            assert item.id is not None  # assigned in pass 1
            skill_evidence_ids[skill_id].append(item.id)

    for skill_id, sources in skill_sources.items():
        result.skill_corroboration[skill_id] = len(sources)

    for item, skill_ids in scored:
        if not skill_ids:
            continue
        corroboration = min(result.skill_corroboration.get(skill_id, 1) for skill_id in skill_ids)
        if corroboration > max(1, item.corroboration_count):
            item.corroboration_count = corroboration
            recomputed = compute_confidence(
                kind=item.kind,
                authority=item.source_authority
                if isinstance(item.source_authority, SourceAuthority)
                else None,
                occurred_at=item.occurred_at,
                locator=item.locator,
                independent_sources=corroboration,
                extraction_method=methods.get(item.kind, "deterministic"),
                weights=confidence_weights,
            )
            item.confidence = recomputed.score
            item.breakdown = recomputed

    result.evidence = [item for item, _ in scored]

    for skill_id, ids in skill_evidence_ids.items():
        confidences = [
            item.confidence for item, skills in scored if skill_id in skills and item.id in ids
        ]
        result.skill_evidence[skill_id] = ids
        result.skill_confidence[skill_id] = (
            round(sum(confidences) / len(confidences), 4) if confidences else 0.0
        )

    # ── skill nodes and their edges ──────────────────────────────────────────
    declared = {item.skill.canonical_id: item for item in profile.skills}
    all_skill_ids = sorted(set(declared) | set(skill_evidence_ids))

    for skill_id in all_skill_ids:
        profile_skill = declared.get(skill_id)
        display = profile_skill.skill.display_name if profile_skill else skill_id
        sid = node_id(GraphNodeType.SKILL, skill_id)
        confidence = result.skill_confidence.get(skill_id, 0.0)
        result.nodes.append(
            GraphNode(
                id=sid,
                type=GraphNodeType.SKILL,
                label=display,
                confidence=confidence or None,
                group=skill_id,
                meta={
                    "category": (
                        profile_skill.skill.category.value if profile_skill else "unknown"
                    ),
                    "evidence_count": len(skill_evidence_ids.get(skill_id, [])),
                    "corroboration": result.skill_corroboration.get(skill_id, 0),
                    "declared": profile_skill is not None,
                },
            )
        )
        result.edges.append(
            GraphEdge(
                id=f"{candidate_node}:HAS:{sid}",
                source=candidate_node,
                target=sid,
                relation=EvidenceRelation.HAS,
                confidence=confidence or None,
            )
        )

        # Projects and experiences that legitimately demonstrate the skill.
        for project in profile.projects:
            identifier = str(project.id) if project.id else project.name
            # Deliberately not ``pid``: that name is the node id built earlier in this
            # function, and reusing it for a possibly-missing lookup conflated two
            # different things.
            project_node = project_nodes.get(identifier)
            if project_node is None:
                continue
            blob = " ".join(
                [project.name, project.summary, project.description, *project.tech_stack]
            )
            mentions = {skill.canonical_id for skill, _, _ in extract_skill_mentions(blob)}
            if skill_id in mentions:
                result.edges.append(
                    GraphEdge(
                        id=f"{project_node}:DEMONSTRATES:{sid}",
                        source=project_node,
                        target=sid,
                        relation=EvidenceRelation.DEMONSTRATES,
                        confidence=confidence or None,
                    )
                )

    # ── evidence nodes ───────────────────────────────────────────────────────
    for item, skill_ids in scored:
        assert item.id is not None
        result.nodes.append(
            GraphNode(
                id=item.id,
                type=node_type_for(item.kind),
                label=item.title,
                confidence=item.confidence,
                group=(sorted(skill_ids)[0] if skill_ids else None),
                meta={
                    "kind": item.kind.value,
                    "locator": item.locator.display,
                    "snippet": item.snippet[:200],
                    "corroboration": item.corroboration_count,
                },
            )
        )
        for skill_id in sorted(skill_ids):
            sid = node_id(GraphNodeType.SKILL, skill_id)
            result.edges.append(
                GraphEdge(
                    id=f"{sid}:EVIDENCED_BY:{item.id}",
                    source=sid,
                    target=item.id,
                    relation=EvidenceRelation.EVIDENCED_BY,
                    confidence=item.confidence,
                )
            )
            result.links.append(
                EvidenceLink(
                    from_type=GraphNodeType.SKILL,
                    from_id=sid,
                    to_type=node_type_for(item.kind),
                    to_id=item.id,
                    relation=EvidenceRelation.EVIDENCED_BY,
                    confidence=item.confidence,
                    rationale=f"来自 {item.locator.display}",
                )
            )

    # The condition is about the *evidence*, not the profile: a graph built from
    # material that yielded no skills is the case worth warning about, even when
    # the profile itself declares plenty.
    if not skill_evidence_ids and evidence:
        result.warnings.append(
            "evidence was supplied but no taxonomy skill could be resolved from it; "
            "the graph has no skill nodes"
        )

    # ── optional job layer ───────────────────────────────────────────────────
    if job is not None:
        attach_job(result, job=job, candidate_node=candidate_node)

    return result
