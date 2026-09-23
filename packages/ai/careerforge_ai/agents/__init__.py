"""The nine domain agents.

Each agent is a named workflow plus the prompt context that workflow needs — not a
chat loop. Dependencies arrive through :class:`careerforge_ai.orchestrator.RunContext`,
which is what makes an agent testable with fake ports and its cost attributable
step by step.

Status, so the README and the docs do not overstate what exists:

===================================  ==========================================
Agent                                Status
===================================  ==========================================
``JobAgent``                         ✅ WF-03 · JD → structured, normalised analysis
``ValidatorAgent``                   ✅ WF-06 · claim verification and the gate
``MatchAgent``                       ✅ WF-04 · explainable match scoring
``ProfileAgent``                     ⬜ WF-01 · extraction handler exists in the heuristic provider
``EvidenceAgent``                    ⬜ WF-02 · graph construction exists in ``graph/``
``ResumeAgent``                      ⬜ WF-05
``InterviewAgent``                   ⬜ WF-07
``CoachAgent``                       ⬜ WF-08
``RecruiterAgent``                   ⬜ WF-10
===================================  ==========================================

The remaining agents are thin workflow wrappers around already-tested engines; what
they add is orchestration and tracing, not new logic.
"""

from __future__ import annotations

from careerforge_ai.agents.base import (
    PROMPT_CHAR_BUDGET,
    Agent,
    AgentOutcome,
    merge_workflow_warnings,
    normalise_whitespace,
    render_bullets,
    strip_markup,
    truncate_for_prompt,
)
from careerforge_ai.agents.job import (
    JOB_AGENT,
    JobAgent,
    build_jd_analysis,
    build_workflow as build_job_workflow,
)
from careerforge_ai.agents.match import (
    MATCH_AGENT,
    MatchAgent,
    build_workflow as build_match_workflow,
    compute_match,
)
from careerforge_ai.agents.validator import (
    VALIDATOR_AGENT,
    ValidatorAgent,
    build_workflow as build_validator_workflow,
    validate_claim_text,
)

__all__ = [
    "JOB_AGENT",
    "MATCH_AGENT",
    "PROMPT_CHAR_BUDGET",
    "VALIDATOR_AGENT",
    "Agent",
    "AgentOutcome",
    "JobAgent",
    "MatchAgent",
    "ValidatorAgent",
    "build_jd_analysis",
    "build_job_workflow",
    "build_match_workflow",
    "build_validator_workflow",
    "merge_workflow_warnings",
    "normalise_whitespace",
    "render_bullets",
    "compute_match",
    "strip_markup",
    "truncate_for_prompt",
    "validate_claim_text",
]
