"""``/profile`` — extraction and the stored candidate profile (``docs/API.md`` §2.2).

``POST /profile/import`` runs the ProfileAgent over text (or over a stored document's text)
and persists the result. ``GET /profile`` returns what is stored, so a client can render the
profile without re-running extraction — and, more importantly, so a *correction* is possible
on a row rather than only on a transcript.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from careerforge_api.core.errors import NotFoundError, ValidationError
from careerforge_api.deps import CurrentUser, DbSession
from careerforge_api.models.profile_entity import ENTITY_ORIGINS
from careerforge_api.routers.ai import AIServiceDep
from careerforge_api.schemas.profile import ProfileImportAccepted, ProfileResponse
from careerforge_api.services.document_service import DocumentService
from careerforge_api.services.profile_service import ProfileService

__all__ = ["router"]

router = APIRouter(prefix="/profile", tags=["profile"])


class ImportProfileRequest(BaseModel):
    """Either text or a stored document id. Unknown fields are refused.

    ``origin`` is accepted so an importer can label its own output honestly
    (``import`` for a file, ``user_corrected`` for a paste a human fixed) instead of having
    the server assume.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    text: str | None = Field(default=None, max_length=200_000)
    document_id: str | None = Field(default=None, alias="documentId")
    origin: str = Field(default="import", description=" | ".join(ENTITY_ORIGINS))


@router.post("/import", summary="Extract and store a candidate profile")
async def import_profile_endpoint(
    payload: ImportProfileRequest,
    session: DbSession,
    user: CurrentUser,
    agent: AIServiceDep,
) -> ProfileImportAccepted:
    """Extract entities from text and persist them.

    Re-importing replaces the entity rows rather than appending: a résumé re-exported with one
    sentence reworded is the same profile, and appending would multiply it. The natural key
    that makes this safe is recorded on every row.
    """
    if payload.origin not in ENTITY_ORIGINS:
        raise ValidationError(
            f"unknown origin '{payload.origin}'",
            details=[
                {
                    "field": "origin",
                    "issue": "not_allowed",
                    "message": f"allowed: {', '.join(ENTITY_ORIGINS)}",
                }
            ],
        )
    if not payload.text and not payload.document_id:
        raise ValidationError(
            "provide either text or a documentId",
            details=[{"field": "text", "issue": "missing"}],
        )

    document = None
    text = payload.text or ""
    if payload.document_id:
        try:
            document_id = UUID(payload.document_id)
        except ValueError as exc:
            raise NotFoundError("Document not found") from exc
        document = await DocumentService(session).get(document_id, user=user)
        if document is None:
            raise NotFoundError("Document not found")
        if not document.raw_text:
            # Local Mode keeps no text, so there is nothing to extract from — and saying
            # which rule applied is more useful than an empty profile.
            raise ValidationError(
                f"{document.filename} has no stored text; raw-text retention is disabled "
                "for this account, so upload the text directly instead"
            )
        text = document.raw_text

    service = ProfileService(session)
    try:
        outcome = await service.import_text(
            user=user,
            executor=agent.executor(),
            text=text,
            source_kind="resume",
            document=document,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    stored = await service.load(user)
    return ProfileImportAccepted(
        counts=outcome.counts,
        skills_normalised=outcome.skills_normalised,
        unmapped_skills=outcome.unmapped_skills,
        warnings=outcome.warnings,
        degraded=outcome.degraded,
        document_id=str(outcome.document_id) if outcome.document_id else None,
        profile=ProfileResponse.from_schema(stored, declared_skills=stored.skills),
    )


@router.get("", summary="The stored candidate profile")
async def get_profile(
    session: DbSession,
    user: CurrentUser,
    include_skills: Annotated[bool, Query(alias="includeSkills")] = True,
) -> ProfileResponse:
    """What is stored, assembled from rows — the same assembly every other feature reads."""
    profile = await ProfileService(session).load(user)
    return ProfileResponse.from_schema(
        profile, declared_skills=profile.skills if include_skills else []
    )
