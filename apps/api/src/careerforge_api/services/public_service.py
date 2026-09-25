"""The public candidate page: publishing, privacy and the guarantee that nothing leaks.

The interesting decisions are all about **what a stranger may see**, and each is enforced here
rather than left to the page that renders it:

* **A public view costs no model call.** The narrative (summary, highlights, interview topics)
  is generated once at publish time and stored; reads rebuild nothing and call nobody. A page a
  recruiter can refresh is not a page that should bill the candidate per view.
* **Privacy is applied on read, not only on write.** The stored payload is re-filtered through
  the candidate's *current* switches every time it is served, so unchecking a section hides it
  immediately instead of at the next republish — the window between "I turned that off" and "it
  is actually off" is exactly where a leak lives.
* **Every served payload is scanned for PII.** The agent redacts as it builds, and the service
  re-scans before responding. Two layers because the failure is asymmetric: a false negative
  publishes somebody's phone number, and the cost of the second check is microseconds.
* **A local-scope account cannot publish at all.** ``storage_scope='local'`` means "my data does
  not leave this machine", and a public URL contradicts it; the refusal says so.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from careerforge_ai.agents.recruiter import publish_profile
from careerforge_ai.orchestrator import WorkflowExecutor
from careerforge_ai.parsing.pii import redact_pii, scan_pii
from careerforge_ai.schemas.public import (
    PublicEvidenceLink,
    PublicProfileSummary,
    PublicSectionVisibility,
)
from careerforge_api.core.errors import ForbiddenError, NotFoundError, ValidationError
from careerforge_api.db.compat import utcnow
from careerforge_api.models.user import PublicProfile, User
from careerforge_api.services.job_service import JobService
from careerforge_api.services.profile_service import ProfileService

__all__ = ["PublicService", "PublishOutcome", "SECTIONS"]

#: The switches a candidate can flip, and the defaults. Kept beside the schema they mirror so
#: a field added there cannot be silently unmanaged here.
SECTIONS: tuple[str, ...] = (
    "summary",
    "skills",
    "projects",
    "evidence",
    "highlights",
    "interview_topics",
    "contact",
    "resume_file",
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class PublicView:
    """One served public page: the projection, and the count this view brought it to."""

    summary: PublicProfileSummary
    view_count: int


@dataclass(frozen=True, slots=True)
class PublishOutcome:
    """What a publish produced: the stored row, and whether the model degraded."""

    profile: PublicProfile
    degraded: bool
    warnings: list[str]


def slugify(display_name: str, *, suffix: str) -> str:
    """A URL-safe slug from a display name, always ending in an opaque suffix.

    The suffix is not decoration: a public URL that is guessable from somebody's name lets
    anyone enumerate candidates, and the slug is the only thing standing between a published
    profile and a stranger who can spell.
    """
    base = _SLUG_RE.sub("-", display_name.strip().lower()).strip("-")
    base = base[:40] or "candidate"
    return f"{base}-{suffix}"


class PublicService:
    """Publishing, un-publishing, and serving the public projection."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── reads a stranger can make ────────────────────────────────────────────

    async def public_profile(self, slug: str) -> PublicView | None:
        """The published summary, re-filtered by the candidate's current switches.

        ``None`` for an unknown slug **and** for an unpublished one — the caller turns both into
        404. Distinguishing them would tell a stranger which slugs exist.
        """
        row = await self._published_row(slug)
        if row is None:
            return None
        summary = self._load_summary(row)
        filtered = self._apply_visibility(summary, row)
        await self._count_view(row)
        # The count is returned rather than read back off the payload: the projection is the
        # agent's output and has no business carrying a view counter, and a page whose footer
        # always reads "0 views" is a page that looks broken.
        return PublicView(summary=self._scrub(filtered), view_count=row.view_count)

    async def skill_evidence(self, slug: str, skill_id: str) -> list[PublicEvidenceLink] | None:
        """The evidence behind one skill — the Recruiter View's click-to-expand.

        ``None`` when the page is not published; an empty list when the skill exists but its
        evidence is private. The second case is deliberately not a 404: the skill is public, and
        saying "there is nothing to show" is different from saying "no such skill".
        """
        row = await self._published_row(slug)
        if row is None:
            return None
        summary = self._apply_visibility(self._load_summary(row), row)
        for skill in summary.skills:
            if skill.canonical_id == skill_id:
                return [self._scrub_links([link])[0] for link in skill.evidence]
        return []

    async def settings(self, user: User) -> dict[str, Any]:
        """The candidate's own view of their publish state."""
        row = await self._row(user)
        visibility = self._visibility_of(row)
        return {
            "slug": row.slug if row else None,
            "isPublished": bool(row and row.is_published),
            "publishedAt": row.published_at if row else None,
            "viewCount": row.view_count if row else 0,
            "sections": visibility.model_dump(),
            "hiddenSkills": self._hidden_skills(user),
            "canPublish": self._can_publish(user),
            "url": self.public_url(row.slug) if row and row.slug else None,
            "piiFindings": self._stored_findings(row),
        }

    # ── writes only the owner can make ───────────────────────────────────────

    async def publish(
        self,
        user: User,
        *,
        executor: WorkflowExecutor,
        published: bool = True,
        sections: dict[str, Any] | None = None,
        slug: str | None = None,
    ) -> PublishOutcome:
        """Publish (or un-publish) the public page, regenerating the narrative when publishing."""
        row = await self._row(user)
        if not published:
            if row is None:
                row = PublicProfile(user_id=user.id, slug=None)
                self._session.add(row)
            row.is_published = False
            await self._session.flush()
            return PublishOutcome(profile=row, degraded=False, warnings=["已取消发布"])

        if not self._can_publish(user):
            raise ForbiddenError(
                "本地模式（storage_scope=local）的账号不能发布公开页：公开 URL 与「数据不出本机」相互矛盾。"
                "如需发布，请先在设置中切换为云端模式。"
            )

        visibility = self._visibility_of(row)
        if sections:
            visibility = self._visibility_from(sections, current=visibility)

        profile = await ProfileService(self._session).load(user)
        graph, warnings = await JobService(self._session).build_graph_result(
            user_id=user.id, profile=profile
        )
        resolved_slug = (
            slug
            or (row.slug if row else None)
            or slugify(user.display_name, suffix=user.id.hex[:8])
        )

        summary, outcome = await publish_profile(
            executor,
            profile=profile,
            graph=graph,
            visibility=visibility,
            slug=resolved_slug,
        )
        warnings.extend(outcome.warnings)
        if summary is None:  # pragma: no cover - the workflow always assembles
            raise ValidationError("公开页生成失败：RecruiterAgent 没有返回结果")

        # The heading of the public page is the **person**, and the line under it is their
        # professional title. The agent derives `display_name` from `profile.headline` (with
        # `ProfileService.load` falling back to `user.display_name` when no headline is stored), so
        # a candidate who *has* a headline was published with the same sentence as their name and
        # their title: the page printed it twice, which reads as duplicated data rather than as a
        # design. The account's own display name is the honest source for the heading, and it is
        # never the legal name (`docs/API.md` §2.13) — the candidate chose it.
        if user.display_name:
            summary = summary.model_copy(update={"display_name": user.display_name})

        payload = summary.model_dump(mode="json")
        findings = scan_pii(_flatten(payload))
        payload = self._apply_hidden_skills(payload, user)

        if row is None:
            row = PublicProfile(user_id=user.id, slug=resolved_slug)
            self._session.add(row)
        row.slug = resolved_slug
        row.is_published = True
        row.sections = visibility.model_dump()
        row.summary = str(payload.get("summary") or "")
        row.highlights = list(payload.get("highlights") or [])
        row.interview_topics = list(payload.get("interview_topics") or [])
        row.published_at = utcnow()
        # The full payload is kept so a view costs no model call; anything that must stay
        # private is filtered on the way out, not on the way in.
        row.public_payload = payload
        row.pii_findings = [finding.as_dict() for finding in findings]
        await self._session.flush()
        return PublishOutcome(profile=row, degraded=outcome.degraded, warnings=warnings)

    async def update_settings(
        self,
        user: User,
        *,
        sections: dict[str, Any] | None = None,
        hidden_skills: list[str] | None = None,
    ) -> dict[str, Any]:
        """Section switches and the per-skill hide list — applied on the next read."""
        row = await self._row(user)
        if sections:
            visibility = self._visibility_from(sections, current=self._visibility_of(row))
            if row is None:
                raise NotFoundError("尚未发布公开页，无法设置可见性")
            row.sections = visibility.model_dump()
        if hidden_skills is not None:
            settings = dict(user.privacy_settings or {})
            settings["hidden_skills"] = sorted(
                {skill.strip() for skill in hidden_skills if skill.strip()}
            )
            user.privacy_settings = settings
        await self._session.flush()
        return await self.settings(user)

    # ── internals ────────────────────────────────────────────────────────────

    async def _row(self, user: User) -> PublicProfile | None:
        return await self._session.scalar(
            select(PublicProfile)
            .where(PublicProfile.user_id == user.id)
            .options(selectinload(PublicProfile.user))
        )

    async def _published_row(self, slug: str) -> PublicProfile | None:
        """The published row, with its owner loaded.

        ``selectinload`` rather than the default lazy load: a public read touches ``row.user``
        for the hide list, and a lazy load inside an async session raises ``MissingGreenlet``
        — a 500 on the one endpoint strangers can reach.
        """
        return await self._session.scalar(
            select(PublicProfile)
            .where(PublicProfile.slug == slug, PublicProfile.is_published.is_(True))
            .options(selectinload(PublicProfile.user))
        )

    async def _count_view(self, row: PublicProfile) -> None:
        """Count the view. Best-effort by design: a read must not fail because of analytics."""
        row.view_count = (row.view_count or 0) + 1
        await self._session.flush()

    def _load_summary(self, row: PublicProfile) -> PublicProfileSummary:
        payload = row.public_payload or {}
        if payload:
            return PublicProfileSummary.model_validate(payload)
        # No stored payload (published by an older build): fall back to what is in the columns
        # rather than serving an empty page that looks like a privacy decision.
        return PublicProfileSummary(
            slug=row.slug or "",
            display_name=row.user.display_name if row.user else "",
            summary=row.summary or "",
            highlights=list(row.highlights or []),
            interview_topics=list(row.interview_topics or []),
            visibility=self._visibility_of(row),
        )

    def _apply_visibility(
        self, summary: PublicProfileSummary, row: PublicProfile
    ) -> PublicProfileSummary:
        """Re-apply the *current* switches to the stored payload, and the hide list.

        This is the function that makes "I turned it off" true immediately. It runs on every
        read, so a switch flipped a second ago is already in force.
        """
        visibility = self._visibility_of(row)
        hidden = set(self._hidden_skills(row.user) if row.user else [])
        return summary.model_copy(
            update={
                "visibility": visibility,
                "summary": summary.summary if visibility.summary else "",
                "skills": [
                    skill
                    for skill in (summary.skills if visibility.skills else [])
                    if skill.canonical_id not in hidden
                ],
                "projects": summary.projects if visibility.projects else [],
                "highlights": summary.highlights if visibility.highlights else [],
                "interview_topics": summary.interview_topics if visibility.interview_topics else [],
                "contact": summary.contact if visibility.contact else {},
                "github_url": summary.github_url if visibility.contact else None,
                "website_url": summary.website_url if visibility.contact else None,
            }
        )

    @staticmethod
    def _visibility_of(row: PublicProfile | None) -> PublicSectionVisibility:
        if row is None or not row.sections:
            return PublicSectionVisibility()
        known = {key: value for key, value in row.sections.items() if key in SECTIONS}
        return PublicSectionVisibility.model_validate(known)

    @staticmethod
    def _visibility_from(
        sections: dict[str, Any], *, current: PublicSectionVisibility
    ) -> PublicSectionVisibility:
        merged = current.model_dump()
        for key, value in sections.items():
            if key not in SECTIONS:
                raise ValidationError(
                    f"unknown section '{key}'",
                    details=[
                        {
                            "field": "sections",
                            "issue": "not_allowed",
                            "message": f"allowed: {', '.join(SECTIONS)}",
                        }
                    ],
                )
            merged[key] = bool(value)
        return PublicSectionVisibility.model_validate(merged)

    @staticmethod
    def _hidden_skills(user: User | None) -> list[str]:
        if user is None:
            return []
        settings = user.privacy_settings or {}
        value = settings.get("hidden_skills")
        return [str(item) for item in value] if isinstance(value, list) else []

    @staticmethod
    def _stored_findings(row: PublicProfile | None) -> list[dict[str, Any]]:
        if row is None:
            return []
        findings = row.pii_findings or []
        return [dict(item) for item in findings if isinstance(item, dict)]

    @staticmethod
    def _can_publish(user: User) -> bool:
        """Local-scope accounts are not publishable: the public URL contradicts the promise."""
        return user.storage_scope != "local"

    @staticmethod
    def _apply_hidden_skills(payload: dict[str, Any], user: User) -> dict[str, Any]:
        hidden = set(PublicService._hidden_skills(user))
        if not hidden:
            return payload
        skills = [
            skill
            for skill in payload.get("skills") or []
            if skill.get("canonical_id") not in hidden
        ]
        return {**payload, "skills": skills}

    @staticmethod
    def _scrub(summary: PublicProfileSummary) -> PublicProfileSummary:
        """Second PII pass, on the way out.

        The agent redacts while building; this runs on the payload that is about to be served,
        which is the only place that can be certain. A false negative here publishes somebody's
        phone number, and a false positive costs a masked string — the asymmetry decides it.
        """
        text, findings = redact_pii(_flatten(summary.model_dump(mode="json")))
        if not findings:
            return summary
        try:
            scrubbed = json.loads(text)
        except json.JSONDecodeError:  # pragma: no cover - the text is JSON by construction
            return summary
        return PublicProfileSummary.model_validate(scrubbed)

    @staticmethod
    def _scrub_links(links: list[PublicEvidenceLink]) -> list[PublicEvidenceLink]:
        out: list[PublicEvidenceLink] = []
        for link in links:
            title, title_findings = redact_pii(link.title)
            display, display_findings = redact_pii(link.locator_display)
            if title_findings or display_findings:
                link = link.model_copy(update={"title": title, "locator_display": display})
            out.append(link)
        return out

    @staticmethod
    def public_url(slug: str) -> str:
        """The shareable path. Absolute URLs are the client's business (it knows its own host)."""
        return f"/candidate/{slug}"


def _flatten(payload: Any) -> str:
    """A single string for the PII scanner: it reads text, not data structures."""
    return json.dumps(payload, ensure_ascii=False)
