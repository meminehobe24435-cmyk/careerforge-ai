"""Candidate profile persistence: extract once, then read real rows everywhere.

This service closes a gap that three other features were quietly paying for. Before it
existed, every consumer rebuilt a profile with no experiences and no projects:

* the graph drew placeholder nodes for entities it could not resolve;
* the match engine scored the experience and project dimensions at **0.0** — the honest
  reading of "no data", but useless to a candidate who has both;
* Profile Strength's completeness dimension was blind.

The extraction itself is the AI core's job (``ProfileAgent``); this layer owns three things
the core cannot do: it decides what identifies an entity across re-imports, it distinguishes
a model extraction from a human correction, and it keeps ``profile_skills`` in step with the
skill dictionary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.agents.profile import import_profile
from careerforge_ai.orchestrator import WorkflowExecutor
from careerforge_ai.schemas.profile import (
    Achievement,
    CandidateProfile,
    Education,
    Experience,
    ProfileImportResult,
    ProfileSkill,
    Project,
)
from careerforge_api.models.document import Document
from careerforge_api.models.evidence import EvidenceLinkRow
from careerforge_api.models.profile_entity import (
    Achievement as AchievementRow,
    Education as EducationRow,
    Experience as ExperienceRow,
    ProfileSkillRow,
    Project as ProjectRow,
)
from careerforge_api.models.skill import Skill
from careerforge_api.models.user import Profile, User
from careerforge_api.services.profile_mapping import (
    ACHIEVEMENT_KINDS,
    EXPERIENCE_KINDS,
    achievement_from_row,
    education_from_row,
    experience_from_row,
    node_id_for_row,
    project_from_row,
    skill_from_row,
)

__all__ = ["ProfileImportOutcome", "ProfileService", "dedupe_key"]


@dataclass(slots=True)
class ProfileImportOutcome:
    """What one import stored."""

    profile: CandidateProfile
    counts: dict[str, int] = field(default_factory=dict)
    skills_normalised: dict[str, str] = field(default_factory=dict)
    unmapped_skills: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False
    document_id: UUID | None = None


def dedupe_key(*parts: str | None) -> str:
    """A stable identity for an entity across re-imports.

    Built from what a human would call the same thing: a school and a degree, a company and a
    title, a project name. Deliberately *not* the description — a résumé re-exported with one
    sentence reworded is the same job, and keying on prose would duplicate the profile on
    every edit.
    """
    cleaned = [part.strip().lower() for part in parts if part and part.strip()]
    return "|".join(cleaned) or "unknown"


class ProfileService:
    """Extraction and storage for one user's career entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── import ───────────────────────────────────────────────────────────────

    async def import_text(
        self,
        *,
        user: User,
        executor: WorkflowExecutor,
        text: str,
        source_kind: str = "resume",
        document: Document | None = None,
    ) -> ProfileImportOutcome:
        """Extract a profile from text and persist it.

        Raises:
            ValueError: the text is empty, or the extractor returned nothing usable.
        """
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("the document has no text to extract a profile from")

        result, outcome = await import_profile(
            executor,
            cleaned,
            source_kind=source_kind,
            slug=(document.filename if document else None),
        )
        if result is None:
            raise ValueError("the profile could not be extracted from this text")

        counts = await self._persist(user, result, document=document)
        return ProfileImportOutcome(
            profile=result.profile,
            counts=counts,
            skills_normalised=dict(result.skills_normalised),
            unmapped_skills=list(result.unmapped_skills),
            warnings=[*result.warnings, *outcome.warnings],
            degraded=result.degraded,
            document_id=document.id if document else None,
        )

    async def _persist(
        self, user: User, result: ProfileImportResult, *, document: Document | None
    ) -> dict[str, int]:
        profile = result.profile
        document_id = document.id if document else None

        await self._upsert_profile_row(user, profile)
        counts = {
            "educations": await self._replace_educations(user, profile.educations, document_id),
            "experiences": await self._replace_experiences(user, profile.experiences, document_id),
            "projects": await self._replace_projects(user, profile.projects, document_id),
            "achievements": await self._replace_achievements(user, profile.achievements),
            "skills": await self._replace_skills(user, profile.skills),
        }
        await self._session.flush()
        return counts

    async def _upsert_profile_row(self, user: User, profile: CandidateProfile) -> None:
        row = await self._session.scalar(select(Profile).where(Profile.user_id == user.id))
        if row is None:
            row = Profile(user_id=user.id)
            self._session.add(row)
        # Only overwrite with something: an extraction that returned an empty headline must
        # not erase a headline the candidate typed.
        if profile.headline:
            row.headline = profile.headline
        if profile.summary:
            row.summary = profile.summary
        if profile.location:
            row.location = profile.location
        if profile.target_roles:
            row.target_roles = list(profile.target_roles)
        if profile.years_experience is not None:
            row.years_experience = profile.years_experience
        if profile.github_username:
            row.github_username = profile.github_username
        if profile.website:
            row.website = profile.website
        if not row.slug:
            row.slug = await self._unique_slug(user, profile)
        await self._session.flush()

    async def _unique_slug(self, user: User, profile: CandidateProfile) -> str:
        """A public-page key that is stable and free.

        Derived from the display name rather than the email: the slug appears in a URL a
        candidate will share, and an address in a URL is a privacy leak with extra steps.
        """
        base = (profile.slug or user.display_name or "candidate").strip().lower()
        slug = "".join(char if char.isalnum() else "-" for char in base).strip("-") or "candidate"
        candidate = f"{slug[:40]}-{user.id.hex[:6]}"
        taken = await self._session.scalar(select(Profile.slug).where(Profile.slug == candidate))
        return candidate if taken is None else f"{slug[:36]}-{user.id.hex[:10]}"

    async def _upsert_entities(self, model: Any, user: User, rows: list[dict[str, Any]]) -> int:
        """Upsert by ``dedupe_key``; delete what the source no longer contains.

        Row identity is preserved because the graph stores *edges* against these ids: replacing
        a project whose name did not change must not orphan the ``candidate → project`` and
        ``project → skill`` edges pointing at it. An entity the source really dropped is deleted,
        with its edges, which is the honest outcome.

        Returns how many entities the source contained.
        """
        existing = {row.dedupe_key: row for row in await self._entities(model, user)}
        seen: set[str] = set()
        for payload in rows:
            key = payload["dedupe_key"]
            seen.add(key)
            current = existing.get(key)
            if current is None:
                self._session.add(model(user_id=user.id, **payload))
                continue
            # ``column``, not ``field``: that name is the dataclasses helper imported at the top
            # of this module, and shadowing it would break that import for the rest of the file.
            for column, value in payload.items():
                setattr(current, column, value)
        for key, row in existing.items():
            if key not in seen:
                # Take the node's edges with it. The graph stores edges against derived node
                # ids, and an edge whose endpoint no longer exists renders as a placeholder —
                # a bubble labelled ``project:de6dd367`` that nobody can open. Deleting the
                # entity without its edges is what produced exactly that in a live run.
                identifier = node_id_for_row(model, row)
                if identifier is not None:
                    await self._session.execute(
                        delete(EvidenceLinkRow).where(
                            EvidenceLinkRow.user_id == user.id,
                            (EvidenceLinkRow.from_id == identifier)
                            | (EvidenceLinkRow.to_id == identifier),
                        )
                    )
                await self._session.delete(row)
        await self._session.flush()
        return len(rows)

    async def _replace_educations(
        self, user: User, items: list[Education], document_id: UUID | None
    ) -> int:
        return await self._upsert_entities(
            EducationRow,
            user,
            [
                {
                    "school": item.school,
                    "degree": item.degree,
                    "major": item.major,
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                    "gpa": item.gpa,
                    "highlights": list(item.highlights),
                    "evidence_strength": item.evidence_strength.numeric,
                    "origin": item.origin.value,
                    "source_document_id": document_id,
                    "dedupe_key": dedupe_key(item.school, item.degree, item.major),
                }
                for item in items
            ],
        )

    async def _replace_experiences(
        self, user: User, items: list[Experience], document_id: UUID | None
    ) -> int:
        return await self._upsert_entities(
            ExperienceRow,
            user,
            [
                {
                    "kind": item.kind if item.kind in EXPERIENCE_KINDS else "fulltime",
                    "company": item.company,
                    "title": item.title,
                    "location": item.location,
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                    "is_current": item.is_current,
                    "description": item.description,
                    "highlights": list(item.highlights),
                    "evidence_strength": item.evidence_strength.numeric,
                    "origin": item.origin.value,
                    "source_document_id": document_id,
                    "dedupe_key": dedupe_key(item.company, item.title),
                }
                for item in items
            ],
        )

    async def _replace_projects(
        self, user: User, items: list[Project], document_id: UUID | None
    ) -> int:
        return await self._upsert_entities(
            ProjectRow,
            user,
            [
                {
                    "name": item.name,
                    "role": item.role,
                    "summary": item.summary,
                    "description": item.description,
                    "tech_stack": list(item.tech_stack),
                    "start_date": item.start_date,
                    "end_date": item.end_date,
                    "repository_id": item.repository_id,
                    "links": dict(item.links),
                    "architecture_mermaid": item.architecture_mermaid,
                    "key_challenges": list(item.key_challenges),
                    "technical_decisions": list(item.technical_decisions),
                    "tradeoffs": list(item.tradeoffs),
                    "debugging_stories": list(item.debugging_stories),
                    "evidence_strength": item.evidence_strength.numeric,
                    "origin": item.origin.value,
                    "source_document_id": document_id,
                    "dedupe_key": dedupe_key(item.name),
                }
                for item in items
            ],
        )

    async def _replace_achievements(self, user: User, items: list[Achievement]) -> int:
        return await self._upsert_entities(
            AchievementRow,
            user,
            [
                {
                    "kind": item.kind if item.kind in ACHIEVEMENT_KINDS else "other",
                    "title": item.title,
                    "issuer": item.issuer,
                    "awarded_on": item.awarded_on,
                    "level": item.level,
                    "description": item.description,
                    "evidence_strength": item.evidence_strength.numeric,
                    "origin": item.origin.value,
                    "dedupe_key": dedupe_key(item.title, item.issuer),
                }
                for item in items
            ],
        )

    async def _replace_skills(self, user: User, items: list[ProfileSkill]) -> int:
        """Replace the declared skills, resolving each against the dictionary.

        A skill the taxonomy does not know is skipped rather than stored as free text: the
        table's whole purpose is to join the graph's canonical ids, and a row that cannot be
        joined would look like a declaration to some readers and nothing to others. The
        importer reports those names back in ``unmapped_skills`` instead.
        """
        await self._session.execute(
            delete(ProfileSkillRow).where(ProfileSkillRow.user_id == user.id)
        )
        if not items:
            return 0

        canonical_ids = [item.skill.canonical_id for item in items if item.skill.canonical_id]
        dictionary = {
            row.canonical_id: row
            for row in (
                await self._session.scalars(
                    select(Skill).where(Skill.canonical_id.in_(canonical_ids))
                )
            ).all()
        }

        written = 0
        for item in items:
            canonical = item.skill.canonical_id
            skill = dictionary.get(canonical)
            if skill is None:
                continue
            self._session.add(
                ProfileSkillRow(
                    user_id=user.id,
                    skill_id=skill.id,
                    level=item.level.value,
                    evidence_score=float(item.evidence_score),
                    evidence_count=item.evidence_count,
                    is_target=item.is_target,
                    origin=item.origin.value,
                    canonical_id=canonical,
                )
            )
            written += 1
        return written

    # ── reads ────────────────────────────────────────────────────────────────

    async def load(self, user: User) -> CandidateProfile:
        """Rebuild the candidate profile from stored rows.

        This is what every downstream consumer reads — the graph builder, the match engine and
        the dashboard — so they all see the same profile, assembled from the same rows.
        """
        row = await self._session.scalar(select(Profile).where(Profile.user_id == user.id))
        slug = row.slug if row is not None and row.slug else f"user-{user.id.hex[:8]}"

        return CandidateProfile(
            user_id=user.id,
            slug=slug,
            headline=(row.headline if row and row.headline else user.display_name),
            summary=row.summary if row and row.summary else "",
            location=row.location if row else None,
            github_username=row.github_username if row else None,
            website=row.website if row else None,
            target_roles=list(row.target_roles) if row else [],
            years_experience=(
                float(row.years_experience)
                if row is not None and row.years_experience is not None
                else None
            ),
            educations=[
                education_from_row(entity) for entity in await self._entities(EducationRow, user)
            ],
            experiences=[
                experience_from_row(entity) for entity in await self._entities(ExperienceRow, user)
            ],
            projects=[
                project_from_row(entity) for entity in await self._entities(ProjectRow, user)
            ],
            achievements=[
                achievement_from_row(entity)
                for entity in await self._entities(AchievementRow, user)
            ],
            skills=await self._declared_skills(user),
        )

    async def graph_nodes(self, user: User) -> dict[UUID, Any]:
        """Graph node ids for this user's entities, keyed the way the builder derives them.

        The graph is stored as evidence plus edges (ADR-005), so entity nodes are *derived*: a
        link ending at a project only renders if the reader can recompute the same id the
        builder used. It can — the builder keys a project by its row id (or its name when it
        has none), an experience by ``company:title``, an education by its school and an
        achievement by its title. Before these tables existed, every such endpoint came back as
        a placeholder labelled ``project:4f3a9b21``.
        """
        from careerforge_ai.graph import node_id
        from careerforge_ai.schemas.common import GraphNodeType
        from careerforge_ai.schemas.evidence import GraphNode

        profile = await self.load(user)
        nodes: dict[UUID, Any] = {}

        # ``node_type`` rather than ``kind``: the first parameter's name would collide with the
        # ``kind`` meta key an experience carries, and a positional call would silently win.
        def add(node_type: GraphNodeType, key: str, label: str, **meta: Any) -> None:
            identifier = node_id(node_type, key)
            nodes[identifier] = GraphNode(
                id=identifier, type=node_type, label=label, group=key, meta=dict(meta)
            )

        for project in profile.projects:
            add(
                GraphNodeType.PROJECT,
                str(project.id) if project.id else project.name,
                project.name,
                role=project.role or "",
                tech_stack=list(project.tech_stack),
            )
        for experience in profile.experiences:
            add(
                GraphNodeType.EXPERIENCE,
                f"{experience.company}:{experience.title}",
                f"{experience.company} · {experience.title}",
                kind=experience.kind,
            )
        for education in profile.educations:
            add(GraphNodeType.EDUCATION, education.school, education.school)
        for achievement in profile.achievements:
            add(GraphNodeType.ACHIEVEMENT, achievement.title, achievement.title)
        return nodes

    async def _entities(self, model: Any, user: User) -> list[Any]:
        statement = select(model).where(model.user_id == user.id)
        return list((await self._session.scalars(statement)).all())

    async def _declared_skills(self, user: User) -> list[ProfileSkill]:
        statement = select(ProfileSkillRow).where(ProfileSkillRow.user_id == user.id)
        rows = list((await self._session.scalars(statement)).all())
        if not rows:
            return []
        dictionary = {
            row.canonical_id: row
            for row in (
                await self._session.scalars(
                    select(Skill).where(Skill.canonical_id.in_([r.canonical_id for r in rows]))
                )
            ).all()
        }
        declared: list[ProfileSkill] = [
            skill_from_row(row, dictionary.get(row.canonical_id)) for row in rows
        ]
        return declared
