"""Domain services: the layer between routers and the AI core.

Services own transactions and business rules; routers own HTTP. Nothing here
imports FastAPI, which is what keeps the auth/seed/health logic testable without an
ASGI stack and reusable from the worker process.
"""

from __future__ import annotations

from careerforge_api.services.auth_service import AuthService, TokenRevocationRegistry
from careerforge_api.services.seed_service import SeedReport, ensure_demo_user, seed_all
from careerforge_api.services.skill_taxonomy_service import SkillSyncReport, sync_skill_taxonomy
from careerforge_api.services.system_service import collect_health, collect_info

__all__ = [
    "AuthService",
    "SeedReport",
    "SkillSyncReport",
    "TokenRevocationRegistry",
    "collect_health",
    "collect_info",
    "ensure_demo_user",
    "seed_all",
    "sync_skill_taxonomy",
    "AGENT_CATALOGUE",
    "AIService",
    "DatabaseRunTracker",
    "InterviewSessionStore",
]

from careerforge_api.services.ai_service import (
    AGENT_CATALOGUE,
    AIService,
    DatabaseRunTracker,
    InterviewSessionStore,
)
