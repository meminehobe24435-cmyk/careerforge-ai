"""GitHub intelligence schemas.

The goal is not "list repositories" — it is to convert a code host into
*evidence*: which languages are really used, which engineering domains the work
demonstrates, and which technical elements a project actually contains.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from careerforge_ai.schemas.common import CFBaseModel, Confidence, StrictModel, Unit

__all__ = [
    "CommitSummary",
    "EngineeringSignal",
    "ExtractedProjectIntelligence",
    "GithubProfileAnalysis",
    "LanguageStat",
    "ProjectIntelligence",
    "RepoFileSummary",
    "RepoSummary",
]


class LanguageStat(CFBaseModel):
    name: str
    bytes: int = Field(default=0, ge=0)
    percent: float = Field(default=0.0, ge=0.0, le=100.0)


class RepoFileSummary(CFBaseModel):
    path: str
    language: str | None = None
    size_bytes: int = 0
    sha: str | None = None
    is_significant: bool = False
    significance_reason: str | None = None
    content_excerpt: str = ""


class CommitSummary(CFBaseModel):
    sha: str
    message: str
    author_name: str | None = None
    committed_at: datetime | None = None
    additions: int = 0
    deletions: int = 0
    files_changed: int = 0
    url: str | None = None
    is_significant: bool = False
    significance_reason: str | None = None


class RepoSummary(CFBaseModel):
    full_name: str
    name: str
    owner: str
    description: str | None = None
    html_url: str | None = None
    default_branch: str = "main"
    primary_language: str | None = None
    languages: list[LanguageStat] = Field(default_factory=list)
    stars: int = 0
    forks: int = 0
    topics: list[str] = Field(default_factory=list)
    is_fork: bool = False
    is_archived: bool = False
    size_kb: int = 0
    pushed_at: datetime | None = None
    readme_text: str = ""


class EngineeringSignal(CFBaseModel):
    """A detected engineering direction, e.g. "Embedded Systems"."""

    label: str
    score: Confidence = 0.0
    signals: list[str] = Field(
        default_factory=list, description="Concrete detections that produced the score"
    )


class ProjectIntelligence(CFBaseModel):
    """What a repository actually demonstrates, element by element."""

    repository_full_name: str
    detected_elements: list[str] = Field(
        default_factory=list,
        description="e.g. FreeRTOS, PID, UART DMA, IMU, Encoder — detected deterministically",
    )
    element_sources: dict[str, list[str]] = Field(
        default_factory=dict, description="element → files or commits where it was found"
    )
    domains: list[EngineeringSignal] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    architecture_hints: list[str] = Field(default_factory=list)
    readme_quality: Unit = Field(default=0.0, description="How usable the README is as evidence")
    commit_hygiene: Unit = Field(
        default=0.0, description="Share of commits with meaningful messages"
    )
    degraded: bool = False


class GithubProfileAnalysis(CFBaseModel):
    """The GitHub Intelligence page payload."""

    username: str
    languages: list[LanguageStat] = Field(default_factory=list)
    engineering_profile: list[EngineeringSignal] = Field(default_factory=list)
    repositories: list[RepoSummary] = Field(default_factory=list)
    total_stars: int = 0
    total_commits_sampled: int = 0
    last_analyzed_at: datetime | None = None
    degraded: bool = False
    notes: list[str] = Field(default_factory=list)

    @property
    def top_languages(self) -> list[LanguageStat]:
        return sorted(self.languages, key=lambda item: item.percent, reverse=True)[:5]


class ExtractedProjectIntelligence(StrictModel):
    """LLM-facing: narrative enrichment on top of deterministic detection.

    The element list is detected by rules from real file names and content; the
    model is only asked for the parts that genuinely require language ability.
    """

    highlights: list[str] = Field(
        default_factory=list,
        description="3–5 notable engineering aspects, each grounded in the input",
    )
    architecture_hints: list[str] = Field(
        default_factory=list,
        description="Inferred module layers, e.g. 'sensor → MCU → control loop'",
    )
    domains: list[str] = Field(
        default_factory=list, description="Engineering directions this project fits"
    )
    summary: str = Field(
        default="", description="Two sentences describing the project's engineering substance"
    )
