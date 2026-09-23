"""HTTP routers, mounted under ``settings.api_prefix`` (``/api/v1``).

PHASE 1 ships ``/auth``, ``/system`` and ``/tasks``. The remaining groups from
``docs/API.md`` §2 (profile, documents, github, evidence, jobs, resume, interview,
applications, analytics, public, search) are added by the phases that own their domain
logic — this package is where they will be registered.
"""

from __future__ import annotations

from careerforge_api.routers import auth, system, tasks

__all__ = ["auth", "system", "tasks"]
