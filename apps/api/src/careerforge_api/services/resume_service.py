"""Resume versions and claims: the gate's memory.

The AI core decides what is supported (``ResumeAgent`` for a whole rewrite, ``ValidatorAgent``
for one sentence). This service does what the core cannot:

1. **store the verdict, not just the text.** A claim row keeps its status, confidence, the rules
   that fired and the safer rewrite, so "why was this sentence changed" is answerable later,
   without re-running a model that may not even be configured that day;
2. **store the citations.** ``claim_evidence`` is what turns "the gate said yes" into "here is
   the file and the line". A supported claim with no citation would be an assertion wearing a
   green badge, which is the thing this product exists to prevent;
3. **keep both sides of a rewrite.** ``original_text`` holds the candidate's own wording, so a
   reviewer can judge whether the optimised version invented something rather than only seeing
   the result.

Nothing here decides a verdict. Rejecting a claim is the agent's job; this layer's job is to
refuse to lose the reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.agents.resume import optimize_resume
from careerforge_ai.agents.validator import validate_claim_text
from careerforge_ai.orchestrator import WorkflowExecutor
from careerforge_ai.schemas.claim import ClaimValidation, ResumeOptimizationResult
from careerforge_ai.schemas.common import ClaimStatus
from careerforge_ai.schemas.job import JDAnalysis
from careerforge_api.models.job_posting import Job
from careerforge_api.models.resume import ClaimEvidence, ResumeClaim, ResumeVersion
from careerforge_api.models.user import User
from careerforge_api.services.profile_service import ProfileService
from careerforge_api.services.retrieval_service import (
    EvidenceRetrieverService,
    build_retriever,
)

__all__ = ["ClaimOutcome", "ResumeService", "claim_stats_of", "integrity_of"]

#: Statuses counted as "this sentence has evidence behind it". ``partially_supported`` counts
#: because the gate only downgrades a claim when something in it is unproven, and the bullet
#: still has a citation — the UI shows the caveat separately.
_SUPPORTED = {ClaimStatus.SUPPORTED.value, ClaimStatus.PARTIALLY_SUPPORTED.value}

#: The sections the database CHECK allows; anything else is stored as ``summary``.
_SECTIONS = frozenset({"summary", "experience", "project", "skill", "education"})


def claim_stats_of(validations: list[ClaimValidation]) -> dict[str, int]:
    """``{supported: n, partially_supported: n, unsupported: n, contradicted: n}``."""
    stats = dict.fromkeys(("supported", "partially_supported", "unsupported", "contradicted"), 0)
    for validation in validations:
        stats[validation.status.value] = stats.get(validation.status.value, 0) + 1
    return stats


def integrity_of(validations: list[ClaimValidation]) -> float:
    """Share of claims with evidence behind them — the one number this feature exists for.

    A résumé with no claims scores 0.0 rather than 1.0: an empty résumé is not a well-supported
    one, and reporting 100% integrity for having written nothing would be a flattering bug.
    """
    if not validations:
        return 0.0
    supported = sum(1 for item in validations if item.status.value in _SUPPORTED)
    return round(supported / len(validations), 4)


@dataclass(slots=True)
class ClaimOutcome:
    """One validated claim, with the persisted row's id."""

    claim_id: UUID
    validation: ClaimValidation
    section: str = "summary"
    original_text: str = ""
    evidence_ids: list[UUID] = field(default_factory=list)


@dataclass(slots=True)
class OptimizeOutcome:
    """What one optimisation stored."""

    version_id: UUID
    result: ResumeOptimizationResult
    claim_stats: dict[str, int] = field(default_factory=dict)
    integrity_score: float = 0.0
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False


class ResumeService:
    """Résumé versions, claims and single-claim validation for one user."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── optimisation ─────────────────────────────────────────────────────────

    async def optimize(
        self,
        *,
        user: User,
        executor: WorkflowExecutor,
        bullets: list[dict[str, str]] | None = None,
        job: Job | None = None,
        label: str = "",
        parent_version_id: UUID | None = None,
        embedder: Any | None = None,
    ) -> OptimizeOutcome:
        """Rewrite the candidate's bullets for a target job, gating every one of them.

        The profile is read through ``ProfileService`` so the rewrite is grounded in the same
        rows every other feature sees — a bullet can only be supported by evidence the graph
        already holds.
        """
        profile = await ProfileService(self._session).load(user)
        job_analysis = self._job_analysis(job)

        # The gate can only accept a bullet it can find evidence for, so it is given a
        # retriever over this user's stored evidence. Without one it rejects everything.
        # ``ResumeAgent`` derives the rules-phase text from the profile itself, so this path
        # needs no ``evidence_text`` — the single-claim path below does, because nothing else
        # supplies it there.
        retriever = await build_retriever(self._session, user_id=user.id, embedder=embedder)

        result, outcome = await optimize_resume(
            executor,
            profile=profile,
            job=job_analysis,
            # The agent's bullet shape is ``{"section", "text"}``. Mapped explicitly rather than
            # passed through: the API's field is ``original`` (the candidate's own wording, which
            # the response returns as ``originalText``), and handing the engine a key it does not
            # read made every bullet look empty — it then politely reported having nothing to
            # rewrite, which is a silent failure rather than an error.
            bullets=[
                {
                    "section": str(bullet.get("section") or "project"),
                    "text": str(bullet.get("text") or bullet.get("original") or ""),
                }
                for bullet in (bullets or [])
            ],
            retriever=retriever,
            user_id=user.id,
        )
        if result is None:
            raise ValueError("the résumé could not be optimised from this profile")

        version = ResumeVersion(
            user_id=user.id,
            label=label or (job_analysis.role if job_analysis else "résumé"),
            target_job_id=job.id if job else None,
            source="generated",
            content_md=_render_markdown(result),
            content_json={
                "bullets": [bullet.model_dump(mode="json") for bullet in result.bullets],
                "degraded": result.degraded,
            },
            parent_version_id=parent_version_id,
            diff_summary=_diff_summary(result),
            # Computed from the validations this call is about to store, rather than copied from
            # the agent's own summary field. A version whose ``claim_stats`` reads ``{}`` beside a
            # list of claims is a summary contradicting its own contents, and the stored claims
            # are the ground truth for both numbers.
            integrity_score=integrity_of(result.validations),
            claim_stats=claim_stats_of(result.validations),
        )
        self._session.add(version)
        await self._session.flush()

        # Paired by text, not by index. Two lists that happen to have the same length are not
        # the same claim: indexing them together would attach one bullet's verdict to another
        # bullet's sentence, which is the worst possible bug in a feature about provenance.
        bullets_by_text = {bullet.optimized: bullet for bullet in result.bullets}
        for validation in result.validations:
            bullet = bullets_by_text.get(validation.claim)
            await self._store_claim(
                user=user,
                validation=validation,
                version_id=version.id,
                job_id=job.id if job else None,
                section=bullet.section if bullet else "summary",
                original_text=bullet.original if bullet else "",
            )
        await self._session.flush()

        return OptimizeOutcome(
            version_id=version.id,
            result=result,
            claim_stats=claim_stats_of(result.validations),
            integrity_score=integrity_of(result.validations),
            warnings=[*outcome.warnings, *result.new_evidence_suggestions],
            degraded=result.degraded,
        )

    @staticmethod
    def _job_analysis(job: Job | None) -> JDAnalysis | None:
        if job is None:
            return None
        return JDAnalysis.model_validate(job.analysis or {})

    async def _evidence_text(self, user: User, *, limit: int = 60, budget: int = 12_000) -> str:
        """The candidate's own material, as the rules phase reads it.

        Titles and snippets of the most confident evidence, capped in both count and length: the
        rules do token overlap, so this is a lexical aid, not an embedding input, and a bound keeps
        a candidate with a thousand fragments from turning every validation into a corpus scan.
        """
        documents = await EvidenceRetrieverService(self._session).documents(user_id=user.id)
        parts: list[str] = []
        used = 0
        for document in documents[:limit]:
            block = f"{document.title}\n{document.text}".strip()
            if not block:
                continue
            parts.append(block)
            used += len(block)
            if used >= budget:
                break
        return "\n\n".join(parts)

    # ── single-claim validation ──────────────────────────────────────────────

    async def validate(
        self,
        *,
        user: User,
        executor: WorkflowExecutor,
        text: str,
        section: str = "summary",
        job: Job | None = None,
        retriever: Any | None = None,
        embedder: Any | None = None,
    ) -> ClaimOutcome:
        """Validate one sentence and store it — with no résumé version attached.

        This is the Validator page's path: a candidate pastes a sentence they are considering and
        finds out whether they can back it up. The claim is stored on its own, which is why
        ``resume_version_id`` is nullable.
        """
        resolved = retriever or await build_retriever(
            self._session, user_id=user.id, embedder=embedder
        )
        validation, _outcome = await validate_claim_text(
            executor,
            text,
            retriever=resolved,
            user_id=user.id,
            # The deterministic rules run *before* retrieval, and they read this text. Left
            # empty, the technical-noun rule reports every technology in the sentence as
            # unmentioned — a live run had "使用 STM32 与 FreeRTOS 开发电机控制固件" come back
            # partially supported with ``skill_not_in_graph`` while citing the very document
            # that names both. Supplying the candidate's material is the documented contract for
            # callers that hold it; retrieval then augments the rules rather than replacing them.
            evidence_text=await self._evidence_text(user),
        )
        if validation is None:
            raise ValueError("the claim could not be validated")

        claim = await self._store_claim(
            user=user,
            validation=validation,
            version_id=None,
            job_id=job.id if job else None,
            section=section if section in _SECTIONS else "summary",
            original_text="",
        )
        await self._session.flush()
        return ClaimOutcome(
            claim_id=claim.id,
            validation=validation,
            section=claim.section,
            evidence_ids=[source.evidence_id for source in validation.sources],
        )

    # ── storage ──────────────────────────────────────────────────────────────

    async def _store_claim(
        self,
        *,
        user: User,
        validation: ClaimValidation,
        version_id: UUID | None,
        job_id: UUID | None,
        section: str,
        original_text: str,
    ) -> ResumeClaim:
        claim = ResumeClaim(
            user_id=user.id,
            resume_version_id=version_id,
            target_job_id=job_id,
            section=section if section in _SECTIONS else "summary",
            text=validation.claim,
            original_text=original_text or validation.claim,
            status=validation.status.value,
            confidence=float(validation.confidence),
            safe_rewrite=validation.safe_rewrite.text if validation.safe_rewrite else "",
            reasons=[
                {
                    "rule": reason.rule.value
                    if hasattr(reason.rule, "value")
                    else str(reason.rule),
                    "severity": reason.severity,
                    "message": reason.message,
                    "evidenceIds": [str(item) for item in reason.evidence_ids],
                }
                for reason in validation.reasons
            ],
            retrieval=(
                validation.retrieval.model_dump(mode="json")
                if validation.retrieval is not None
                else {}
            ),
            has_quantified_claim=validation.has_quantified_claim,
            independent_source_count=validation.independent_source_count,
            rule_version=validation.rule_version,
            model=validation.model,
            prompt_version=validation.prompt_version,
        )
        self._session.add(claim)
        await self._session.flush()

        for rank, source in enumerate(validation.sources):
            self._session.add(
                ClaimEvidence(
                    claim_id=claim.id,
                    evidence_id=source.evidence_id,
                    user_id=user.id,
                    relevance=float(source.relevance),
                    channel=(
                        source.channel.value if hasattr(source.channel, "value") else "semantic"
                    ),
                    rank=rank,
                )
            )
        return claim

    # ── reads ────────────────────────────────────────────────────────────────

    async def list_versions(self, *, user: User, limit: int = 20) -> list[ResumeVersion]:
        statement = (
            select(ResumeVersion)
            .where(ResumeVersion.user_id == user.id)
            .order_by(ResumeVersion.created_at.desc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_version(self, version_id: UUID, *, user: User) -> ResumeVersion | None:
        statement = select(ResumeVersion).where(
            ResumeVersion.id == version_id, ResumeVersion.user_id == user.id
        )
        return await self._session.scalar(statement)

    async def claims_of(self, version: ResumeVersion) -> list[ResumeClaim]:
        statement = (
            select(ResumeClaim)
            .where(ResumeClaim.resume_version_id == version.id)
            .order_by(ResumeClaim.created_at)
        )
        return list((await self._session.scalars(statement)).all())

    async def get_claim(self, claim_id: UUID, *, user: User) -> ResumeClaim | None:
        statement = select(ResumeClaim).where(
            ResumeClaim.id == claim_id, ResumeClaim.user_id == user.id
        )
        return await self._session.scalar(statement)

    async def delete_version(self, version: ResumeVersion) -> None:
        """Delete a version and everything under it (claims and citations cascade)."""
        await self._session.delete(version)
        await self._session.flush()

    async def delete_claim(self, claim: ResumeClaim) -> None:
        """Delete one claim; its citations cascade."""
        await self._session.delete(claim)
        await self._session.flush()


def _render_markdown(result: ResumeOptimizationResult) -> str:
    """The optimised résumé as text, which is what a candidate copies out."""
    if not result.bullets:
        return ""
    lines: list[str] = []
    current = ""
    for bullet in result.bullets:
        if bullet.section != current:
            current = bullet.section
            lines.append(f"\n## {current}")
        lines.append(f"- {bullet.optimized}")
    return "\n".join(lines).strip()


def _diff_summary(result: ResumeOptimizationResult) -> dict[str, Any]:
    """What changed, in a form a UI can render without re-diffing text."""
    return {
        "bullets": len(result.bullets),
        "rewritten": sum(1 for bullet in result.bullets if bullet.optimized != bullet.original),
        "rejected": len(result.rejected),
        "sections": sorted({bullet.section for bullet in result.bullets}),
    }
