"""Tests for MatchAgent.

The property under test is the one the product promises: a match score a user can
interrogate, produced without a model, and identical on every run. The narrative
step is checked in the opposite direction — it must be *unable* to change the
number, and its absence must not remove the explanation.
"""

from __future__ import annotations

import pytest

from careerforge_ai.agents import MatchAgent, compute_match
from careerforge_ai.graph import build_evidence_graph
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.common import (
    EvidenceKind,
    RequirementLevel,
    SkillCategory,
    SkillLevel,
    SourceAuthority,
    utcnow,
)
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator
from careerforge_ai.schemas.job import JDAnalysis, JDSkill
from careerforge_ai.schemas.match import MatchDimensionKey
from careerforge_ai.schemas.profile import (
    CandidateProfile,
    Experience,
    ProfileSkill,
    Project,
    SkillRef,
)


@pytest.fixture
def executor() -> WorkflowExecutor:
    return WorkflowExecutor(
        provider=HeuristicProvider(),
        prompts=load_prompt_registry(),
        settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
    )


def _skill(
    canonical_id: str, display: str, category: SkillCategory, level: SkillLevel
) -> ProfileSkill:
    return ProfileSkill(
        skill=SkillRef(canonical_id=canonical_id, display_name=display, category=category),
        level=level,
        # Evidence counts matter: without them the engine treats every claim as
        # unproven and the evidence dimension has nothing to measure.
        evidence_count=3,
        evidence_score=0.9,
    )


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        slug="alex",
        headline="Embedded Engineer",
        summary="电子信息工程本科，做过两轮自平衡机器人与无人机控制链路。",
        target_roles=["Embedded Engineer"],
        years_experience=1.0,
        experiences=[
            Experience(
                company="某科技",
                title="嵌入式软件实习生",
                description="使用 STM32 与 FreeRTOS 开发电机控制固件。",
            )
        ],
        projects=[
            Project(
                name="Balance Robot",
                summary="基于 STM32 的两轮自平衡小车",
                description="使用 FreeRTOS 划分任务，PID 控制电机。",
                tech_stack=["STM32", "FreeRTOS", "PID"],
            )
        ],
        skills=[
            _skill("stm32", "STM32", SkillCategory.EMBEDDED, SkillLevel.STRONG),
            _skill("free_rtos", "FreeRTOS", SkillCategory.EMBEDDED, SkillLevel.STRONG),
            _skill("c", "C", SkillCategory.LANGUAGE, SkillLevel.STRONG),
        ],
    )


@pytest.fixture
def job() -> JDAnalysis:
    def required(canonical_id: str, raw: str) -> JDSkill:
        return JDSkill(
            canonical_id=canonical_id,
            raw_text=raw,
            requirement=RequirementLevel.REQUIRED,
            jd_evidence=f"熟悉 {raw}",
        )

    return JDAnalysis(
        company="某科技",
        role="嵌入式软件工程师",
        location="深圳",
        education_requirement="本科",
        years_experience_min=1.0,
        required_skills=[
            required("stm32", "STM32"),
            required("free_rtos", "FreeRTOS"),
            required("c", "C"),
            required("can", "CAN"),
        ],
    )


@pytest.fixture
def graph(profile: CandidateProfile):
    evidence = [
        EvidenceItem(
            kind=EvidenceKind.REPO_FILE,
            title="motor_control.c",
            snippet="基于 STM32 与 FreeRTOS 的 PID 电机闭环控制实现。",
            locator=EvidenceLocator(path="Core/Src/motor_control.c", line=42),
            source_authority=SourceAuthority.CODE_OR_COMMIT,
            confidence=0.0,
            occurred_at=utcnow(),
        ),
        EvidenceItem(
            kind=EvidenceKind.COMMIT,
            title="a1b2c3d",
            snippet="feat: STM32 时钟与 FreeRTOS 任务初始化",
            locator=EvidenceLocator(sha="a1b2c3d"),
            source_authority=SourceAuthority.CODE_OR_COMMIT,
            confidence=0.0,
            occurred_at=utcnow(),
        ),
    ]
    return build_evidence_graph(profile=profile, evidence=evidence, job=None)


class TestMatchResult:
    async def test_produces_a_score_with_five_dimensions(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        result, outcome = await compute_match(executor, job=job, profile=profile)
        assert outcome.ok
        assert result is not None
        assert 0.0 <= result.score <= 100.0
        assert set(result.dimensions) == set(MatchDimensionKey.ALL)

    async def test_why_payload_is_complete(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        result, _ = await compute_match(executor, job=job, profile=profile)
        assert result is not None
        assert result.why.formula
        assert len(result.why.dimensions) == 5
        assert result.why.explanation
        assert result.why.algorithm_version == "match@1.0.0"
        for dimension in result.why.dimensions:
            assert dimension.formula, dimension.key

    async def test_dimensions_sum_to_the_total(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        result, _ = await compute_match(executor, job=job, profile=profile)
        assert result is not None
        assert sum(dim.weighted for dim in result.dimensions.values()) == pytest.approx(
            result.score, abs=0.01
        )

    async def test_is_reproducible(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        first, _ = await compute_match(executor, job=job, profile=profile)
        second, _ = await compute_match(executor, job=job, profile=profile)
        assert first is not None and second is not None
        assert first.score == second.score
        assert [d.score for d in first.dimensions.values()] == [
            d.score for d in second.dimensions.values()
        ]
        assert first.why.formula == second.why.formula

    async def test_gaps_and_unknowns_are_distinguished(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        result, _ = await compute_match(executor, job=job, profile=profile)
        assert result is not None
        gap_ids = {item.canonical_id for item in result.gaps}
        unknown_ids = {item.canonical_id for item in result.unknowns}
        # CAN is embedded and the candidate demonstrably has embedded evidence.
        assert "can" in gap_ids
        assert gap_ids.isdisjoint(unknown_ids)

    async def test_evidence_from_the_graph_raises_confidence(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        with_graph, _ = await compute_match(executor, job=job, profile=profile, graph=graph)
        without_graph, _ = await compute_match(executor, job=job, profile=profile)
        assert with_graph is not None and without_graph is not None
        assert (
            with_graph.dimensions[MatchDimensionKey.EVIDENCE].score
            > without_graph.dimensions[MatchDimensionKey.EVIDENCE].score
        )

    async def test_missing_graph_is_reported_not_hidden(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        _, outcome = await compute_match(executor, job=job, profile=profile)
        assert any("证据图谱" in warning for warning in outcome.warnings)


class TestNarrative:
    async def test_narrative_cannot_be_empty_without_losing_the_explanation(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        # The heuristic provider has no handler for the narrative schema, so the
        # prose is empty — but the deterministic explanation must still be there.
        result, _ = await compute_match(executor, job=job, profile=profile)
        assert result is not None
        assert result.why.explanation
        assert result.narrative == "" or isinstance(result.narrative, str)

    async def test_narrative_schema_has_no_numeric_field(self) -> None:
        """Structural guarantee: a model cannot return a different score."""
        from careerforge_ai.schemas.match import ExtractedMatchNarrative

        for name, field in ExtractedMatchNarrative.model_fields.items():
            assert field.annotation is str or field.annotation == list[str], name


class TestWorkflowShape:
    async def test_trace_names_every_step(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        _, outcome = await compute_match(executor, job=job, profile=profile)
        names = [step.name for step in outcome.record.steps]
        assert names == ["prepare", "score", "narrate"]

    async def test_agent_exposes_its_workflow(self) -> None:
        workflow = MatchAgent().workflow()
        assert workflow.name == "job_match"
        assert workflow.agent == "match"

    async def test_missing_inputs_fail_loudly(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        with pytest.raises(ValueError):
            await MatchAgent().run(executor, job=None, profile=profile)  # type: ignore[arg-type]
