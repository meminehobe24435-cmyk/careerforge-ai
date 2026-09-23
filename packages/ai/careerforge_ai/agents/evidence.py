"""EvidenceAgent — raw material → evidence nodes and a connected graph (WF-02).

This is the bridge between "the candidate has some files" and "the candidate can
prove a claim". Its whole job is to turn material into *locatable* evidence:
every item it produces carries a locator good enough that a human can go and check
it, because evidence a person cannot verify is not evidence.

Deterministic throughout, with one exception noted below. What each source
contributes:

* a **repository file** — the file path, its language and an excerpt;
* a **commit** — the SHA, the subject and the change size;
* a **README** — a whole-document source, weaker than code but often the only
  description of why something was built;
* a **document chunk** — a heading-scoped fragment, with its page;
* a **profile entity** — an experience or project the candidate described.

Ranking those sources is not this agent's job: ``graph.build_evidence_graph``
assigns authority, specificity and corroboration, and the confidence formula turns
them into a number. Keeping ingestion and scoring apart is what lets a reviewer
audit either one on its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

from careerforge_ai.agents.base import AgentOutcome, merge_workflow_warnings
from careerforge_ai.graph import GraphBuildResult, build_evidence_graph
from careerforge_ai.orchestrator import RunContext, Step, Workflow, WorkflowExecutor
from careerforge_ai.schemas.common import EvidenceKind, SourceAuthority
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator
from careerforge_ai.schemas.github import CommitSummary, RepoFileSummary, RepoSummary
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_ai.schemas.profile import CandidateProfile

__all__ = [
    "EVIDENCE_AGENT",
    "DocumentChunkInput",
    "EvidenceAgent",
    "build_workflow",
    "build_graph",
    "evidence_from_document_chunks",
    "evidence_from_profile",
    "evidence_from_repository",
    "summarise_graph",
]

EVIDENCE_AGENT = "evidence"

#: Excerpt length stored on an evidence item. Long enough to recognise the code or
#: the argument, short enough to display in a drawer without pagination.
_EXCERPT_CHARS = 1200

#: How many significant files and commits to ingest per repository. Beyond this the
#: graph stops being readable and starts being noise.
_MAX_FILES_PER_REPO = 40
_MAX_COMMITS_PER_REPO = 40


@dataclass(slots=True)
class DocumentChunkInput:
    """One chunk of an uploaded document, already split by the ingestion layer."""

    document_id: UUID
    chunk_index: int
    content: str
    heading_path: str = ""
    page_no: int | None = None
    char_start: int = 0
    char_end: int = 0


def _excerpt(text: str, *, limit: int = _EXCERPT_CHARS) -> str:
    cleaned = text.strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


# ── material → evidence ──────────────────────────────────────────────────────


def evidence_from_document_chunks(chunks: list[DocumentChunkInput]) -> list[EvidenceItem]:
    """Turn document chunks into evidence.

    Chunks are `DOCUMENT_CHUNK` rather than `README`: a fragment of an uploaded
    document is authority-tier *uploaded document*, which sits below code and below
    a README in the confidence formula. That ordering is the product's opinion about
    what counts as proof, and it is applied here rather than argued about later.
    """
    items: list[EvidenceItem] = []
    for chunk in chunks:
        if not chunk.content.strip():
            continue
        items.append(
            EvidenceItem(
                kind=EvidenceKind.DOCUMENT_CHUNK,
                title=chunk.heading_path or f"document chunk #{chunk.chunk_index + 1}",
                snippet=_excerpt(chunk.content),
                locator=EvidenceLocator(
                    path=chunk.heading_path or None,
                    page=chunk.page_no,
                    char_start=chunk.char_start or None,
                    char_end=chunk.char_end or None,
                    section=chunk.heading_path or None,
                ),
                source_authority=SourceAuthority.UPLOADED_DOCUMENT,
                confidence=0.0,
                document_chunk_id=None,
            )
        )
    return items


def evidence_from_repository(
    repository: RepoSummary,
    *,
    files: list[RepoFileSummary] | None = None,
    commits: list[CommitSummary] | None = None,
) -> list[EvidenceItem]:
    """Turn a repository into file-, commit- and README-level evidence."""
    items: list[EvidenceItem] = []

    for file in (files or [])[:_MAX_FILES_PER_REPO]:
        if not file.is_significant:
            continue
        items.append(
            EvidenceItem(
                kind=EvidenceKind.REPO_FILE,
                title=file.path,
                snippet=_excerpt(file.content_excerpt or file.significance_reason or file.path),
                locator=EvidenceLocator(
                    path=file.path,
                    url=f"{repository.html_url}/blob/{repository.default_branch}/{file.path}"
                    if repository.html_url
                    else None,
                ),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                confidence=0.0,
                metadata={
                    "repository": repository.full_name,
                    "language": file.language or "",
                    "significance": file.significance_reason or "",
                },
            )
        )

    for commit in (commits or [])[:_MAX_COMMITS_PER_REPO]:
        if not commit.is_significant:
            continue
        items.append(
            EvidenceItem(
                kind=EvidenceKind.COMMIT,
                title=f"{commit.sha[:7]} · {commit.message.splitlines()[0][:80]}",
                snippet=_excerpt(commit.message),
                locator=EvidenceLocator(
                    sha=commit.sha,
                    url=commit.url
                    or (
                        f"{repository.html_url}/commit/{commit.sha}"
                        if repository.html_url
                        else None
                    ),
                ),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                confidence=0.0,
                occurred_at=commit.committed_at,
                metadata={
                    "repository": repository.full_name,
                    "files_changed": commit.files_changed,
                },
            )
        )

    if repository.readme_text.strip():
        items.append(
            EvidenceItem(
                kind=EvidenceKind.README,
                title=f"{repository.name}/README",
                snippet=_excerpt(repository.readme_text),
                locator=EvidenceLocator(
                    path="README.md",
                    url=f"{repository.html_url}#readme" if repository.html_url else None,
                ),
                source_authority=SourceAuthority.README,
                confidence=0.0,
                occurred_at=repository.pushed_at,
                metadata={"repository": repository.full_name},
            )
        )

    return items


def _as_datetime(value: date | None) -> datetime | None:
    """Lift a calendar date to the UTC instant it starts.

    A résumé says "2023-07", not "2023-07-01T00:00:00Z". Pydantic would coerce the date
    to midnight silently, which happens to be right but leaves the conversion implicit;
    the recency factor then reads a naive-looking value that is actually UTC. Doing it
    here keeps the schema's ``datetime`` honest and the timezone explicit.
    """
    if value is None or isinstance(value, datetime):
        return value
    return datetime.combine(value, time.min, tzinfo=UTC)


def evidence_from_profile(profile: CandidateProfile) -> list[EvidenceItem]:
    """Turn the candidate's own described entities into evidence.

    These are self-reports, so they carry the weakest authority tier that still
    counts. They exist to be *corroborated*: an experience saying "used FreeRTOS"
    plus a `freertos.c` in a repository is worth far more than either alone, and the
    corroboration factor is where that difference is realised.
    """
    items: list[EvidenceItem] = []

    for experience in profile.experiences:
        body = "\n".join([experience.description, *experience.highlights]).strip()
        if not body:
            continue
        items.append(
            EvidenceItem(
                kind=EvidenceKind.EXPERIENCE,
                title=f"{experience.company} · {experience.title}",
                snippet=_excerpt(body),
                locator=EvidenceLocator(section="experience"),
                source_authority=SourceAuthority.UPLOADED_DOCUMENT,
                confidence=0.0,
                occurred_at=_as_datetime(experience.start_date),
                metadata={"kind": experience.kind},
            )
        )

    for project in profile.projects:
        body = "\n".join([project.summary, project.description, *project.tech_stack]).strip()
        if not body:
            continue
        items.append(
            EvidenceItem(
                kind=EvidenceKind.PROJECT,
                title=project.name,
                snippet=_excerpt(body),
                locator=EvidenceLocator(section="project"),
                source_authority=SourceAuthority.UPLOADED_DOCUMENT,
                confidence=0.0,
                occurred_at=_as_datetime(project.start_date),
                metadata={"tech_stack": project.tech_stack},
            )
        )

    for achievement in profile.achievements:
        body = "\n".join([achievement.issuer or "", achievement.description]).strip()
        items.append(
            EvidenceItem(
                kind=EvidenceKind.ACHIEVEMENT,
                title=achievement.title,
                snippet=_excerpt(body or achievement.title),
                locator=EvidenceLocator(section="achievement"),
                source_authority=SourceAuthority.UPLOADED_DOCUMENT,
                confidence=0.0,
                occurred_at=_as_datetime(achievement.awarded_on),
                metadata={"kind": achievement.kind},
            )
        )

    return items


def summarise_graph(result: GraphBuildResult) -> dict[str, Any]:
    """Counts and coverage metrics for the UI's summary strip."""
    by_kind: dict[str, int] = {}
    for item in result.evidence:
        by_kind[item.kind.value] = by_kind.get(item.kind.value, 0) + 1

    return {
        "evidence": len(result.evidence),
        "evidence_by_kind": dict(sorted(by_kind.items())),
        "nodes": result.node_count,
        "edges": result.edge_count,
        "skills": len(result.skill_evidence),
        "mean_confidence": result.mean_confidence,
        "orphan_evidence": len(result.orphan_evidence),
        "orphan_evidence_ratio": (
            round(len(result.orphan_evidence) / len(result.evidence), 4) if result.evidence else 0.0
        ),
        "warnings": list(result.warnings),
    }


# ── workflow ─────────────────────────────────────────────────────────────────


def build_workflow() -> Workflow:
    """The WF-02 graph: gather → build_graph → summarise."""
    return Workflow(
        name="evidence_build",
        agent=EVIDENCE_AGENT,
        trigger="api",
        description="Turn profile entities, documents and repositories into evidence and a graph",
        steps=(
            Step(
                name="gather",
                fn=_gather,
                agent=EVIDENCE_AGENT,
                description="Normalise every material source into evidence items",
            ),
            Step(
                name="graph",
                fn=_graph,
                depends_on=("gather",),
                agent=EVIDENCE_AGENT,
                description="Assign confidence and connect the graph",
            ),
            Step(
                name="summarise",
                fn=_summarise,
                depends_on=("gather", "graph"),
                agent=EVIDENCE_AGENT,
                description="Coverage and orphan counts for the UI",
            ),
        ),
    )


async def _gather(context: RunContext, inputs: dict[str, Any]) -> list[EvidenceItem]:
    profile: CandidateProfile = context.service("profile")
    chunks: list[DocumentChunkInput] = list(context.maybe_service("document_chunks") or [])
    repositories: list[tuple[RepoSummary, list[RepoFileSummary], list[CommitSummary]]] = list(
        context.maybe_service("repositories") or []
    )

    items: list[EvidenceItem] = []
    items.extend(evidence_from_profile(profile))
    items.extend(evidence_from_document_chunks(chunks))
    for repository, files, commits in repositories:
        items.extend(evidence_from_repository(repository, files=files, commits=commits))

    if not items:
        context.metadata.setdefault("warnings", []).append("没有任何可用材料，无法构建证据图谱")
    return items


async def _graph(context: RunContext, inputs: dict[str, Any]) -> GraphBuildResult:
    profile: CandidateProfile = context.service("profile")
    job: JDAnalysis | None = context.maybe_service("job")
    evidence: list[EvidenceItem] = inputs["gather"]

    result = build_evidence_graph(
        profile=profile,
        evidence=evidence,
        job=job if isinstance(job, JDAnalysis) else None,
    )
    if result.warnings:
        context.metadata.setdefault("warnings", []).extend(result.warnings)

    context.metadata["input_ref"] = {"evidence_in": len(evidence)}
    context.metadata["output_ref"] = {
        "nodes": result.node_count,
        "edges": result.edge_count,
        "skills": len(result.skill_evidence),
    }
    return result


async def _summarise(context: RunContext, inputs: dict[str, Any]) -> dict[str, Any]:
    result: GraphBuildResult = inputs["graph"]
    return summarise_graph(result)


class EvidenceAgent:
    """Builds evidence and the graph from whatever material is available."""

    name = EVIDENCE_AGENT

    def workflow(self) -> Workflow:
        return build_workflow()

    async def run(
        self,
        executor: WorkflowExecutor,
        *,
        profile: CandidateProfile,
        document_chunks: list[DocumentChunkInput] | None = None,
        repositories: list[tuple[RepoSummary, list[RepoFileSummary], list[CommitSummary]]]
        | None = None,
        job: JDAnalysis | None = None,
    ) -> AgentOutcome:
        services: dict[str, Any] = {
            "profile": profile,
            "document_chunks": document_chunks or [],
            "repositories": repositories or [],
        }
        if job is not None:
            services["job"] = job

        output = await executor.run(self.workflow(), trigger="api", services=services)
        result: GraphBuildResult | None = output.get("graph")
        warnings = merge_workflow_warnings(output)
        warnings.extend(str(item) for item in output.metadata.get("warnings", []))

        return AgentOutcome(
            value=result,
            record=output.record,
            degraded=output.degraded,
            degradation_reason=output.degradation_reason,
            warnings=warnings,
        )


async def build_graph(
    executor: WorkflowExecutor, **kwargs: Any
) -> tuple[GraphBuildResult | None, AgentOutcome]:
    """Convenience wrapper returning both the graph and its trace."""
    outcome = await EvidenceAgent().run(executor, **kwargs)
    return outcome.value, outcome
