"""``GET /dashboard`` models (``docs/API.md`` §2.10).

Mirrors the frozen client types in ``packages/shared/src/api/types.ts`` field for field. Two
additions to ``meta`` are deliberate and are the reason this file exists rather than a bare
dict:

* ``unavailable`` names the metrics whose data source does not exist yet. A zero on the
  dashboard is read as "you have none", and for the tracker that would be a claim the system
  cannot make;
* ``definitions`` ships each metric's actual 口径 next to the number, so the label and the
  arithmetic cannot drift apart.

``skillsRadar.market`` is optional here although the client type requires it: the market
average needs a job corpus that is not collected yet, and a fabricated baseline would turn a
comparison into a decoration.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DashboardMeta",
    "DashboardNextAction",
    "DashboardProfileStrength",
    "DashboardRecentJob",
    "DashboardResponse",
    "DashboardStats",
    "SkillRadarPoint",
]


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class DashboardProfileStrength(_CamelModel):
    score: float
    #: ``None`` when nothing was measured a week ago — not the same statement as "no change".
    delta_7d: float | None = Field(default=None, alias="delta7d")


class DashboardStats(_CamelModel):
    """Fractions are 0..1 for the three coverage/match metrics; the rest are counts."""

    evidence_coverage: float = Field(default=0.0, alias="evidenceCoverage")
    skill_coverage: float = Field(default=0.0, alias="skillCoverage")
    resume_match: float = Field(default=0.0, alias="resumeMatch")
    applications: float = 0.0
    interviews: float = 0.0
    offers: float = 0.0


class SkillRadarPoint(_CamelModel):
    skill: str
    user: float
    #: Market baseline. Absent until the job corpus exists; the UI draws one series then.
    market: float | None = None


class DashboardRecentJob(_CamelModel):
    job_id: str = Field(alias="jobId")
    company: str = ""
    role: str = ""
    match_score: float = Field(default=0.0, alias="matchScore")
    status: str = "wishlist"


class DashboardNextAction(_CamelModel):
    type: str
    title: str
    #: ISO-8601 timestamp.
    at: str


class DashboardMeta(_CamelModel):
    cache_hit: bool = Field(default=False, alias="cacheHit")
    took_ms: int = Field(default=0, alias="tookMs")
    #: Metric keys whose data source is not implemented, with the owning phase.
    unavailable: dict[str, str] = Field(default_factory=dict)
    #: Metric key → the definition actually used to compute it.
    definitions: dict[str, str] = Field(default_factory=dict)


class DashboardResponse(_CamelModel):
    """``data`` of ``GET /dashboard``."""

    profile_strength: DashboardProfileStrength = Field(alias="profileStrength")
    stats: DashboardStats
    skills_radar: list[SkillRadarPoint] = Field(default_factory=list, alias="skillsRadar")
    recent_jobs: list[DashboardRecentJob] = Field(default_factory=list, alias="recentJobs")
    next_actions: list[DashboardNextAction] = Field(default_factory=list, alias="nextActions")
    meta: DashboardMeta = Field(default_factory=DashboardMeta)
