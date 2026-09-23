"""Cross-cutting API concerns: settings, security, errors, logging, ids.

Everything in this package is framework-facing plumbing shared by the routers,
the middleware and the workers. The sub-modules are imported explicitly
(``careerforge_api.core.security``) so this package stays free of import cycles.
"""

from __future__ import annotations

__all__: list[str] = []
