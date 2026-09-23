"""The heuristic provider package.

Split by responsibility rather than kept as one module:

* :mod:`text` — tokenisation, overlap scoring, feature-hash embeddings, sections
* :mod:`registry` — the handler registry
* :mod:`handlers_jd` / :mod:`handlers_claim` / :mod:`handlers_profile` /
  :mod:`handlers_interview` / :mod:`handlers_learning` / :mod:`handlers_github`
  — one module per schema family
* :mod:`synthesis` — the generic valid-but-empty fallback
* :mod:`provider` — the :class:`HeuristicProvider` itself

The handler modules are imported here for their registration side effect: the
decorator is what makes them reachable, so importing this package must import
them.
"""

from __future__ import annotations

# Imported for their registration side effect — do not remove as "unused".
from careerforge_ai.providers.heuristic import (  # noqa: F401
    handlers_claim,
    handlers_github,
    handlers_interview,
    handlers_jd,
    handlers_learning,
    handlers_profile,
)
from careerforge_ai.providers.heuristic.provider import HeuristicProvider
from careerforge_ai.providers.heuristic.registry import HEURISTIC_HANDLERS, handles
from careerforge_ai.providers.heuristic.text import (
    HEURISTIC_EMBEDDING_DIM,
    bullets,
    first_date,
    heuristic_embedding,
    split_sections,
    token_overlap,
    tokens,
)

__all__ = [
    "HEURISTIC_EMBEDDING_DIM",
    "HEURISTIC_HANDLERS",
    "HeuristicProvider",
    "bullets",
    "first_date",
    "handles",
    "heuristic_embedding",
    "split_sections",
    "token_overlap",
    "tokens",
]
