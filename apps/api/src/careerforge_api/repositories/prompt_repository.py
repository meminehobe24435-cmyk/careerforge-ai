"""``prompt_versions`` access plus the startup synchronisation of ``prompts/*.md``.

The registry on disk is the source of truth (``docs/ARCHITECTURE.md`` §9); this
repository mirrors it so a historical ``agent_runs.prompt_version`` can be resolved
to the exact text that produced it, even after the file changed.

Synchronisation follows ``docs/DATABASE.md`` §2.11 — *"内容哈希变化即新增版本"* — so
editing a prompt without bumping its declared ``version:`` creates a new row at the
next free version instead of rewriting a revision that already-traced runs point at.
Exactly one version per prompt name is ``is_active``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.prompting.registry import PromptRegistry, PromptTemplate
from careerforge_api.models.prompt import PromptVersion

__all__ = ["PromptRepository", "PromptSyncReport"]


@dataclass(slots=True)
class PromptSyncReport:
    """What :meth:`PromptRepository.sync_registry` changed."""

    inserted: int = 0
    bumped: int = 0
    unchanged: int = 0
    deactivated: int = 0
    names: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.inserted + self.bumped + self.unchanged

    def as_dict(self) -> dict[str, object]:
        return {
            "inserted": self.inserted,
            "bumped": self.bumped,
            "unchanged": self.unchanged,
            "deactivated": self.deactivated,
            "total": self.total,
        }


class PromptRepository:
    """Persistence for the prompt registry mirror."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, name: str, version: int) -> PromptVersion | None:
        statement = select(PromptVersion).where(
            PromptVersion.name == name, PromptVersion.version == version
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def latest(self, name: str) -> PromptVersion | None:
        statement = (
            select(PromptVersion)
            .where(PromptVersion.name == name)
            .order_by(PromptVersion.version.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def active(self) -> list[PromptVersion]:
        statement = (
            select(PromptVersion)
            .where(PromptVersion.is_active.is_(True))
            .order_by(PromptVersion.name)
        )
        return list((await self._session.execute(statement)).scalars())

    async def list_all(self) -> list[PromptVersion]:
        statement = select(PromptVersion).order_by(PromptVersion.name, PromptVersion.version)
        return list((await self._session.execute(statement)).scalars())

    async def count(self) -> int:
        return int(
            (await self._session.execute(select(func.count(PromptVersion.id)))).scalar() or 0
        )

    async def _max_version(self, name: str) -> int:
        statement = select(func.max(PromptVersion.version)).where(PromptVersion.name == name)
        return int((await self._session.execute(statement)).scalar() or 0)

    def _add(self, template: PromptTemplate, version: int) -> PromptVersion:
        row = PromptVersion(
            name=template.name,
            version=version,
            content=template.body,
            content_sha256=template.content_sha256,
            path=template.path or None,
            variables=list(template.declared_variables()),
            notes=template.description or None,
            is_active=True,
        )
        self._session.add(row)
        return row

    async def sync_registry(self, registry: PromptRegistry) -> PromptSyncReport:
        """Idempotently mirror ``registry`` into the table. Safe to run on every boot.

        Three cases per prompt, in order:

        1. the declared ``(name, version)`` is stored with identical content → nothing to
           do (this is the normal path on every subsequent boot);
        2. the *latest* revision already holds this content → nothing to do. Without this
           check, a file whose content changed without its ``version:`` being bumped would
           insert a fresh revision on **every** boot, because the declared version keeps
           pointing at the original row (``docs/DATABASE.md`` §2.11 wants one new revision
           per content change, not one per restart);
        3. otherwise a new revision is recorded — at the author's declared number when it
           is genuinely new and higher, otherwise at ``max(version) + 1``.
        """
        report = PromptSyncReport()
        if not registry.templates:
            return report

        for (name, declared_version), template in sorted(registry.templates.items()):
            if name not in report.names:
                report.names.append(name)

            existing = await self.get(name, declared_version)
            if existing is not None and existing.content_sha256 == template.content_sha256:
                # Keep the descriptive fields fresh; the content is identical.
                existing.path = template.path or existing.path
                existing.variables = list(template.declared_variables())
                report.unchanged += 1
                continue

            latest = await self.latest(name)
            if latest is not None and latest.content_sha256 == template.content_sha256:
                report.unchanged += 1
                continue

            if latest is None:
                self._add(template, declared_version)
                report.inserted += 1
                continue
            if existing is None and declared_version > latest.version:
                # The author bumped the version in front matter: honour it.
                self._add(template, declared_version)
                report.inserted += 1
                continue

            self._add(template, latest.version + 1)
            report.bumped += 1

        await self._session.flush()
        report.deactivated = await self._refresh_active_flags(report.names)
        return report

    async def _refresh_active_flags(self, names: list[str]) -> int:
        """Exactly the highest version of each prompt stays active."""
        changed = 0
        for name in names:
            highest = await self._max_version(name)
            result = await self._session.execute(
                update(PromptVersion)
                .where(
                    PromptVersion.name == name,
                    PromptVersion.is_active.is_(True),
                    PromptVersion.version != highest,
                )
                .values(is_active=False)
            )
            changed += int(result.rowcount or 0)  # type: ignore[attr-defined]
            result = await self._session.execute(
                update(PromptVersion)
                .where(PromptVersion.name == name, PromptVersion.version == highest)
                .values(is_active=True)
            )
            changed += int(result.rowcount or 0)  # type: ignore[attr-defined]
        return changed
