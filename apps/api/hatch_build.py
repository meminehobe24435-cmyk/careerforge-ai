"""Hatchling metadata hook: resolve the sibling AI core as a path dependency.

``docs/ARCHITECTURE.md`` keeps the AI core and the HTTP API in one monorepo, and
the API must always be installed against the *working tree* copy of
``packages/ai`` rather than a published wheel. ``packages/ai`` is at
``../../packages/ai`` relative to this file.

PEP 508 needs an absolute ``file:///`` URL, and pip resolves a relative ``file:``
URL against the current working directory — which differs between the repository
root (``pip install -e ".\apps\api[dev]"``) and this directory
(``cd apps/api; pip install -e ".[dev]"``). Computing the absolute path here, from
``self.root``, makes both invocations behave identically.
"""

from __future__ import annotations

from pathlib import Path

from hatchling.metadata.plugin.interface import MetadataHookInterface

__all__ = ["CustomMetadataHook"]

#: Everything the HTTP layer needs, mirroring the AI core's runtime requirements.
BASE_DEPENDENCIES: tuple[str, ...] = (
    "fastapi>=0.115,<1",
    "uvicorn[standard]>=0.32,<1",
    "pydantic>=2.9,<3",
    "pydantic-settings>=2.6,<3",
    "sqlalchemy[asyncio]>=2.0.36,<2.1",
    "aiosqlite>=0.20",
    "asyncpg>=0.30",
    "alembic>=1.14,<2",
    "pyjwt>=2.9,<3",
    "bcrypt>=4.2",
    "python-multipart>=0.0.12",
    "httpx>=0.27,<1",
    "email-validator>=2.2",
)


def ai_core_path(root: Path) -> Path:
    """Absolute path of the sibling ``packages/ai`` package."""
    return (root / ".." / ".." / "packages" / "ai").resolve()


class CustomMetadataHook(MetadataHookInterface):
    """Injects ``careerforge-ai`` as a direct reference to the monorepo copy."""

    def update(self, metadata: dict) -> None:
        ai_core = ai_core_path(Path(self.root))
        reference = f"careerforge-ai @ {ai_core.as_uri()}"
        metadata["dependencies"] = [reference, *BASE_DEPENDENCIES]
