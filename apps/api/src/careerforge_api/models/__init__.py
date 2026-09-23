"""PHASE 1 ORM models.

Every table here is documented in ``docs/DATABASE.md`` §2; the other 24 tables
arrive with the phases that need them. Importing this package populates
``Base.metadata``, which is what ``create_all`` and the Alembic baseline both read.
"""

from __future__ import annotations

from careerforge_api.db.base import Base
from careerforge_api.models.cache import AI_CACHE_KINDS, AiCache
from careerforge_api.models.job import (
    BACKGROUND_JOB_STATUSES,
    BACKGROUND_JOB_TERMINAL_STATUSES,
    BackgroundJob,
)
from careerforge_api.models.observability import (
    AGENT_RUN_STATUSES,
    AGENT_RUN_TRIGGERS,
    LLM_OPERATIONS,
    LLM_STATUSES,
    AgentRun,
    LlmCall,
)
from careerforge_api.models.prompt import PromptVersion
from careerforge_api.models.skill import SKILL_CATEGORIES, Skill
from careerforge_api.models.user import (
    ROLE_VALUES,
    STORAGE_SCOPE_VALUES,
    Profile,
    PublicProfile,
    User,
)

__all__ = [
    "AGENT_RUN_STATUSES",
    "AGENT_RUN_TRIGGERS",
    "AI_CACHE_KINDS",
    "BACKGROUND_JOB_STATUSES",
    "BACKGROUND_JOB_TERMINAL_STATUSES",
    "LLM_OPERATIONS",
    "LLM_STATUSES",
    "ROLE_VALUES",
    "SKILL_CATEGORIES",
    "STORAGE_SCOPE_VALUES",
    "AgentRun",
    "AiCache",
    "BackgroundJob",
    "Base",
    "LlmCall",
    "Profile",
    "PromptVersion",
    "PublicProfile",
    "Skill",
    "User",
]
