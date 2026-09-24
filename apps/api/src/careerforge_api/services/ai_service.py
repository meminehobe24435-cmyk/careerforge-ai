"""AI service layer: one place that builds executors and runs agents.

Three responsibilities, kept together because they share the same lifetime:

* **Build the executor.** The provider chain is created once per process (it holds a
  cache and resilience state); the executor, which carries a per-run tracker, is
  built per request so its traces land in that request's transaction.
* **Persist run traces.** :class:`DatabaseRunTracker` writes ``agent_runs`` rows so
  the AI Runs page has real data. It inserts on start and updates on finish: a run
  whose process died leaves a ``running`` row behind, which is the honest record —
  silent disappearance would be worse.
* **Hold interview sessions.** An interview spans several HTTP calls, so its state
  has to live somewhere between them.

The session store is in-process, and that is a real limitation rather than a design
choice: a second worker would not see a session started by the first. It is stated
here and surfaced by ``GET /ai/capabilities`` so the constraint is visible rather
than discovered. Moving it to Redis is the same change as the queue's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from careerforge_ai.agents import (
    CoachAgent,
    EvidenceAgent,
    InterviewAgent,
    JobAgent,
    MatchAgent,
    ProfileAgent,
    RecruiterAgent,
    ResumeAgent,
    ValidatorAgent,
)
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import PromptRegistry
from careerforge_ai.providers import LLMProvider
from careerforge_ai.schemas.interview import InterviewSession
from careerforge_ai.schemas.observability import AgentRunRecord
from careerforge_api.core.logging import get_logger
from careerforge_api.models.observability import AgentRun
from careerforge_api.services.metering import (
    DatabaseCacheStore,
    MeteredProvider,
    RunRecorder,
)

__all__ = ["AIService", "DatabaseRunTracker", "InterviewSessionStore", "AGENT_CATALOGUE"]

logger = get_logger("careerforge_api.ai")

#: The agent catalogue, in the order ``docs/ARCHITECTURE.md`` introduces them. Kept
#: as data so ``GET /ai/capabilities`` reports what exists rather than a hand-written
#: claim about what exists.
AGENT_CATALOGUE: tuple[dict[str, str], ...] = (
    {
        "agent": "profile",
        "workflow": "profile_ingest",
        "status": "ready",
        "purpose": "简历/文档 → 结构化候选人画像",
    },
    {
        "agent": "evidence",
        "workflow": "evidence_build",
        "status": "ready",
        "purpose": "材料 → 证据节点与证据图谱",
    },
    {
        "agent": "job",
        "workflow": "jd_analysis",
        "status": "ready",
        "purpose": "JD → 结构化、归一化的岗位分析",
    },
    {
        "agent": "match",
        "workflow": "job_match",
        "status": "ready",
        "purpose": "五维可解释匹配评分（确定性）",
    },
    {
        "agent": "validator",
        "workflow": "claim_validate",
        "status": "ready",
        "purpose": "断言验证与防幻觉门禁",
    },
    {
        "agent": "resume",
        "workflow": "resume_optimize",
        "status": "ready",
        "purpose": "简历逐条改写，全部过门禁",
    },
    {
        "agent": "interview",
        "workflow": "interview_start/turn/finish",
        "status": "ready",
        "purpose": "自适应模拟面试与七维 Scorecard",
    },
    {
        "agent": "coach",
        "workflow": "skill_gap",
        "status": "ready",
        "purpose": "技能缺口 → 30 天计划与 mini project",
    },
    {
        "agent": "recruiter",
        "workflow": "recruiter_publish",
        "status": "ready",
        "purpose": "公开候选人页（含 PII 脱敏）",
    },
)


@dataclass(slots=True)
class _RunRow:
    """A run whose row has been inserted and whose steps are accumulated in memory."""

    record: AgentRunRecord
    row_id: UUID


class DatabaseRunTracker:
    """Persists ``agent_runs``. Insert on start, update on finish.

    Steps are accumulated in memory and written once at the end rather than on every
    step. A request-scoped run is short enough that incremental writes would only add
    round-trips, and a crash mid-run still leaves the ``running`` row that says so.
    """

    def __init__(self, session: AsyncSession, *, recorder: RunRecorder | None = None) -> None:
        self._session = session
        self._rows: dict[int, _RunRow] = {}
        #: Told about the run id so the model calls made inside it can point back at it. Without
        #: this link ``llm_calls`` rows are orphans, and "which model call belonged to this run"
        #: — the question the AI Runs page exists to answer — has no answer.
        self._recorder = recorder

    async def start_run(self, record: AgentRunRecord) -> AgentRunRecord:
        row = AgentRun(
            id=record.id or uuid4(),
            user_id=record.user_id,
            workflow=record.workflow,
            agent=record.agent,
            status="running",
            trigger=record.trigger
            if record.trigger in {"api", "job", "manual", "seed", "eval"}
            else "api",
            steps=[],
            input_ref={},
            output_ref={},
            provider=record.provider,
            model=record.model,
            request_id=record.request_id,
            started_at=record.started_at,
        )
        self._session.add(row)
        await self._session.flush()
        record.id = row.id
        self._rows[id(record)] = _RunRow(record=record, row_id=row.id)
        if self._recorder is not None:
            self._recorder.bind_run(row.id)
        return record

    async def record_step(self, run: AgentRunRecord, step: Any) -> None:
        # Accumulated on the record; written by ``finish_run``.
        run.steps.append(step)
        run.recompute_totals()

    async def finish_run(self, run: AgentRunRecord) -> None:
        run.recompute_totals()
        tracked = self._rows.pop(id(run), None)
        if tracked is None:
            return
        row = await self._session.get(AgentRun, tracked.row_id)
        if row is None:  # pragma: no cover - the row is inserted in start_run
            return
        row.status = run.status.value if hasattr(run.status, "value") else str(run.status)
        row.steps = [step.model_dump(mode="json") for step in run.steps]
        row.input_ref = dict(run.input_ref)
        row.output_ref = dict(run.output_ref)
        row.prompt_tokens = run.tokens.prompt_tokens
        row.completion_tokens = run.tokens.completion_tokens
        row.total_tokens = run.tokens.total_tokens
        row.cost_usd = run.cost.usd
        row.cost_cny = run.cost.cny
        row.latency_ms = run.latency_ms
        row.cache_hit = run.cache_hits > 0
        row.prompt_version = run.prompt_version
        row.error = run.error_message
        row.finished_at = run.finished_at


class InterviewSessionStore:
    """In-process interview sessions, keyed by session id and scoped per user.

    Scoping matters: without the user check, one account could continue another's
    interview by guessing an id.
    """

    def __init__(self) -> None:
        self._sessions: dict[UUID, tuple[UUID | None, InterviewSession]] = {}

    def put(self, session: InterviewSession, *, user_id: UUID | None) -> UUID:
        session_id = session.id or uuid4()
        session.id = session_id
        self._sessions[session_id] = (user_id, session)
        return session_id

    def get(self, session_id: UUID, *, user_id: UUID | None) -> InterviewSession | None:
        entry = self._sessions.get(session_id)
        if entry is None:
            return None
        owner, session = entry
        if owner is not None and owner != user_id:
            return None
        return session

    def drop(self, session_id: UUID) -> None:
        self._sessions.pop(session_id, None)

    @property
    def active(self) -> int:
        return len(self._sessions)


class AIService:
    """Request-scoped access to the agent layer."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        prompts: PromptRegistry,
        session: AsyncSession | None = None,
        sessions: InterviewSessionStore | None = None,
        retriever: Any | None = None,
        cache_store: DatabaseCacheStore | None = None,
        user_id: UUID | None = None,
    ) -> None:
        self._provider = provider
        self._prompts = prompts
        self._session = session
        self.sessions = sessions if sessions is not None else InterviewSessionStore()
        self._retriever = retriever
        #: Shared across requests (built once with the provider chain), so a second identical
        #: request hits the first one's cached answer — which is what makes a hit rate meaningful.
        self.cache_store = cache_store
        self._user_id = user_id
        self._recorder: RunRecorder | None = None

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def embedder(self) -> Any:
        """The provider, for callers that need embeddings rather than completions.

        The retriever's vector arm takes anything with an ``embed`` method, and the provider
        already satisfies that port. Handing it over explicitly keeps the choice visible: a
        caller that wants lexical-only retrieval simply passes nothing.
        """
        return self._provider

    def executor(self, *, agent: str = "api", workflow: str = "ai") -> WorkflowExecutor:
        """An executor whose traces and model calls are persisted through this session.

        ``user_id`` and ``request_id`` are passed to ``executor.run()`` by the caller rather than
        captured here, because a single request may run several agents and each should be
        attributable on its own. ``agent`` / ``workflow`` label the metered calls: a ``llm_calls``
        row that cannot say which agent made the call is a row an operator cannot act on.
        """
        tracker = (
            DatabaseRunTracker(self._session, recorder=self.recorder())
            if self._session is not None
            else None
        )
        provider = self._provider
        if self._session is not None:
            # The wrapper sits *outside* the shared chain, so the cache and the resilience state
            # the app built once keep being the ones in use; only the recording is per request.
            provider = MeteredProvider(
                self._provider,
                recorder=self.recorder(),
                agent=agent,
                workflow=workflow,
            )
        return WorkflowExecutor(
            provider=provider,
            prompts=self._prompts,
            tracker=tracker,
            cache=self.cache_store,
            # One retry inside a request: the provider chain already retries transient
            # failures, and stacking retries multiplies worst-case latency.
            settings=ExecutorSettings(max_retries=1),
        )

    def recorder(self) -> RunRecorder:
        """The metering buffer for this request, or a detached one when there is no session."""
        if self._recorder is None:
            self._recorder = RunRecorder(self._session, user_id=self._user_id)  # type: ignore[arg-type]
        return self._recorder

    async def flush_observability(self) -> int:
        """Write the buffered model calls and cache events.

        Called by the endpoints that run AI work, before their response is serialised: the
        request owns the transaction, so this is the one place the rows can be written without
        opening a second connection mid-flight.
        """
        if self._recorder is None:
            return 0
        return await self._recorder.flush(cache_store=self.cache_store)

    # ── agents ───────────────────────────────────────────────────────────────

    def profile_agent(self) -> ProfileAgent:
        return ProfileAgent()

    def evidence_agent(self) -> EvidenceAgent:
        return EvidenceAgent()

    def job_agent(self) -> JobAgent:
        return JobAgent()

    def match_agent(self) -> MatchAgent:
        return MatchAgent()

    def validator_agent(self) -> ValidatorAgent:
        return ValidatorAgent()

    def resume_agent(self) -> ResumeAgent:
        return ResumeAgent()

    def interview_agent(self) -> InterviewAgent:
        return InterviewAgent()

    def coach_agent(self) -> CoachAgent:
        return CoachAgent()

    def recruiter_agent(self) -> RecruiterAgent:
        return RecruiterAgent()

    @property
    def retriever(self) -> Any | None:
        """The hybrid retriever, when one is configured for this process.

        ``None`` on the current deployment: the evidence tables arrive with the
        Evidence Graph phase, so validation runs on supplied material alone and says
        so in its reasons rather than pretending retrieval happened.
        """
        return self._retriever
