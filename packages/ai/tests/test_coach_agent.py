"""Tests for CoachAgent.

The rule under test: every gap ends in an artefact. A plan that produces only
"understanding" produces nothing in this system, so the assertions check that each
planned gap comes with a mini project and a claim the candidate could support
afterwards.
"""

from __future__ import annotations

import pytest

from careerforge_ai.agents import CoachAgent, build_learning_plan
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


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        slug="alex",
        headline="Embedded Engineer",
        summary="电子信息工程本科，做过两轮自平衡机器人。",
        years_experience=1.0,
        experiences=[
            Experience(
                company="某科技",
                title="嵌入式实习生",
                description="使用 STM32 与 FreeRTOS 开发电机控制固件。",
            )
        ],
        projects=[
            Project(
                name="Balance Robot",
                summary="基于 STM32 的两轮自平衡小车",
                tech_stack=["STM32", "FreeRTOS", "PID"],
            )
        ],
        skills=[
            ProfileSkill(
                skill=SkillRef(
                    canonical_id="stm32", display_name="STM32", category=SkillCategory.EMBEDDED
                ),
                level=SkillLevel.STRONG,
                evidence_count=3,
            )
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
        education_requirement="本科",
        required_skills=[
            required("stm32", "STM32"),
            required("can", "CAN"),
            required("autosar", "AUTOSAR"),
        ],
    )


@pytest.fixture
def graph(profile: CandidateProfile):
    return build_evidence_graph(
        profile=profile,
        evidence=[
            EvidenceItem(
                kind=EvidenceKind.REPO_FILE,
                title="motor_control.c",
                snippet="基于 STM32 的 PID 电机控制实现。",
                locator=EvidenceLocator(path="Core/Src/motor_control.c", line=42),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                confidence=0.0,
                occurred_at=utcnow(),
            )
        ],
    )


class TestGapMatrix:
    async def test_produces_a_plan_with_priorities(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        plan, outcome = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        assert outcome.ok
        assert plan is not None
        assert plan.weeks
        assert plan.priority_order

    async def test_matrix_travels_alongside_the_plan(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        _, outcome = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        matrix = outcome.extras.get("matrix")
        assert matrix is not None
        # STM32 is evidenced, CAN and AUTOSAR are not.
        met = {row.canonical_id for row in matrix.rows if row.gap_level.value == "none"}
        assert "stm32" in met
        assert "can" not in met

    async def test_priorities_are_descending(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        _, outcome = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        matrix = outcome.extras["matrix"]
        priorities = [row.priority for row in matrix.rows]
        assert priorities == sorted(priorities, reverse=True)

    async def test_missing_graph_is_reported(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis
    ) -> None:
        _, outcome = await build_learning_plan(executor, job=job, profile=profile)
        assert any("证据图谱" in warning for warning in outcome.warnings)


class TestPlan:
    async def test_plan_is_ordered_by_computed_priority(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        plan, _ = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        assert plan is not None
        # CAN and AUTOSAR are the gaps; STM32 is met and must not be planned.
        assert "stm32" not in plan.priority_order
        assert set(plan.priority_order) <= {"can", "autosar"}

    async def test_every_planned_gap_gets_a_mini_project(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        plan, _ = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        assert plan is not None
        planned_skills = set(plan.priority_order)
        project_skills = {project.skill_canonical_id for project in plan.mini_projects}
        assert planned_skills <= project_skills

    async def test_mini_projects_state_what_they_prove(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        plan, _ = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        assert plan is not None
        assert plan.mini_projects
        for project in plan.mini_projects:
            assert project.evidence_potential
            assert project.deliverables
            assert project.acceptance_criteria

    async def test_weeks_have_concrete_outputs(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        plan, _ = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        assert plan is not None
        for week in plan.weeks:
            assert week.theme
            assert week.output
            assert week.verification

    async def test_horizon_is_configurable(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        plan, _ = await build_learning_plan(
            executor, job=job, profile=profile, graph=graph, horizon_days=60
        )
        assert plan is not None
        assert plan.horizon_days == 60
        assert len(plan.weeks) > 4

    async def test_no_gaps_means_no_plan_but_no_crash(
        self, executor: WorkflowExecutor, profile: CandidateProfile, graph
    ) -> None:
        # A job that requires nothing the candidate lacks, *with* the graph: without
        # it a claimed skill carries no confidence and correctly counts as a gap."""
        job = JDAnalysis(
            role="匹配岗位",
            required_skills=[
                JDSkill(
                    canonical_id="stm32",
                    raw_text="STM32",
                    requirement=RequirementLevel.REQUIRED,
                )
            ],
        )
        plan, outcome = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        assert plan is not None
        assert plan.priority_order == []
        assert any("缺口" in warning for warning in outcome.warnings)


class TestWorkflowShape:
    async def test_trace_names_every_step(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        _, outcome = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        assert [step.name for step in outcome.record.steps] == [
            "matrix",
            "prioritise",
            "plan",
            "assemble",
        ]

    async def test_agent_exposes_its_workflow(self) -> None:
        workflow = CoachAgent().workflow()
        assert workflow.name == "skill_gap"
        assert workflow.agent == "coach"

    async def test_missing_inputs_fail_loudly(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        with pytest.raises(ValueError):
            await CoachAgent().run(executor, job=None, profile=profile)  # type: ignore[arg-type]

    async def test_is_deterministic(
        self, executor: WorkflowExecutor, profile: CandidateProfile, job: JDAnalysis, graph
    ) -> None:
        first, _ = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        second, _ = await build_learning_plan(executor, job=job, profile=profile, graph=graph)
        assert first is not None and second is not None
        assert first.priority_order == second.priority_order
        assert [w.theme for w in first.weeks] == [w.theme for w in second.weeks]
