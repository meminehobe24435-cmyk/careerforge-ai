"""CareerForge AI — evidence-driven career operating system core.

This package contains the domain intelligence of CareerForge AI:

* :mod:`careerforge_ai.orchestrator` — explicit, observable agent workflows
* :mod:`careerforge_ai.agents` — the nine domain agents
* :mod:`careerforge_ai.providers` — pluggable LLM providers (incl. a deterministic
  heuristic provider so the product works with zero API keys)
* :mod:`careerforge_ai.rag` — hybrid retrieval (dense + lexical) with RRF fusion
* :mod:`careerforge_ai.graph` — evidence graph construction and traversal
* :mod:`careerforge_ai.scoring` — **deterministic** scoring engines
* :mod:`careerforge_ai.prompting` — versioned prompt registry
* :mod:`careerforge_ai.observability` — token, latency and cost accounting

Architectural rule (ADR-022): this package must never import a web framework or
an ORM. It receives plain data objects and talks to the outside world through
ports, which keeps it independently testable and evaluable.
"""

from __future__ import annotations

__all__ = ["ALGORITHM_VERSIONS", "__version__"]

__version__ = "0.1.0"

#: Versions of the deterministic algorithms. Persisted alongside results so a
#: historical score can always be explained by the algorithm that produced it.
ALGORITHM_VERSIONS: dict[str, str] = {
    "evidence_confidence": "confidence@1.0.0",
    "job_match": "match@1.0.0",
    "profile_strength": "strength@1.0.0",
    "gap_priority": "gap@1.0.0",
    "retrieval": "retrieval@1.0.0",
}
