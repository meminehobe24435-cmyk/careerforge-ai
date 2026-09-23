"""Ports: the interfaces the AI core uses to reach the outside world.

The AI core is deliberately ignorant of web frameworks and ORMs (ADR-022). It
talks to persistence and external services only through these protocols, which
means every agent can be unit-tested with an in-memory fake — no database, no
network, and no API key.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from careerforge_ai.schemas.evidence import (
    EvidenceItem,
    EvidenceLink,
    GraphQuery,
    RetrievalResult,
)
from careerforge_ai.schemas.github import RepoSummary
from careerforge_ai.schemas.profile import CandidateProfile

__all__ = [
    "Clock",
    "EvidenceRepository",
    "GitHubPort",
    "JobRepository",
    "ProfileRepository",
    "RunRepository",
    "SystemClock",
    "VectorHit",
    "VectorRecord",
    "VectorStore",
]


class VectorRecord:
    """One embedded item awaiting storage."""

    __slots__ = ("content_hash", "dim", "metadata", "model", "owner_id", "owner_type", "vector")

    def __init__(
        self,
        *,
        owner_type: str,
        owner_id: UUID,
        model: str,
        vector: Sequence[float],
        content_hash: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.owner_type = owner_type
        self.owner_id = owner_id
        self.model = model
        self.dim = len(vector)
        self.vector = list(vector)
        self.content_hash = content_hash
        self.metadata = dict(metadata or {})


class VectorHit:
    """A nearest-neighbour result."""

    __slots__ = ("metadata", "owner_id", "owner_type", "score")

    def __init__(
        self,
        *,
        owner_type: str,
        owner_id: UUID,
        score: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.owner_type = owner_type
        self.owner_id = owner_id
        self.score = score
        self.metadata = dict(metadata or {})


@runtime_checkable
class VectorStore(Protocol):
    """Dense-vector storage and nearest-neighbour search.

    Implemented by ``PgVectorStore`` (production) and ``SqliteVectorStore``
    (local, exact search over a normalised matrix) behind the same contract
    (ADR-004).
    """

    async def upsert(self, records: Sequence[VectorRecord], *, user_id: UUID) -> int: ...

    async def search(
        self,
        vector: Sequence[float],
        *,
        user_id: UUID,
        owner_types: Sequence[str] | None = None,
        model: str | None = None,
        limit: int = 10,
        filters: Mapping[str, Any] | None = None,
    ) -> list[VectorHit]: ...

    async def delete(self, *, user_id: UUID, owner_type: str, owner_ids: Sequence[UUID]) -> int: ...


@runtime_checkable
class EvidenceRepository(Protocol):
    """Read/write access to evidence and its graph edges."""

    async def add(self, items: Sequence[EvidenceItem], *, user_id: UUID) -> list[UUID]: ...

    async def add_links(self, links: Sequence[EvidenceLink], *, user_id: UUID) -> int: ...

    async def get(self, evidence_id: UUID, *, user_id: UUID) -> EvidenceItem | None: ...

    async def list_for_owner(
        self, *, user_id: UUID, owner_type: str, owner_id: UUID
    ) -> list[EvidenceItem]: ...

    async def graph(self, query: GraphQuery, *, user_id: UUID) -> tuple[list[Any], list[Any]]: ...

    async def lexical_search(
        self, query: str, *, user_id: UUID, limit: int = 20
    ) -> list[EvidenceItem]: ...


@runtime_checkable
class ProfileRepository(Protocol):
    """Candidate profile persistence."""

    async def load(self, *, user_id: UUID) -> CandidateProfile | None: ...

    async def save(self, profile: CandidateProfile, *, user_id: UUID) -> CandidateProfile: ...

    async def evidence_stats(self, *, user_id: UUID) -> Mapping[str, Any]: ...


@runtime_checkable
class JobRepository(Protocol):
    """Job persistence for the matching and gap workflows."""

    async def load_analysis(self, job_id: UUID, *, user_id: UUID) -> Any | None: ...

    async def save_skills(self, job_id: UUID, *, user_id: UUID, skills: Sequence[Any]) -> int: ...


@runtime_checkable
class RunRepository(Protocol):
    """Persistence for what the tracker produces, plus the cache table."""

    async def persist_run(self, record: Any) -> None: ...

    async def persist_llm_call(self, record: Any) -> None: ...

    async def cache_get(self, key: str) -> Any | None: ...

    async def cache_set(self, key: str, value: Any, *, ttl_seconds: int, kind: str) -> None: ...


@runtime_checkable
class GitHubPort(Protocol):
    """GitHub access, abstracted so tests and offline demos can supply fixtures."""

    async def fetch_repositories(self, username: str, *, limit: int = 30) -> list[RepoSummary]: ...

    async def fetch_readme(self, full_name: str) -> str: ...

    async def fetch_files(self, full_name: str, *, limit: int = 50) -> list[Any]: ...

    async def fetch_commits(self, full_name: str, *, limit: int = 50) -> list[Any]: ...

    async def rate_limit(self) -> Mapping[str, Any]: ...


@runtime_checkable
class Clock(Protocol):
    """Injectable time, so recency-dependent scoring is testable."""

    def now(self) -> datetime: ...


class SystemClock:
    """Default clock: real UTC time."""

    def now(self) -> datetime:
        from careerforge_ai.schemas.common import utcnow

        return utcnow()


def retrieval_placeholder(query: str) -> RetrievalResult:
    """Empty result helper so callers never construct an inconsistent object."""
    return RetrievalResult(query=query)
