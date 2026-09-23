"""Repository layer: the only place that builds SQL for tenant-owned data.

Every repository method that touches user data takes an explicit ``user_id`` and
filters on it. Routers and services compose these methods instead of writing their
own queries, which keeps ``docs/ARCHITECTURE.md`` §10's "越权" mitigation auditable
in one directory.
"""

from __future__ import annotations

from careerforge_api.repositories.prompt_repository import PromptRepository, PromptSyncReport
from careerforge_api.repositories.task_repository import TaskRepository
from careerforge_api.repositories.user_repository import UserRepository, normalise_email

__all__ = [
    "PromptRepository",
    "PromptSyncReport",
    "TaskRepository",
    "UserRepository",
    "normalise_email",
]
