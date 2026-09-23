"""Job analysis and matching, persisted.

The engine does the thinking (``careerforge_ai.agents.job`` / ``.match``); this service
does what needs a database:

1. run ``JobAgent`` over the pasted text and store the resulting ``JDAnalysis`` both as the
   audit record (``analysis``) and as queryable rows (``job_skills``) — the skill tree and
   the gap query are traversals over those rows, not JSON parsing at read time;
2. rebuild the *engine-level* graph from the stored evidence rows, because the match
   engine consumes a ``GraphBuildResult`` (``skill_evidence`` and ``skill_confidence``),
   not the API's node/edge payload;
3. persist each computed match as a new row. History is kept rather than overwritten: when
   a score moves, the previous row says what it moved from and which version produced it.

Nothing here decides a score. ``docs/ARCHITECTURE.md`` §6 keeps the numbers in the scoring
engine precisely so that a service layer cannot drift into inventing them.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.agents.job import build_jd_analysis
from careerforge_ai.agents.match import compute_match
from careerforge_ai.graph import node_id as node_id_for_skill
from careerforge_ai.graph.builder_types import GraphBuildResult
from careerforge_ai.orchestrator import WorkflowExecutor
from careerforge_ai.parsing.skill_taxonomy import SKILL_BY_ID, SKILLS
from careerforge_ai.schemas.common import (
    EvidenceKind,
    GraphNodeType,
    SkillCategory,
    SkillLevel,
    SourceAuthority,
)
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator
from careerforge_ai.schemas.job import JDAnalysis, JDSkill, RequirementLevel
from careerforge_ai.schemas.match import JobMatchResult
from careerforge_ai.schemas.profile import CandidateProfile, ProfileSkill, SkillRef
from careerforge_api.models.evidence import Evidence
from careerforge_api.models.job_posting import Job
from careerforge_api.models.user import Profile, User
from careerforge_api.repositories.evidence_repository import EvidenceRepository
from careerforge_api.repositories.job_repository import JobRepository

__all__ = ["JobAnalysisOutcome", "JobService"]

#: Requirement level → the order the UI draws them in.
_LEVELS = (RequirementLevel.REQUIRED, RequirementLevel.PREFERRED, RequirementLevel.BONUS)


class JobAnalysisOutcome:
    """What one analysis pass produced."""

    __slots__ = ("analysis", "created", "job", "skill_count", "warnings")

    def __init__(
        self,
        *,
        job: Job,
        analysis: JDAnalysis,
        skill_count: int,
        created: bool,
        warnings: list[str],
    ) -> None:
        self.job = job
        self.analysis = analysis
        self.skill_count = skill_count
        self.created = created
        self.warnings = warnings


def description_hash(text: str) -> str:
    """De-duplication key for a posting: the text as pasted, whitespace-normalised."""
    normalised = "\n".join(line.strip() for line in text.strip().splitlines())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


class JobService:
    """Analysis and matching for one user."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._jobs = JobRepository(session)
        self._evidence = EvidenceRepository(session)

    # ── analysis ─────────────────────────────────────────────────────────────

    async def analyze(
        self,
        *,
        user: User,
        executor: WorkflowExecutor,
        text: str,
        source: str = "paste",
        source_url: str | None = None,
        request_id: str | None = None,
    ) -> JobAnalysisOutcome:
        """Parse a posting and persist it.

        Raises:
            ValueError: the text is empty, or the parser returned nothing usable — a job
                row with no analysis would render as an empty card, which is worse than an
                error the caller can act on.
        """
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("the job description is empty")

        analysis, outcome = await build_jd_analysis(executor, cleaned)
        if analysis is None:
            raise ValueError("the job description could not be parsed")

        job, created = await self._jobs.upsert(
            user_id=user.id,
            description_sha256=description_hash(cleaned),
            fields={
                "company_name_raw": analysis.company,
                "role": analysis.role or "（未识别岗位名称）",
                "level": analysis.level,
                "location": analysis.location,
                "remote_type": analysis.remote_type,
                "employment_type": analysis.employment_type,
                "salary_min": analysis.salary_min,
                "salary_max": analysis.salary_max,
                "salary_currency": analysis.salary_currency,
                "education_requirement": analysis.education_requirement,
                "years_experience_min": analysis.years_experience_min,
                "description_raw": cleaned,
                "source": source,
                "source_url": source_url,
                "analysis": analysis.model_dump(mode="json"),
                "responsibilities": list(analysis.responsibilities),
                "nice_to_have": list(analysis.nice_to_have),
                "keywords": list(analysis.keywords),
                "parse_status": self._status_for(analysis),
                "parse_confidence": float(analysis.parse_confidence),
            },
        )
        skill_count = await self._jobs.replace_skills(job, self._skill_rows(job, analysis))
        await self._session.flush()
        _ = request_id  # the executor records it on the run row; kept for signature symmetry

        return JobAnalysisOutcome(
            job=job,
            analysis=analysis,
            skill_count=skill_count,
            created=created,
            warnings=list(outcome.warnings),
        )

    @staticmethod
    def _status_for(analysis: JDAnalysis) -> str:
        """Map the analysis' own status onto the documented ``parse_status`` values.

        ``heuristic_fallback`` is the honest label when the parse ran without a model: the
        row itself carries the distinction, so a later re-parse with a real provider is
        visible rather than silent.
        """
        if analysis.degraded:
            return "heuristic_fallback"
        status = analysis.parse_status
        return status if status in {"parsed", "failed", "pending"} else "parsed"

    def _skill_rows(self, job: Job, analysis: JDAnalysis) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for level in _LEVELS:
            skills: list[JDSkill] = list(getattr(analysis, f"{level.value}_skills", []))

            for skill in skills:
                # ``dedupe_key`` is the canonical id when the taxonomy matched and the raw
                # text otherwise, so the unique constraint keeps working for unmatched
                # skills (a nullable column would make NULL never compare equal).
                key = skill.canonical_id or skill.raw_text.strip().lower()
                if not key or (key, level.value) in seen:
                    continue
                seen.add((key, level.value))
                rows.append(
                    {
                        "canonical_id": skill.canonical_id,
                        "raw_text": skill.raw_text,
                        "requirement": level.value,
                        "weight": float(skill.weight),
                        "jd_evidence": skill.jd_evidence,
                        "mentions": skill.mentions,
                        "dedupe_key": key,
                    }
                )
        return rows

    # ── matching ─────────────────────────────────────────────────────────────

    async def match(
        self,
        *,
        user: User,
        executor: WorkflowExecutor,
        job: Job,
        request_id: str | None = None,
    ) -> tuple[JobMatchResult | None, list[str]]:
        """Compute and store a match against the user's stored evidence graph."""
        analysis = JDAnalysis.model_validate(job.analysis or {})
        profile = await self._profile_of(user)
        graph, warnings = await self.build_graph_result(user_id=user.id, profile=profile)

        result, outcome = await compute_match(executor, job=analysis, profile=profile, graph=graph)
        warnings.extend(outcome.warnings)
        if result is None:
            return None, warnings

        await self._jobs.add_match(
            user_id=user.id,
            job_id=job.id,
            score=result.score,
            skill_score=result.dimensions["skill"].score,
            experience_score=result.dimensions["experience"].score,
            project_score=result.dimensions["project"].score,
            education_score=result.dimensions["education"].score,
            evidence_score=result.dimensions["evidence"].score,
            weights={key: dimension.weight for key, dimension in result.dimensions.items()},
            strengths=[item.model_dump(mode="json") for item in result.strengths],
            gaps=[item.model_dump(mode="json") for item in result.gaps],
            unknowns=[item.model_dump(mode="json") for item in result.unknowns],
            why=result.why.model_dump(mode="json"),
            evidence_used=[str(item) for item in result.why.evidence_used],
            algorithm_version=result.why.algorithm_version,
            model=None if outcome.degraded else executor.provider.name,
        )
        await self._session.flush()
        _ = request_id
        return result, warnings

    async def build_graph_result(
        self, *, user_id: UUID, profile: CandidateProfile
    ) -> tuple[GraphBuildResult | None, list[str]]:
        """Rebuild the engine-level graph from stored evidence.

        The match engine reads ``skill_evidence`` (skill → evidence ids) and
        ``skill_confidence`` (skill → mean confidence). Both are derivable from the stored
        rows — evidence plus ``EVIDENCED_BY`` edges — so the engine can run against the
        database without a second, differently-shaped graph representation existing.

        Returns ``(None, warnings)`` when there is no evidence at all: the engine records
        that the evidence dimension has nothing to measure rather than scoring it as zero.
        """
        rows = await self._evidence.list_for_user(user_id=user_id, limit=2000)
        if not rows:
            return None, ["尚无证据：请先上传简历并运行分析，证据强度维度才有数据可算。"]

        items = [_evidence_item(row) for row in rows]
        links = await self._evidence.list_links(user_id=user_id)

        skill_evidence: dict[str, list[UUID]] = {}
        for link in links:
            if link.relation != "EVIDENCED_BY" or link.from_type != GraphNodeType.SKILL.value:
                continue
            canonical = canonical_of_skill_node(link.from_id)
            if canonical:
                skill_evidence.setdefault(canonical, []).append(link.to_id)

        by_id = {row.id: row for row in rows}
        skill_confidence: dict[str, float] = {}
        for canonical, ids in skill_evidence.items():
            confidences = [float(by_id[item].confidence) for item in ids if item in by_id]
            if confidences:
                skill_confidence[canonical] = round(sum(confidences) / len(confidences), 4)

        return (
            GraphBuildResult(
                evidence=items,
                skill_evidence=skill_evidence,
                skill_confidence=skill_confidence,
                skill_corroboration={key: len(value) for key, value in skill_evidence.items()},
            ),
            [],
        )

    async def _profile_of(self, user: User) -> CandidateProfile:
        """The profile the match engine reads, filled from the stored rows.

        Skills are declared from the **evidence graph** rather than from ``profile.skills``:
        the entity tables (§2.2) arrive with the profile phase, and an empty declaration list
        would make every required skill look unmatched even when evidence for it exists —
        the score would be wrong in the direction that flatters nobody.
        """
        profile_row = await self._session.scalar(select(Profile).where(Profile.user_id == user.id))
        links = await self._evidence.list_links(user_id=user.id)

        counts: dict[str, int] = {}
        for link in links:
            if link.relation != "EVIDENCED_BY" or link.from_type != GraphNodeType.SKILL.value:
                continue
            canonical = canonical_of_skill_node(link.from_id)
            if canonical:
                counts[canonical] = counts.get(canonical, 0) + 1

        skills = [
            ProfileSkill(
                skill=SkillRef(
                    canonical_id=canonical,
                    display_name=SKILL_BY_ID[canonical].display_name
                    if canonical in SKILL_BY_ID
                    else canonical.replace("_", " ").title(),
                    category=SKILL_BY_ID[canonical].category
                    if canonical in SKILL_BY_ID
                    else SkillCategory.TOOL,
                ),
                level=SkillLevel.MODERATE,
                evidence_count=count,
            )
            for canonical, count in sorted(counts.items())
        ]

        slug = (
            profile_row.slug
            if profile_row is not None and profile_row.slug
            else f"user-{user.id.hex[:8]}"
        )
        headline = (
            profile_row.headline
            if profile_row is not None and profile_row.headline
            else user.display_name
        )
        return CandidateProfile(slug=slug, headline=headline, skills=skills)

    # ── reads ────────────────────────────────────────────────────────────────

    async def get(self, job_id: UUID, *, user: User) -> Job | None:
        return await self._jobs.get(job_id, user_id=user.id)

    async def list_for_user(
        self, *, user: User, role_contains: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[Job], int]:
        jobs = list(
            await self._jobs.list_for_user(
                user_id=user.id, role_contains=role_contains, limit=limit, offset=offset
            )
        )
        return jobs, await self._jobs.count(user_id=user.id)

    async def delete(self, job: Job) -> None:
        await self._jobs.delete(job)

    async def latest_match(self, *, job: Job, user: User) -> Any:
        return await self._jobs.latest_match(job_id=job.id, user_id=user.id)

    async def match_history(self, *, job: Job, user: User) -> list[Any]:
        return list(await self._jobs.match_history(job_id=job.id, user_id=user.id))


def _evidence_item(row: Evidence) -> EvidenceItem:
    """Rebuild an engine value object from a stored row."""
    return EvidenceItem(
        id=row.id,
        kind=EvidenceKind(row.kind),
        title=row.title,
        snippet=row.snippet,
        locator=EvidenceLocator.model_validate(row.locator or {}),
        confidence=float(row.confidence),
        source_authority=_authority(float(row.source_authority)),
        occurred_at=row.occurred_at,
        corroboration_count=row.corroboration_count,
        document_chunk_id=row.document_chunk_id,
        content_hash=row.content_hash,
        metadata=dict(row.metadata_ or {}),
    )


def _authority(score: float) -> SourceAuthority:
    """Nearest authority tier for a stored score — the tier, not the score, is what
    ``EvidenceItem`` carries; the exact factor lives in the row."""
    from careerforge_ai.scoring.confidence import AUTHORITY_SCORES

    return min(AUTHORITY_SCORES, key=lambda tier: abs(AUTHORITY_SCORES[tier] - score))


#: Skill node id → canonical id, built once at import.
#:
#: The graph derives a skill node's id from its canonical id (``graph.node_id``), so the
#: reverse lookup is a dictionary over the taxonomy — about a hundred entries, fixed for the
#: life of the process.
SKILL_NODE_IDS: dict[UUID, str] = {
    node_id_for_skill(GraphNodeType.SKILL, skill.canonical_id): skill.canonical_id
    for skill in SKILLS
}


def canonical_of_skill_node(node: UUID) -> str | None:
    """Canonical id behind a skill node id, or ``None`` when it is not a known skill."""
    return SKILL_NODE_IDS.get(node)
