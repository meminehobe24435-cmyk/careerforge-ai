"""The nine domain agents.

Each agent owns one workflow and one ``Workflow`` definition:

===================================  ==========================================
Agent                                Responsibility
===================================  ==========================================
``ProfileAgent``                     resume/document → structured profile
``EvidenceAgent``                    material → evidence nodes and graph edges
``JobAgent``                         job description → structured analysis
``MatchAgent``                       deterministic five-dimension match score
``ResumeAgent``                      bullet-level rewrite under evidence constraints
``ValidatorAgent``                   claim verification and the hallucination gate
``InterviewAgent``                   adaptive multi-turn interview simulation
``CoachAgent``                       skill gaps → 30-day plan with mini projects
``RecruiterAgent``                   public, evidence-backed candidate profile
===================================  ==========================================

PHASE 1 establishes the orchestrator and providers these agents are built on;
the agents themselves arrive with their respective phases.
"""

from __future__ import annotations

__all__: list[str] = []
