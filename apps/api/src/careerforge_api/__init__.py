"""CareerForge AI HTTP API (PHASE 1).

The package wraps :mod:`careerforge_ai` — which owns every AI decision, prompt and
score — in the HTTP contract from ``docs/API.md``. Nothing in here re-implements
provider selection, prompt loading or scoring: it composes the core's ports.

Import surface::

    from careerforge_api.main import app, create_app
"""

from __future__ import annotations

__all__ = ["__version__"]

#: Kept in sync with ``pyproject.toml`` and surfaced by ``GET /system/info``.
__version__ = "0.1.0"
