"""The optional job layer of the evidence graph.

Adding a target job turns a description of what the candidate has into a statement
about what is missing: ``REQUIRES`` edges from the job, ``MATCHES`` where the
evidence supports a requirement, and ``GAP`` where it does not.

Every ``REQUIRES`` link carries the JD sentence it came from. That is what lets
the skill-gap page say "this requirement came from *this* line" rather than
presenting an unattributed demand.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from careerforge_ai.graph.builder_types import GraphBuildResult
from careerforge_ai.graph.ids import node_id
from careerforge_ai.schemas.common import EvidenceKind, EvidenceRelation, GraphNodeType
from careerforge_ai.schemas.evidence import EvidenceLink, GraphEdge, GraphNode
from careerforge_ai.schemas.job import JDAnalysis

__all__ = ["attach_job", "node_type_for"]

_NODE_TYPE_BY_KIND: Mapping[EvidenceKind, GraphNodeType] = {
    EvidenceKind.REPO_FILE: GraphNodeType.REPO_FILE,
    EvidenceKind.COMMIT: GraphNodeType.COMMIT,
    EvidenceKind.README: GraphNodeType.DOCUMENT,
    EvidenceKind.DOCUMENT_CHUNK: GraphNodeType.DOCUMENT,
    EvidenceKind.EXPERIENCE: GraphNodeType.EXPERIENCE,
    EvidenceKind.PROJECT: GraphNodeType.PROJECT,
    EvidenceKind.ACHIEVEMENT: GraphNodeType.ACHIEVEMENT,
    EvidenceKind.MANUAL: GraphNodeType.DOCUMENT,
    EvidenceKind.LLM_INFERENCE: GraphNodeType.DOCUMENT,
}


def node_type_for(kind: EvidenceKind) -> GraphNodeType:
    """Map an evidence kind onto its graph node type."""
    return _NODE_TYPE_BY_KIND[kind]


def attach_job(
    result: GraphBuildResult,
    *,
    job: JDAnalysis,
    candidate_node: UUID,
) -> None:
    """Add the job node, its requirements, and the match/gap verdicts."""
    key = f"{job.company or 'unknown'}::{job.role or 'unknown'}"
    job_node = node_id(GraphNodeType.JOB, key)
    result.nodes.append(
        GraphNode(
            id=job_node,
            type=GraphNodeType.JOB,
            label=f"{job.role} @ {job.company}" if job.company else job.role,
            meta={"location": job.location or "", "level": job.level or ""},
        )
    )

    for jd_skill in job.all_skills:
        if not jd_skill.canonical_id:
            # An un-normalised skill cannot be joined to the graph. Recording the
            # reason beats a silent omission when someone asks why a requirement
            # is missing from the visualisation.
            result.warnings.append(
                f"job requires '{jd_skill.raw_text}' which the taxonomy did not resolve"
            )
            continue

        skill_node = node_id(GraphNodeType.SKILL, jd_skill.canonical_id)
        evidence_ids = result.skill_evidence.get(jd_skill.canonical_id, [])
        has_evidence = bool(evidence_ids)

        result.edges.append(
            GraphEdge(
                id=f"{job_node}:REQUIRES:{skill_node}",
                source=job_node,
                target=skill_node,
                relation=EvidenceRelation.REQUIRES,
            )
        )
        result.edges.append(
            GraphEdge(
                id=f"{skill_node}:{'MATCHES' if has_evidence else 'GAP'}:{job_node}",
                source=skill_node,
                target=job_node,
                relation=EvidenceRelation.MATCHES if has_evidence else EvidenceRelation.GAP,
                rationale=(
                    f"{len(evidence_ids)} 条证据支持" if has_evidence else "岗位要求但图谱中无证据"
                ),
            )
        )
        result.links.append(
            EvidenceLink(
                from_type=GraphNodeType.JOB,
                from_id=job_node,
                to_type=GraphNodeType.SKILL,
                to_id=skill_node,
                relation=EvidenceRelation.REQUIRES,
                rationale=f"JD 原文：{jd_skill.jd_evidence[:80]}",
            )
        )

    result.edges.append(
        GraphEdge(
            id=f"{candidate_node}:HAS:{job_node}",
            source=candidate_node,
            target=job_node,
            relation=EvidenceRelation.HAS,
        )
    )
