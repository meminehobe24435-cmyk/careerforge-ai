"""``/jobs`` — JD analysis, the skill tree and explainable matching (``docs/API.md`` §2.6).

Two endpoints are deliberately **synchronous**, as the documented contract says:

* ``POST /jobs/analyze`` — the parse runs the JobAgent, which may call a model, but the
  response is the analysis itself rather than a handle to poll. A posting is a page of text;
  queueing it would add a poll round-trip to something a user is waiting on with a cursor in
  the box.
* ``POST /jobs/{id}/match`` — matching is deterministic arithmetic over the stored graph, so
  there is nothing to wait for.

Scoring has exactly one home (``careerforge_ai.scoring``). This router reads the engine's
numbers and serialises them; it never computes one.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from careerforge_api.core.errors import ConflictError, NotFoundError, ValidationError
from careerforge_api.deps import CurrentUser, DbSession, get_request_id
from careerforge_api.models.job_posting import JOB_SOURCES, Job
from careerforge_api.routers.ai import AIServiceDep
from careerforge_api.schemas.job import (
    AnalyzeJobRequest,
    JobDetail,
    JobListResponse,
    JobResponse,
    MatchDimensionResponse,
    MatchedSkillResponse,
    MatchResponse,
    MatchWhyResponse,
    MissedSkillResponse,
    SkillTreeResponse,
    UnknownSkillResponse,
)
from careerforge_api.services.job_service import JobService

__all__ = ["router"]

router = APIRouter(prefix="/jobs", tags=["jobs"])

MAX_LIST_LIMIT = 100


def _parse_uuid(raw: str) -> UUID:
    """A malformed id is a ``404``: it is simply an id that does not exist."""
    try:
        return UUID(raw)
    except ValueError as exc:
        raise NotFoundError("Job not found") from exc


async def _load_own(job_id: str, *, session: DbSession, user: CurrentUser) -> Job:
    job = await JobService(session).get(_parse_uuid(job_id), user=user)
    if job is None:
        raise NotFoundError("Job not found")
    return job


async def _match_score_of(session: DbSession, user: CurrentUser, job: Job) -> float | None:
    row = await JobService(session).latest_match(job=job, user=user)
    return float(row.score) if row is not None else None


@router.post("/analyze", summary="Parse a job description and store it")
async def analyze_job(
    payload: AnalyzeJobRequest,
    request: Request,
    session: DbSession,
    user: CurrentUser,
    agent: AIServiceDep,
    request_id: Annotated[str, Depends(get_request_id)],
) -> JobDetail:
    """Parse a pasted posting. Re-pasting the same text updates the existing job.

    De-duplication is on the posting text, so re-analysing after a prompt change replaces
    the analysis instead of creating a duplicate card — and keeps the match history attached
    to one job.
    """
    if payload.source not in JOB_SOURCES:
        raise ValidationError(
            f"unknown source '{payload.source}'",
            details=[
                {
                    "field": "source",
                    "issue": "not_allowed",
                    "message": f"allowed: {', '.join(JOB_SOURCES)}",
                }
            ],
        )

    service = JobService(session)
    try:
        outcome = await service.analyze(
            user=user,
            executor=agent.executor(),
            text=payload.text,
            source=payload.source,
            source_url=payload.source_url,
            request_id=request_id,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    detail = JobDetail.from_row(outcome.job, include_raw=True)
    detail.analysis["warnings"] = outcome.warnings
    return detail


@router.get("", summary="List stored job postings")
async def list_jobs(
    session: DbSession,
    user: CurrentUser,
    q: Annotated[str | None, Query(description="Substring match on the role")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> JobListResponse:
    service = JobService(session)
    jobs, total = await service.list_for_user(
        user=user, role_contains=q, limit=limit, offset=offset
    )
    items = [
        JobResponse.from_row(job, match_score=await _match_score_of(session, user, job))
        for job in jobs
    ]
    return JobListResponse(items=items, total=total)


@router.get("/{job_id}", summary="Job detail")
async def get_job(job_id: str, session: DbSession, user: CurrentUser) -> JobDetail:
    job = await _load_own(job_id, session=session, user=user)
    return JobDetail.from_row(
        job, match_score=await _match_score_of(session, user, job), include_raw=True
    )


@router.get("/{job_id}/skill-tree", summary="Required / preferred / bonus tree")
async def get_skill_tree(job_id: str, session: DbSession, user: CurrentUser) -> SkillTreeResponse:
    """The three documented levels, each requirement carrying its JD sentence.

    Unmatched requirements are included rather than filtered out: a posting that names a
    technology the taxonomy does not know is exactly the case a reader wants to see.
    """
    from careerforge_api.schemas.job import JobSkillResponse

    job = await _load_own(job_id, session=session, user=user)
    required = [JobSkillResponse.from_row(row) for row in job.skills_at("required")]
    preferred = [JobSkillResponse.from_row(row) for row in job.skills_at("preferred")]
    bonus = [JobSkillResponse.from_row(row) for row in job.skills_at("bonus")]
    unmatched = sum(1 for row in job.skills if row.canonical_id is None)
    return SkillTreeResponse(
        job_id=str(job.id),
        role=job.role,
        company=job.company_name_raw,
        required=required,
        preferred=preferred,
        bonus=bonus,
        unmatched_count=unmatched,
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a job")
async def delete_job(job_id: str, session: DbSession, user: CurrentUser) -> None:
    """Hard delete; requirement rows and match history cascade."""
    job = await _load_own(job_id, session=session, user=user)
    await JobService(session).delete(job)


@router.post("/{job_id}/match", summary="Compute and store a match")
async def match_job(
    job_id: str,
    session: DbSession,
    user: CurrentUser,
    agent: AIServiceDep,
    request_id: Annotated[str, Depends(get_request_id)],
) -> MatchResponse:
    """Compute the match against the stored evidence graph and keep the result.

    Synchronous because the scoring is deterministic arithmetic; the narrative step may
    call a model, and when it degrades the response says so instead of hiding it. Every run
    is stored, so a score that moves has a before and after.
    """
    service = JobService(session)
    job = await _load_own(job_id, session=session, user=user)
    result, warnings = await service.match(
        user=user, executor=agent.executor(), job=job, request_id=request_id
    )
    if result is None:
        raise ConflictError("匹配无法完成：岗位解析结果为空，请重新解析该岗位。")

    return MatchResponse(
        job_id=str(job.id),
        score=float(result.score),
        dimensions={
            key: MatchDimensionResponse(
                key=dimension.key,
                label=dimension.label,
                score=float(dimension.score),
                weight=float(dimension.weight),
                weighted=float(dimension.weighted),
                formula=dimension.formula,
                notes=list(dimension.notes),
                evidence_ids=[str(item) for item in dimension.evidence_ids],
            )
            for key, dimension in result.dimensions.items()
        },
        strengths=[
            MatchedSkillResponse.model_validate(item, from_attributes=True)
            for item in result.strengths
        ],
        gaps=[
            MissedSkillResponse.model_validate(item, from_attributes=True) for item in result.gaps
        ],
        unknowns=[
            UnknownSkillResponse.model_validate(item, from_attributes=True)
            for item in result.unknowns
        ],
        why=MatchWhyResponse(
            formula=result.why.formula,
            algorithm_version=result.why.algorithm_version,
            evidence_used=[str(item) for item in result.why.evidence_used],
            notes=list(result.why.notes),
            explanation=result.why.explanation,
            computed_at=result.why.computed_at,
        ),
        evidence_coverage=float(result.evidence_coverage),
        confidence=float(result.confidence),
        degraded=result.degraded,
        narrative=result.narrative,
        warnings=warnings,
    )


@router.get("/{job_id}/match", summary="The newest stored match")
async def get_match(job_id: str, session: DbSession, user: CurrentUser) -> MatchResponse:
    """The stored match, as far as the row can honestly describe it.

    ``job_matches`` keeps the score, the weights and the ``why`` block. It does **not** keep the
    evidence coverage, the confidence, the degradation state, the narrative or the warnings:
    those describe the run that produced the number, and no column holds them. They are
    therefore returned as ``null`` rather than as the model's ``0.0``/``false``/``[]`` defaults
    (PHASE 14) — a stored match used to report "Evidence Coverage 0%" beside a live endpoint
    that reported 100% for the same job, and the client had no way to tell which was real.
    Recomputing is one ``POST`` away and is the only way to get those five figures.
    """
    job = await _load_own(job_id, session=session, user=user)
    row = await JobService(session).latest_match(job=job, user=user)
    if row is None:
        raise NotFoundError("This job has not been matched yet")

    from careerforge_ai.schemas.match import MatchDimensionKey

    dimensions = {
        key: MatchDimensionResponse(
            key=key,
            label=MatchDimensionKey.LABELS.get(key, key),  # type: ignore[attr-defined]
            score=float(getattr(row, f"{key}_score")),
            weight=float((row.weights or {}).get(key, 0.0)),
            weighted=round(
                float(getattr(row, f"{key}_score")) * float((row.weights or {}).get(key, 0.0)), 2
            ),
            formula=str((row.why or {}).get("formula", "")),
            # Not stored per dimension — see ``MatchDimensionResponse``. ``None`` rather than
            # ``[]``: the Jobs page renders an empty list as "0 pieces of evidence back this
            # dimension", which is a claim the row cannot make.
            notes=None,
            evidence_ids=None,
        )
        for key in row.dimension_scores
    }
    return MatchResponse(
        job_id=str(job.id),
        score=float(row.score),
        dimensions=dimensions,
        strengths=[MatchedSkillResponse.model_validate(item) for item in row.strengths or []],
        gaps=[MissedSkillResponse.model_validate(item) for item in row.gaps or []],
        unknowns=[UnknownSkillResponse.model_validate(item) for item in row.unknowns or []],
        why=MatchWhyResponse(
            formula=str((row.why or {}).get("formula", "")),
            algorithm_version=row.algorithm_version,
            evidence_used=[str(item) for item in row.evidence_used or []],
            notes=[str(item) for item in (row.why or {}).get("notes", [])],
            explanation=str((row.why or {}).get("explanation", "")),
            computed_at=row.created_at,
        ),
        # Not measured by this endpoint — see the docstring. Null is the honest answer, and
        # the client renders it as "unavailable" instead of as a zero.
        evidence_coverage=None,
        confidence=None,
        degraded=None,
        narrative=None,
        warnings=None,
    )
