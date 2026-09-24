"""``/public`` — the recruiter's view, and the candidate's control over it.

Two halves, deliberately separated by authentication even though they share a prefix:

* ``GET /public/candidate/{slug}`` and ``.../evidence/{skillId}`` take **no token**. That is the
  feature: a recruiter opening a shared link should not have to create an account, and a page
  that needs a login is not a shareable page. Everything they can reach is already filtered and
  masked by the service — the endpoints have no owner-only field to leak.
* ``POST /public/publish``, ``GET/PATCH /public/settings`` take a token and can only ever touch
  the caller's own profile.

An unknown slug and an unpublished one both answer 404: distinguishing them would let a stranger
enumerate which candidates exist.
"""

from __future__ import annotations

from fastapi import APIRouter, Path

from careerforge_api.core.errors import NotFoundError
from careerforge_api.deps import CurrentUser, DbSession
from careerforge_api.routers.ai import AIServiceDep
from careerforge_api.schemas.public import (
    PromotePublicProfileRequest,
    PublicEvidenceResponse,
    PublicProfileMeta,
    PublicProfileResponse,
    PublicProjectResponse,
    PublicSettingsResponse,
    PublicSkillResponse,
    UpdatePublicSettingsRequest,
)
from careerforge_api.services.public_service import SECTIONS, PublicService

__all__ = ["router"]

router = APIRouter(prefix="/public", tags=["public"])

#: Slug shape, enforced before a database lookup: a public URL is attacker-supplied input.
_SLUG = Path(..., min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")


def _hidden_sections(sections: dict[str, bool]) -> list[str]:
    return sorted(name for name in SECTIONS if not sections.get(name, False))


@router.get(
    "/candidate/{slug}",
    summary="A published candidate page (no login)",
    description="Filtered by the candidate's current privacy switches; 404 when unpublished.",
)
async def get_public_profile(slug: str = _SLUG, *, session: DbSession) -> PublicProfileResponse:
    service = PublicService(session)
    view = await service.public_profile(slug)
    if view is None:
        raise NotFoundError("Candidate page not found")
    summary = view.summary

    settings = summary.visibility.model_dump()
    return PublicProfileResponse(
        display_name=summary.display_name,
        headline=summary.headline,
        location=summary.location,
        summary=summary.summary,
        target_roles=list(summary.target_roles),
        skills=[
            PublicSkillResponse(
                canonical_id=skill.canonical_id,
                display_name=skill.display_name,
                category=skill.category,
                confidence=float(skill.confidence),
                evidence_count=skill.evidence_count,
                corroboration=skill.corroboration,
                # With the evidence section off, the chip survives and the citations do not:
                # "I have used FreeRTOS" and "here is the file that proves it" are separable
                # promises, and the candidate gets to make them separately.
                evidence=[
                    PublicEvidenceResponse(
                        evidence_id=str(link.evidence_id),
                        title=link.title,
                        kind=link.kind,
                        locator=link.locator_display,
                        url=link.url,
                        confidence=float(link.confidence),
                    )
                    for link in skill.evidence
                ]
                if settings.get("evidence")
                else [],
            )
            for skill in summary.skills
        ],
        projects=[
            PublicProjectResponse(
                name=project.name,
                role=project.role,
                summary=project.summary,
                tech_stack=list(project.tech_stack),
                repository_url=project.repository_url,
                highlights=list(project.highlights),
            )
            for project in summary.projects
        ],
        highlights=list(summary.highlights),
        interview_topics=list(summary.interview_topics),
        github_url=summary.github_url,
        website_url=summary.website_url,
        contact=dict(summary.contact),
        meta=PublicProfileMeta(
            slug=summary.slug,
            generated_at=summary.generated_at,
            evidence_coverage=float(summary.evidence_coverage),
            profile_strength=float(summary.profile_strength),
            hidden_sections=_hidden_sections(settings),
            redactions=[dict(item) for item in summary.redactions],
            view_count=view.view_count,
        ),
    )


@router.get(
    "/candidate/{slug}/evidence/{skill_id}",
    summary="The evidence behind one skill (no login)",
    description="Empty when the skill is public but its evidence is private; 404 when unpublished.",
)
async def get_public_skill_evidence(
    slug: str = _SLUG, skill_id: str = Path(..., min_length=1, max_length=80), *, session: DbSession
) -> list[PublicEvidenceResponse]:
    links = await PublicService(session).skill_evidence(slug, skill_id)
    if links is None:
        raise NotFoundError("Candidate page not found")
    return [
        PublicEvidenceResponse(
            evidence_id=str(link.evidence_id),
            title=link.title,
            kind=link.kind,
            locator=link.locator_display,
            url=link.url,
            confidence=float(link.confidence),
        )
        for link in links
    ]


@router.get("/settings", summary="The owner's publish state and privacy switches")
async def get_public_settings(session: DbSession, user: CurrentUser) -> PublicSettingsResponse:
    return PublicSettingsResponse.model_validate(await PublicService(session).settings(user))


@router.post("/publish", summary="Publish or un-publish the public page")
async def publish_public_profile(
    payload: PromotePublicProfileRequest,
    session: DbSession,
    user: CurrentUser,
    agent: AIServiceDep,
) -> PublicSettingsResponse:
    """Publishing regenerates the narrative through ``RecruiterAgent``; un-publishing is instant.

    The response carries ``warnings`` inside the settings payload's PII findings so a degraded
    model (zero-key deployments) is visible rather than silently producing a thinner page.
    """
    service = PublicService(session)
    await service.publish(
        user,
        executor=agent.executor(),
        published=payload.published,
        sections=payload.sections,
        slug=payload.slug,
    )
    return PublicSettingsResponse.model_validate(await service.settings(user))


@router.patch("/settings", summary="Change what the public page shows")
async def update_public_settings(
    payload: UpdatePublicSettingsRequest, session: DbSession, user: CurrentUser
) -> PublicSettingsResponse:
    """Applied on the next read, not at the next republish — the window between "I turned that
    off" and "it is off" is where a leak would live."""
    settings = await PublicService(session).update_settings(
        user, sections=payload.sections, hidden_skills=payload.hidden_skills
    )
    return PublicSettingsResponse.model_validate(settings)
