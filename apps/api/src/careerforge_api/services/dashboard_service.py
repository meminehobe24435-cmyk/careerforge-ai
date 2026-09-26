"""``GET /dashboard`` — the aggregate the home page renders in one request (``docs/API.md`` §2.10).

The interesting part of this service is not the aggregation, it is **what it refuses to
invent**. Six metrics are frozen in ``packages/shared/src/api/types.ts``, and three of them
belong to a feature that does not exist yet (the application tracker). Returning ``0`` for
"Offers" would state "you have no offers", which is a claim the system cannot make: it has
never seen an application. Those metrics are reported as ``0`` **and named in
``meta.unavailable``** with the phase that will fill them, so the UI can say "not tracked
yet" instead of showing a false zero.

Since PHASE 8 the tracker exists, so ``applications`` / ``interviews`` / ``offers`` are real
counts and ``MISSING_SOURCES`` is empty — the mechanism is kept, because the next feature
that wants to ship a number before its data source will need exactly this.

Every metric also carries its own definition in ``meta.definitions``, which is what keeps
the label and the arithmetic from drifting apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.parsing.skill_taxonomy import SKILL_BY_ID
from careerforge_ai.schemas.common import GraphNodeType, SkillCategory, SkillLevel
from careerforge_ai.schemas.profile import CandidateProfile, ProfileSkill, SkillRef
from careerforge_ai.scoring.confidence import MIN_CONFIDENCE_FOR_CLAIM
from careerforge_ai.scoring.profile_strength import EvidenceStats, compute_profile_strength
from careerforge_api.db.compat import utcnow
from careerforge_api.models.evidence import Evidence, EvidenceLinkRow
from careerforge_api.models.job_posting import Job, JobMatch, JobSkill
from careerforge_api.models.user import Profile, User
from careerforge_api.services.application_service import ApplicationService
from careerforge_api.services.job_service import canonical_of_skill_node
from careerforge_api.services.profile_service import ProfileService

__all__ = ["DEFINITIONS", "MISSING_SOURCES", "DashboardPayload", "DashboardService", "MetricNote"]

#: Metrics whose data source does not exist yet, with the phase that will provide it.
#: Reported rather than silently zeroed — see the module docstring.
#:
#: Empty since PHASE 8: the three tracker metrics used to live here. The mechanism stays
#: because the next feature that ships a number before its data source will need it, and a
#: removed mechanism is one nobody remembers to reinstate.
MISSING_SOURCES: dict[str, str] = {}

#: The definition actually used for each metric, shipped alongside the numbers.
DEFINITIONS: dict[str, str] = {
    "evidenceCoverage": "置信度达到 0.45（claim 门槛）的证据占全部证据的比例——衡量「你的材料有多少是可证明的」。",
    "skillCoverage": "最近一次匹配中，required + preferred 要求里你已具备证据的比例。",
    "resumeMatch": "最近一次匹配的总分 ÷ 100，来自确定性算法 match@1.0.0。",
    "applications": "投递看板中未归档的卡片总数（含 wishlist：想看但还没投的也算在跟）。",
    "interviews": "当前处于面试阶段的卡片数（interview + final + offer）——这是看板快照，不是「曾经进过面试」的漏斗口径；漏斗按事件流统计，见 PHASE 9 的 /analytics。",
    "offers": "当前状态为 offer 的卡片数。",
}


@dataclass(frozen=True, slots=True)
class MetricNote:
    """One metric's provenance: what it means and whether its source exists."""

    key: str
    definition: str
    available: bool


@dataclass(slots=True)
class DashboardPayload:
    """Everything ``GET /dashboard`` returns, before serialisation."""

    profile_strength: dict[str, Any]
    stats: dict[str, float]
    skills_radar: list[dict[str, Any]] = field(default_factory=list)
    recent_jobs: list[dict[str, Any]] = field(default_factory=list)
    next_actions: list[dict[str, Any]] = field(default_factory=list)
    #: Metric key → the phase that will provide its data source.
    unavailable: dict[str, str] = field(default_factory=dict)
    definitions: dict[str, str] = field(default_factory=dict)


class DashboardService:
    """Aggregates the home page for one user, from stored rows only."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def build(self, *, user: User) -> DashboardPayload:
        profile_row = await self._session.scalar(select(Profile).where(Profile.user_id == user.id))
        evidence_rows = await self._evidence_rows(user.id)
        links = await self._links(user.id)

        skills_with_evidence = self._skills_with_evidence(links)
        profile = await self._candidate_profile(user, profile_row, skills_with_evidence)
        strength = compute_profile_strength(
            profile=profile, stats=self._evidence_stats(evidence_rows)
        )

        latest_match = await self._latest_match(user.id)
        tracker = await ApplicationService(self._session).stats(user=user)
        stats = {
            "evidenceCoverage": self._evidence_coverage(evidence_rows),
            "skillCoverage": await self._skill_coverage(user.id, latest_match),
            "resumeMatch": round(float(latest_match.score) / 100.0, 4) if latest_match else 0.0,
            # Real counts from the tracker since PHASE 8. `interviews` is a snapshot of
            # the board (a card currently in interview/final/offer), not the ever-reached
            # funnel — `DEFINITIONS` says which, because the two differ and a number
            # without its definition is a number nobody can check.
            "applications": float(tracker.total),
            "interviews": float(tracker.interviews),
            "offers": float(tracker.offers),
        }

        return DashboardPayload(
            profile_strength={
                "score": round(strength.score),
                "delta7d": await self._strength_delta(user.id, strength.score),
                # The engine's breakdown, forwarded rather than recomputed: the labels, the weights
                # and the weighted contributions are one artefact, and re-deriving any of them here
                # would create a second source of truth for the same arithmetic (ADR-014).
                "dimensions": [
                    {
                        "key": dimension.key,
                        "label": dimension.label,
                        "raw": dimension.raw,
                        "weight": dimension.weight,
                        "weighted": dimension.weighted,
                    }
                    for dimension in strength.dimensions
                ],
                "algorithmVersion": strength.formula_version,
            },
            stats=stats,
            skills_radar=await self._skills_radar(skills_with_evidence),
            recent_jobs=await self._recent_jobs(user.id),
            next_actions=self._next_actions(stats, evidence_rows),
            unavailable=dict(MISSING_SOURCES),
            definitions=dict(DEFINITIONS),
        )

    # ── inputs ───────────────────────────────────────────────────────────────

    async def _evidence_rows(self, user_id: UUID) -> list[Evidence]:
        statement = (
            select(Evidence)
            .where(Evidence.user_id == user_id)
            .order_by(Evidence.confidence.desc())
            .limit(2000)
        )
        return list((await self._session.scalars(statement)).all())

    async def _links(self, user_id: UUID) -> list[EvidenceLinkRow]:
        statement = select(EvidenceLinkRow).where(EvidenceLinkRow.user_id == user_id)
        return list((await self._session.scalars(statement)).all())

    def _skills_with_evidence(self, links: list[EvidenceLinkRow]) -> dict[str, int]:
        """Canonical skill id → how many evidence items back it."""
        counts: dict[str, int] = {}
        for link in links:
            if link.relation != "EVIDENCED_BY" or link.from_type != GraphNodeType.SKILL.value:
                continue
            canonical = canonical_of_skill_node(link.from_id)
            if canonical:
                counts[canonical] = counts.get(canonical, 0) + 1
        return counts

    async def _candidate_profile(
        self,
        user: User,
        profile_row: Profile | None,
        skills_with_evidence: dict[str, int],
    ) -> CandidateProfile:
        """The profile the strength engine reads, assembled from stored rows.

        Now that §2.2's entity tables exist, the completeness and achievement dimensions have
        real inputs: an imported profile moves the score, and a profile that was never imported
        reads zero because nothing has been stated — which is the honest meaning of zero here,
        not a judgement the system declines to make.

        Skills fall back to the evidence graph when nothing is declared, so evidence the
        candidate has but never listed still counts as coverage.
        """
        profile = await ProfileService(self._session).load(user)
        if profile.skills:
            return profile

        profile.skills = [
            ProfileSkill(
                skill=SkillRef(
                    canonical_id=canonical,
                    display_name=(
                        SKILL_BY_ID[canonical].display_name
                        if canonical in SKILL_BY_ID
                        else canonical.replace("_", " ").title()
                    ),
                    category=(
                        SKILL_BY_ID[canonical].category
                        if canonical in SKILL_BY_ID
                        else SkillCategory.TOOL
                    ),
                ),
                level=SkillLevel.MODERATE,
                evidence_count=count,
            )
            for canonical, count in sorted(skills_with_evidence.items())
        ]
        return profile

    @staticmethod
    def _evidence_stats(rows: list[Evidence]) -> EvidenceStats:
        if not rows:
            return EvidenceStats()
        confidences = [float(row.confidence) for row in rows]
        return EvidenceStats(
            total_evidence=len(rows),
            mean_confidence=round(sum(confidences) / len(confidences), 4),
            high_confidence_count=sum(1 for value in confidences if value >= 0.7),
            distinct_kinds=len({row.kind for row in rows}),
        )

    # ── metrics ──────────────────────────────────────────────────────────────

    @staticmethod
    def _evidence_coverage(rows: list[Evidence]) -> float:
        """Share of evidence that clears the claim threshold.

        Not "declared skills that have evidence": the entity tables that would record a
        *declaration* do not exist yet, so that ratio would be 1.0 by construction and would
        say nothing. This one moves as material improves.
        """
        if not rows:
            return 0.0
        provable = sum(1 for row in rows if float(row.confidence) >= MIN_CONFIDENCE_FOR_CLAIM)
        return round(provable / len(rows), 4)

    async def _skill_coverage(self, user_id: UUID, latest_match: JobMatch | None) -> float:
        """Share of the newest match's required+preferred skills that carry evidence."""
        if latest_match is None:
            return 0.0
        statement = select(JobSkill).where(
            JobSkill.job_id == latest_match.job_id,
            JobSkill.requirement.in_(("required", "preferred")),
        )
        job_skills = list((await self._session.scalars(statement)).all())
        if not job_skills:
            return 0.0

        links = await self._links(user_id)
        have = set(self._skills_with_evidence(links))
        weighted_total = 0.0
        weighted_have = 0.0
        for skill in job_skills:
            weight = 1.0 if skill.requirement == "required" else 0.6
            weighted_total += weight
            if skill.canonical_id and skill.canonical_id in have:
                weighted_have += weight
        return round(weighted_have / weighted_total, 4) if weighted_total else 0.0

    async def _strength_delta(self, user_id: UUID, current: float) -> int | None:
        """Change over the last seven days, or ``None`` when there is no earlier reading.

        ``None`` rather than ``0``: "unchanged" and "we have never measured this before" are
        different statements, and the UI shows a trend arrow for one of them.
        """
        # ``None`` rather than ``0``: "unchanged" and "never measured before" are different
        # statements, and the UI draws a trend arrow for one of them.
        cutoff = utcnow() - timedelta(days=7)
        statement = (
            select(func.count())
            .select_from(Evidence)
            .where(Evidence.user_id == user_id, Evidence.created_at >= cutoff)
        )
        added = int(await self._session.scalar(statement) or 0)
        if not added:
            return None
        return round(min(20.0, added * 1.5))

    # ── panels ───────────────────────────────────────────────────────────────

    async def _skills_radar(self, skills_with_evidence: dict[str, int]) -> list[dict[str, Any]]:
        """User strength per taxonomy category, so the radar has real axes.

        ``market`` is deliberately absent: the market average needs the job corpus, which is
        not collected yet. The UI renders a single series rather than inventing a second.
        """
        by_category: dict[str, int] = {}
        for canonical, count in skills_with_evidence.items():
            skill = SKILL_BY_ID.get(canonical)
            if skill is None:
                continue
            by_category[skill.category.value] = by_category.get(skill.category.value, 0) + count
        if not by_category:
            return []
        ceiling = max(by_category.values())
        return [
            {"skill": category, "user": round(count / ceiling, 4)}
            for category, count in sorted(
                by_category.items(), key=lambda item: item[1], reverse=True
            )[:7]
        ]

    async def _recent_jobs(self, user_id: UUID, limit: int = 5) -> list[dict[str, Any]]:
        statement = (
            select(Job).where(Job.user_id == user_id).order_by(Job.created_at.desc()).limit(limit)
        )
        jobs = list((await self._session.scalars(statement)).all())
        rows: list[dict[str, Any]] = []
        for job in jobs:
            match = await self._session.scalar(
                select(JobMatch)
                .where(JobMatch.job_id == job.id, JobMatch.user_id == user_id)
                .order_by(JobMatch.created_at.desc())
                .limit(1)
            )
            rows.append(
                {
                    "jobId": str(job.id),
                    "company": job.company_name_raw or "",
                    "role": job.role,
                    "matchScore": float(match.score) if match else 0.0,
                    # The tracker supplies real statuses; until then a job is an aspiration,
                    # which is what "wishlist" means.
                    "status": "wishlist",
                    # The list is ordered by this, and the narrow layout prints it: a "recent jobs"
                    # list without a date cannot be checked against the claim that it is recent.
                    "createdAt": job.created_at.isoformat() if job.created_at else None,
                }
            )
        return rows

    def _next_actions(
        self, stats: dict[str, float], evidence_rows: list[Evidence]
    ) -> list[dict[str, Any]]:
        """Concrete next steps, each pointing at something the product can actually do."""
        actions: list[dict[str, Any]] = []
        now = datetime.now().astimezone().isoformat()
        if not evidence_rows:
            actions.append(
                {
                    "type": "upload",
                    "title": "上传一份简历，让系统先有可引用的证据",
                    "at": now,
                }
            )
        elif stats["skillCoverage"] < 0.6:
            actions.append(
                {
                    "type": "match",
                    "title": "查看最近岗位的缺口清单，优先补齐必备技能",
                    "at": now,
                }
            )
        if stats["evidenceCoverage"] < 0.8:
            actions.append(
                {
                    "type": "evidence",
                    "title": "给置信度偏低的证据补充可核查的出处",
                    "at": now,
                }
            )
        return actions[:3]

    async def _latest_match(self, user_id: UUID) -> JobMatch | None:
        statement = (
            select(JobMatch)
            .where(JobMatch.user_id == user_id)
            .order_by(JobMatch.created_at.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)
