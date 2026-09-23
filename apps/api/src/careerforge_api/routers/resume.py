"""``/resume`` and the Claim Validator (``docs/API.md`` §2.6/§2.9, §2.5).

Two surfaces, one gate:

* ``POST /resume/optimize`` rewrites the candidate's bullets for a target job and stores the
  result as a version — every bullet gated, every verdict kept;
* ``POST /evidence/validate`` checks a single sentence the candidate is *considering*, with no
  résumé version attached. That is the Validator page's whole purpose, and it is why
  ``resume_claims.resume_version_id`` is nullable.

Both are synchronous. Scoring and rule-checking are deterministic and local; the only network
call is the optional narrative, and when it degrades the response says so.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, status

from careerforge_ai.schemas.claim import ClaimValidation
from careerforge_api.core.errors import NotFoundError, ValidationError
from careerforge_api.deps import CurrentUser, DbSession
from careerforge_api.models.resume import CLAIM_SECTIONS
from careerforge_api.routers.ai import AIServiceDep
from careerforge_api.schemas.resume import (
    ClaimValidationResponse,
    ResumeClaimResponse,
    ResumeOptimizeRequest,
    ResumeVersionDetail,
    ResumeVersionResponse,
    ValidateClaimRequest,
    ValidateClaimResponse,
)
from careerforge_api.services.job_service import JobService
from careerforge_api.services.resume_service import ResumeService

__all__ = ["router", "validator_router"]

router = APIRouter(prefix="/resume", tags=["resume"])
#: The validator endpoints live under ``/evidence`` per ``docs/API.md`` §2.5, but belong to this
#: feature; a second router keeps the mount honest without splitting the implementation.
validator_router = APIRouter(tags=["resume"])

MAX_BATCH = 20


def _parse_uuid(raw: str, *, what: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError as exc:
        raise NotFoundError(f"{what} not found") from exc


def _claim_response(claim: object) -> ResumeClaimResponse:
    return ResumeClaimResponse.from_row(claim)  # type: ignore[arg-type]


@router.post("/optimize", summary="Rewrite bullets for a target job, gating every one")
async def optimize_resume_endpoint(
    payload: ResumeOptimizeRequest,
    session: DbSession,
    user: CurrentUser,
    agent: AIServiceDep,
) -> ResumeVersionDetail:
    """The Copilot path. A bullet whose claim cannot be supported is reported, not reworded.

    That distinction is the product: an unsupported sentence comes back with the reason it failed
    and a safer version *only* when a safer version is honest. Suggesting a smoother phrasing of
    something unprovable would be the failure this feature exists to avoid.
    """
    job = None
    if payload.job_id:
        job = await JobService(session).get(_parse_uuid(payload.job_id, what="Job"), user=user)
        if job is None:
            raise NotFoundError("Job not found")

    service = ResumeService(session)
    try:
        outcome = await service.optimize(
            user=user,
            executor=agent.executor(),
            bullets=[bullet.model_dump() for bullet in payload.bullets],
            job=job,
            label=payload.label,
            embedder=agent.embedder(),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    version = await service.get_version(outcome.version_id, user=user)
    assert version is not None  # written in this transaction
    claims = await service.claims_of(version)
    detail = ResumeVersionDetail.from_row(
        version, claims=[_claim_response(claim) for claim in claims]
    )
    detail.warnings = outcome.warnings
    detail.degraded = outcome.degraded
    return detail


@router.get("/versions", summary="Stored résumé versions")
async def list_versions(
    session: DbSession,
    user: CurrentUser,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ResumeVersionResponse]:
    versions = await ResumeService(session).list_versions(user=user, limit=limit)
    return [ResumeVersionResponse.from_row(version) for version in versions]


@router.get("/versions/{version_id}", summary="A version with its claims and citations")
async def get_version(
    version_id: str, session: DbSession, user: CurrentUser
) -> ResumeVersionDetail:
    service = ResumeService(session)
    version = await service.get_version(_parse_uuid(version_id, what="Resume version"), user=user)
    if version is None:
        raise NotFoundError("Resume version not found")
    claims = await service.claims_of(version)
    return ResumeVersionDetail.from_row(
        version, claims=[_claim_response(claim) for claim in claims]
    )


@router.delete(
    "/versions/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a version, its claims and their citations",
)
async def delete_version(version_id: str, session: DbSession, user: CurrentUser) -> None:
    service = ResumeService(session)
    version = await service.get_version(_parse_uuid(version_id, what="Resume version"), user=user)
    if version is None:
        raise NotFoundError("Resume version not found")
    await service.delete_version(version)


def _validation_response(claim_id: UUID, validation: ClaimValidation) -> ValidateClaimResponse:
    return ValidateClaimResponse(
        claim_id=str(claim_id),
        claim=ClaimValidationResponse.from_schema(validation),
    )


@validator_router.post("/evidence/validate", summary="Claim Validator — one sentence")
async def validate_one(
    payload: ValidateClaimRequest,
    session: DbSession,
    user: CurrentUser,
    agent: AIServiceDep,
) -> ValidateClaimResponse:
    """Check one sentence against the candidate's own evidence.

    No version is created: this is the page where someone pastes a line they are *considering*
    and finds out whether they can back it up before it reaches a résumé.
    """
    if payload.section not in CLAIM_SECTIONS:
        raise ValidationError(
            f"unknown section '{payload.section}'",
            details=[
                {
                    "field": "section",
                    "issue": "not_allowed",
                    "message": f"allowed: {', '.join(CLAIM_SECTIONS)}",
                }
            ],
        )
    job = None
    if payload.job_id:
        job = await JobService(session).get(_parse_uuid(payload.job_id, what="Job"), user=user)
        if job is None:
            raise NotFoundError("Job not found")

    service = ResumeService(session)
    try:
        outcome = await service.validate(
            user=user,
            executor=agent.executor(),
            text=payload.text,
            section=payload.section,
            job=job,
            embedder=agent.embedder(),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    return _validation_response(outcome.claim_id, outcome.validation)


@validator_router.post("/evidence/validate/batch", summary="Claim Validator — up to 20")
async def validate_batch(
    payload: list[ValidateClaimRequest],
    session: DbSession,
    user: CurrentUser,
    agent: AIServiceDep,
) -> list[ValidateClaimResponse]:
    """Validate several sentences in one call.

    Bounded at 20 and synchronous. Each claim is stored on its own, so a failure part-way
    through leaves the successful ones behind rather than discarding work the user watched
    happen — the response reports them in the order they were sent.
    """
    if not payload:
        raise ValidationError(
            "send at least one claim", details=[{"field": "claims", "issue": "missing"}]
        )
    if len(payload) > MAX_BATCH:
        raise ValidationError(
            f"at most {MAX_BATCH} claims per request (got {len(payload)})",
            details=[{"field": "claims", "issue": "too_many"}],
        )

    service = ResumeService(session)
    responses: list[ValidateClaimResponse] = []
    for item in payload:
        try:
            outcome = await service.validate(
                user=user,
                executor=agent.executor(),
                text=item.text,
                section=item.section if item.section in CLAIM_SECTIONS else "summary",
            )
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        responses.append(_validation_response(outcome.claim_id, outcome.validation))
    return responses
