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
``ProfileAgent``                     ✅ WF-01 · resume/document → structured profile
``EvidenceAgent``                    ✅ WF-02 · material → evidence nodes and graph
``ResumeAgent``                      ✅ WF-05 · bullet rewrite under the evidence gate
``InterviewAgent``                   ⬜ WF-07
``CoachAgent``                       ⬜ WF-08
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
from careerforge_ai.agents.coach import (
    COACH_AGENT,
    CoachAgent,
    build_learning_plan,
    build_workflow as build_coach_workflow,
)
from careerforge_ai.agents.evidence import (
    EVIDENCE_AGENT,
    DocumentChunkInput,
    EvidenceAgent,
    build_graph,
    build_workflow as build_evidence_workflow,
)
from careerforge_ai.agents.interview import (
    INTERVIEW_AGENT,
    InterviewAgent,
    finish_interview,
    start_interview,
    submit_answer,
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
from careerforge_ai.agents.profile import (
    PROFILE_AGENT,
    ProfileAgent,
    build_workflow as build_profile_workflow,
    import_profile,
)
from careerforge_ai.agents.recruiter import (
    RECRUITER_AGENT,
    RecruiterAgent,
    publish_profile,
)
from careerforge_ai.agents.resume import (
    RESUME_AGENT,
    ResumeAgent,
    build_workflow as build_resume_workflow,
    optimize_resume,
)
from careerforge_ai.agents.validator import (
    VALIDATOR_AGENT,
    ValidatorAgent,
    build_workflow as build_validator_workflow,
    validate_claim_text,
)

__all__ = [
    "COACH_AGENT",
    "RECRUITER_AGENT",
    "INTERVIEW_AGENT",
    "EVIDENCE_AGENT",
    "RESUME_AGENT",
    "JOB_AGENT",
    "MATCH_AGENT",
    "PROFILE_AGENT",
    "PROMPT_CHAR_BUDGET",
    "VALIDATOR_AGENT",
    "Agent",
    "AgentOutcome",
    "CoachAgent",
    "DocumentChunkInput",
    "EvidenceAgent",
    "InterviewAgent",
    "JobAgent",
    "MatchAgent",
    "ProfileAgent",
    "RecruiterAgent",
    "ResumeAgent",
    "ValidatorAgent",
    "build_coach_workflow",
    "build_evidence_workflow",
    "build_graph",
    "build_learning_plan",
    "build_jd_analysis",
    "build_job_workflow",
    "build_profile_workflow",
    "build_resume_workflow",
    "build_match_workflow",
    "build_validator_workflow",
    "merge_workflow_warnings",
    "normalise_whitespace",
    "render_bullets",
    "compute_match",
    "finish_interview",
    "import_profile",
    "optimize_resume",
    "publish_profile",
    "start_interview",
    "submit_answer",
    "strip_markup",
    "truncate_for_prompt",
    "validate_claim_text",
]
