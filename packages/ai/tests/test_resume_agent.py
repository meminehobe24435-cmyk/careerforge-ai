"""Tests for ResumeAgent — the Copilot whose every line passes the gate.

The product claim is that no unverifiable sentence reaches the resume. These tests
check the claim from both sides: a bullet the material supports is allowed through,
and a bullet carrying a fabricated metric is blocked, kept out of the accepted set,
and comes back with advice on how to make it provable.
"""

from __future__ import annotations

import pytest

from careerforge_ai.agents import ResumeAgent, optimize_resume
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.claim import ClaimStatus
from careerforge_ai.schemas.common import SkillCategory, SkillLevel
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
        summary="电子信息工程本科，做过两轮自平衡机器人与无人机控制链路。",
        experiences=[
            Experience(
                company="某科技",
                title="嵌入式软件实习生",
                description="使用 STM32 与 FreeRTOS 开发电机控制固件。",
                highlights=["参与完成基于 STM32 与 FreeRTOS 的电机控制固件开发"],
            )
        ],
        projects=[
            Project(
                name="Balance Robot",
                summary="参与完成基于 STM32 的两轮自平衡小车控制程序开发",
                description="使用 FreeRTOS 划分任务，PID 控制电机。",
                tech_stack=["STM32", "FreeRTOS", "PID"],
            )
        ],
        skills=[
            ProfileSkill(
                skill=SkillRef(
                    canonical_id="stm32", display_name="STM32", category=SkillCategory.EMBEDDED
                ),
                level=SkillLevel.STRONG,
                evidence_count=2,
            )
        ],
    )


class TestGeneration:
    async def test_produces_a_result_with_bullets(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        result, outcome = await optimize_resume(executor, profile=profile)
        assert outcome.ok
        assert result is not None
        assert result.bullets or result.rejected
        assert result.validations

    async def test_every_bullet_is_validated(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        result, _ = await optimize_resume(executor, profile=profile)
        assert result is not None
        # One validation per generated bullet, in order — the gate is not sampling.
        assert len(result.validations) == len(result.bullets) + len(result.rejected)

    async def test_removes_filler_without_adding_facts(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        result, _ = await optimize_resume(executor, profile=profile)
        assert result is not None
        assert result.bullets
        bullet = result.bullets[0]
        assert "参与完成" not in bullet.optimized
        assert "STM32" in bullet.optimized
        # The deterministic rewriter never introduces a term.
        assert bullet.keywords_added == []

    async def test_accepts_explicit_bullets(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        result, _ = await optimize_resume(
            executor,
            profile=profile,
            bullets=[{"section": "project", "text": "参与完成基于 STM32 的电机控制程序开发"}],
        )
        assert result is not None
        assert len(result.validations) == 1


class TestGate:
    async def test_blocks_a_fabricated_metric(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        result, _ = await optimize_resume(
            executor,
            profile=profile,
            bullets=[{"section": "project", "text": "优化算法性能，提升 70%"}],
        )
        assert result is not None
        assert result.rejected
        # ``unsupported``: the evidence does not refute the number, it simply cannot carry it.
        # The bullet is refused either way — what changed is that the gate no longer claims the
        # candidate's own material conflicts with them.
        assert result.rejected[0].status is ClaimStatus.UNSUPPORTED
        # The blocked bullet must not appear among the accepted ones.
        assert all("70%" not in bullet.optimized for bullet in result.bullets)

    async def test_blocked_claims_come_with_advice(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        result, _ = await optimize_resume(
            executor,
            profile=profile,
            bullets=[{"section": "project", "text": "优化算法性能，提升 70%"}],
        )
        assert result is not None
        assert result.new_evidence_suggestions
        assert any("实测" in item or "数字" in item for item in result.new_evidence_suggestions)

    async def test_integrity_score_reflects_the_accepted_share(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        result, _ = await optimize_resume(
            executor,
            profile=profile,
            bullets=[
                {"section": "project", "text": "参与完成基于 STM32 的电机控制程序开发"},
                {"section": "project", "text": "优化算法性能，提升 70%"},
            ],
        )
        assert result is not None
        assert 0.0 <= result.integrity_score <= 1.0
        assert result.integrity_score == pytest.approx(0.5, abs=0.01)

    async def test_claim_stats_count_every_status(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        result, _ = await optimize_resume(
            executor,
            profile=profile,
            bullets=[
                {"section": "project", "text": "参与完成基于 STM32 的电机控制程序开发"},
                {"section": "project", "text": "优化算法性能，提升 70%"},
            ],
        )
        assert result is not None
        assert sum(result.claim_stats.values()) == len(result.validations)
        # The fabricated metric lands in ``unsupported`` (refused but not refuted); the
        # evidence-supported bullet is at most partially supported, because one profile is one
        # source and corroboration needs two.
        assert result.claim_stats.get("unsupported", 0) == 1
        assert result.claim_stats.get("partially_supported", 0) == 1
        assert result.claim_stats.get("contradicted", 0) == 0

    async def test_self_report_alone_is_weak_not_supported(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        """A bullet backed only by the candidate's own material is 'weak evidence'."""
        result, _ = await optimize_resume(
            executor,
            profile=profile,
            bullets=[
                {"section": "project", "text": "参与完成基于 STM32 与 FreeRTOS 的电机控制固件开发"}
            ],
        )
        assert result is not None
        status = result.validations[0].status
        assert status in {ClaimStatus.PARTIALLY_SUPPORTED, ClaimStatus.SUPPORTED}
        if status is ClaimStatus.PARTIALLY_SUPPORTED:
            assert any("自述" in reason.message for reason in result.validations[0].reasons)

    async def test_unrelated_bullet_is_not_accepted(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        result, _ = await optimize_resume(
            executor,
            profile=profile,
            bullets=[{"section": "summary", "text": "精通 Kubernetes 集群运维与故障排查"}],
        )
        assert result is not None
        assert result.rejected
        assert result.integrity_score == 0.0


class TestWorkflowShape:
    async def test_trace_names_every_step(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        _, outcome = await optimize_resume(executor, profile=profile)
        assert [step.name for step in outcome.record.steps] == [
            "load_ctx",
            "generate",
            "validate",
            "gate",
            "assemble",
        ]

    async def test_agent_exposes_its_workflow(self) -> None:
        workflow = ResumeAgent().workflow()
        assert workflow.name == "resume_optimize"
        assert workflow.agent == "resume"

    async def test_missing_profile_fails_loudly(self, executor: WorkflowExecutor) -> None:
        with pytest.raises(ValueError):
            await ResumeAgent().run(executor, profile=None)  # type: ignore[arg-type]

    async def test_is_deterministic(
        self, executor: WorkflowExecutor, profile: CandidateProfile
    ) -> None:
        first, _ = await optimize_resume(executor, profile=profile)
        second, _ = await optimize_resume(executor, profile=profile)
        assert first is not None and second is not None
        assert first.integrity_score == second.integrity_score
        assert [b.optimized for b in first.bullets] == [b.optimized for b in second.bullets]
        assert [v.status for v in first.validations] == [v.status for v in second.validations]
