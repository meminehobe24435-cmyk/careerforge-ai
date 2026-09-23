"""Tests for the agent layer: JobAgent and ValidatorAgent.

These exercise the workflows end to end through a real :class:`WorkflowExecutor`
with the heuristic provider, which is the configuration most reviewers will run.
The important assertions are about *honesty*: the gate must refuse an unsupported
number, and it must never claim a model judgement it did not receive.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from careerforge_ai.agents import (
    JobAgent,
    ValidatorAgent,
    build_jd_analysis,
    strip_markup,
    truncate_for_prompt,
    validate_claim_text,
)
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.rag import HybridRetriever, RetrievalDocument
from careerforge_ai.schemas.common import ClaimStatus, EvidenceKind
from careerforge_ai.schemas.evidence import EvidenceLocator

EMBEDDED_JD = """某科技
嵌入式软件工程师
工作地点：深圳

公司简介
我们使用 Kubernetes 与 React 构建内部平台。

岗位职责：
1. 负责嵌入式软件的设计、开发与调试；

任职要求：
1. 本科及以上学历，3 年嵌入式开发经验；
2. 熟悉 STM32、FreeRTOS，掌握 C 语言；
3. 熟悉 CAN、SPI 通信协议。

加分项：了解 AUTOSAR。
"""


@pytest.fixture
def executor() -> WorkflowExecutor:
    return WorkflowExecutor(
        provider=HeuristicProvider(),
        prompts=load_prompt_registry(),
        settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
    )


# ── text preparation ─────────────────────────────────────────────────────────


class TestTextPreparation:
    def test_strips_markup_and_script_bodies(self) -> None:
        html = "<div>任职要求<script>alert('x')</script><b>熟悉 STM32</b></div>"
        cleaned = strip_markup(html)
        assert "STM32" in cleaned
        assert "alert" not in cleaned
        assert "<" not in cleaned

    def test_decodes_common_entities(self) -> None:
        assert "&" in strip_markup("C&amp;C")

    def test_truncation_reports_itself(self) -> None:
        text, truncated = truncate_for_prompt("字" * 100, budget=50)
        assert truncated is True
        assert "省略" in text
        assert len(text) < 120

    def test_short_text_is_not_truncated(self) -> None:
        text, truncated = truncate_for_prompt("短文本", budget=50)
        assert truncated is False
        assert text == "短文本"


# ── JobAgent ─────────────────────────────────────────────────────────────────


class TestJobAgent:
    async def test_parses_and_normalises_a_jd(self, executor: WorkflowExecutor) -> None:
        analysis, outcome = await build_jd_analysis(executor, EMBEDDED_JD)
        assert outcome.ok
        assert analysis is not None
        assert analysis.role
        assert analysis.location == "深圳"
        assert analysis.years_experience_min == 3.0
        assert analysis.education_requirement == "本科"

    async def test_skills_carry_canonical_ids(self, executor: WorkflowExecutor) -> None:
        analysis, _ = await build_jd_analysis(executor, EMBEDDED_JD)
        assert analysis is not None
        canonical = {skill.canonical_id for skill in analysis.required_skills}
        assert {"stm32", "free_rtos", "c"} <= canonical

    async def test_requirement_levels_are_respected(self, executor: WorkflowExecutor) -> None:
        analysis, _ = await build_jd_analysis(executor, EMBEDDED_JD)
        assert analysis is not None
        required = {skill.canonical_id for skill in analysis.required_skills}
        bonus = {skill.canonical_id for skill in analysis.bonus_skills}
        assert "autosar" in bonus
        assert "autosar" not in required

    async def test_company_blurb_technology_is_not_a_requirement(
        self, executor: WorkflowExecutor
    ) -> None:
        analysis, _ = await build_jd_analysis(executor, EMBEDDED_JD)
        assert analysis is not None
        required = {skill.canonical_id for skill in analysis.required_skills}
        assert "kubernetes" not in required
        assert "react" not in required

    async def test_every_skill_quotes_the_source(self, executor: WorkflowExecutor) -> None:
        analysis, _ = await build_jd_analysis(executor, EMBEDDED_JD)
        assert analysis is not None
        for skill in analysis.all_skills:
            assert skill.jd_evidence

    async def test_reports_parse_confidence_and_status(self, executor: WorkflowExecutor) -> None:
        analysis, _ = await build_jd_analysis(executor, EMBEDDED_JD)
        assert analysis is not None
        assert 0.0 <= analysis.parse_confidence <= 1.0
        assert analysis.parse_status in {"parsed", "heuristic_fallback", "failed"}

    async def test_empty_input_degrades_instead_of_claiming_success(
        self, executor: WorkflowExecutor
    ) -> None:
        analysis, outcome = await build_jd_analysis(executor, "   ")
        assert analysis is not None
        assert analysis.parse_status == "heuristic_fallback"
        assert outcome.warnings

    async def test_trace_names_every_step(self, executor: WorkflowExecutor) -> None:
        _, outcome = await build_jd_analysis(executor, EMBEDDED_JD)
        names = [step.name for step in outcome.record.steps]
        assert names == ["clean", "extract", "normalise", "assess"]

    async def test_is_deterministic(self, executor: WorkflowExecutor) -> None:
        first, _ = await build_jd_analysis(executor, EMBEDDED_JD)
        second, _ = await build_jd_analysis(executor, EMBEDDED_JD)
        assert first is not None and second is not None
        assert first.model_dump() == second.model_dump()

    async def test_agent_exposes_its_workflow(self) -> None:
        workflow = JobAgent().workflow()
        assert workflow.name == "jd_analysis"
        assert workflow.agent == "job"


# ── ValidatorAgent ───────────────────────────────────────────────────────────


def _document(title: str, text: str, kind: EvidenceKind, confidence: float) -> RetrievalDocument:
    return RetrievalDocument(
        evidence_id=uuid4(),
        title=title,
        text=text,
        kind=kind,
        confidence=confidence,
        locator=EvidenceLocator(path=title, line=1),
    )


async def _executor_with_evidence(
    documents: list[RetrievalDocument],
) -> tuple[WorkflowExecutor, UUID, HybridRetriever]:
    user_id = uuid4()
    retriever = HybridRetriever(embedder=HeuristicProvider(dim=256))
    await retriever.index(documents, user_id=user_id)
    executor = WorkflowExecutor(
        provider=HeuristicProvider(),
        prompts=load_prompt_registry(),
        settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
    )
    return executor, user_id, retriever


class TestValidatorAgent:
    async def test_rejects_a_fabricated_metric(self) -> None:
        executor, user_id, retriever = await _executor_with_evidence(
            [
                _document(
                    "notes.md",
                    "对控制回路做了重构，减少了重复计算。",
                    EvidenceKind.DOCUMENT_CHUNK,
                    0.8,
                )
            ]
        )
        validation, outcome = await validate_claim_text(
            executor,
            "优化算法性能，提升 70%",
            retriever=retriever,
            user_id=user_id,
        )
        assert validation is not None
        assert validation.status is ClaimStatus.CONTRADICTED
        assert validation.is_blocking
        assert validation.has_quantified_claim
        assert any("70%" in str(mention.raw) for mention in validation.numeric_mentions)
        assert outcome.ok

    async def test_rejects_a_metric_even_with_no_evidence_at_all(self) -> None:
        executor = WorkflowExecutor(
            provider=HeuristicProvider(),
            prompts=load_prompt_registry(),
            settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
        )
        validation, _ = await validate_claim_text(executor, "将测试覆盖率提升至 90%")
        assert validation is not None
        # The rule layer blocks before retrieval is even attempted.
        assert validation.status is ClaimStatus.CONTRADICTED

    async def test_accepts_a_claim_with_two_independent_sources(self) -> None:
        shared = "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分并周期调度。"
        executor, user_id, retriever = await _executor_with_evidence(
            [
                _document("freertos.c", shared, EvidenceKind.REPO_FILE, 0.95),
                _document("abc123", f"feat: {shared}", EvidenceKind.COMMIT, 0.93),
            ]
        )
        validation, _ = await validate_claim_text(
            executor,
            "基于 FreeRTOS 开发多任务实时控制系统",
            retriever=retriever,
            user_id=user_id,
        )
        assert validation is not None
        assert validation.independent_source_count >= 2
        assert validation.status in {ClaimStatus.SUPPORTED, ClaimStatus.PARTIALLY_SUPPORTED}

    async def test_one_source_is_not_enough_for_supported(self) -> None:
        shared = "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分并周期调度。"
        executor, user_id, retriever = await _executor_with_evidence(
            [_document("freertos.c", shared, EvidenceKind.REPO_FILE, 0.95)]
        )
        validation, _ = await validate_claim_text(
            executor,
            "基于 FreeRTOS 开发多任务实时控制系统",
            retriever=retriever,
            user_id=user_id,
        )
        assert validation is not None
        assert validation.status is not ClaimStatus.SUPPORTED

    async def test_missing_technical_noun_prevents_support(self) -> None:
        executor, user_id, _retriever = await _executor_with_evidence(
            [
                _document(
                    "spi_sensor.c",
                    "在 STM32 上完成 SPI 传感器驱动的读写与寄存器配置。",
                    EvidenceKind.REPO_FILE,
                    0.95,
                )
            ]
        )
        validation, _ = await validate_claim_text(
            executor,
            "使用 STM32 完成 SPI 与 I2C 传感器驱动开发",
            user_id=user_id,
        )
        assert validation is not None
        assert validation.status is not ClaimStatus.SUPPORTED

    async def test_no_evidence_means_no_support(self) -> None:
        executor, user_id, retriever = await _executor_with_evidence([])
        validation, _ = await validate_claim_text(
            executor,
            "熟练使用 Redis 与 Kafka 构建高并发架构",
            retriever=retriever,
            user_id=user_id,
        )
        assert validation is not None
        assert validation.status in {ClaimStatus.UNSUPPORTED, ClaimStatus.PARTIALLY_SUPPORTED}
        assert validation.unknowns

    async def test_reports_when_retrieval_is_unavailable(self) -> None:
        executor = WorkflowExecutor(
            provider=HeuristicProvider(),
            prompts=load_prompt_registry(),
            settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
        )
        validation, outcome = await validate_claim_text(executor, "使用 Docker 部署服务")
        assert validation is not None
        # No retriever was provided: the run must say so rather than implying the
        # claim was checked.
        assert any("检索" in warning for warning in outcome.warnings)

    async def test_offers_a_safer_rewrite_for_a_blocked_claim(self) -> None:
        executor, user_id, retriever = await _executor_with_evidence(
            [_document("opt.md", "优化算法性能。", EvidenceKind.DOCUMENT_CHUNK, 0.8)]
        )
        validation, _ = await validate_claim_text(
            executor,
            "优化算法性能，提升 70%",
            retriever=retriever,
            user_id=user_id,
        )
        assert validation is not None
        assert validation.safe_rewrite is not None
        assert "70%" not in validation.safe_rewrite.text

    async def test_reasons_are_specific_and_actionable(self) -> None:
        executor, user_id, retriever = await _executor_with_evidence(
            [_document("opt.md", "优化算法性能。", EvidenceKind.DOCUMENT_CHUNK, 0.8)]
        )
        validation, _ = await validate_claim_text(
            executor,
            "优化算法性能，提升 70%",
            retriever=retriever,
            user_id=user_id,
        )
        assert validation is not None
        blocking = validation.blocking_reasons()
        assert blocking
        assert "70%" in blocking[0].message
        assert blocking[0].severity == "blocker"

    async def test_sources_carry_provenance(self) -> None:
        shared = "项目基于 FreeRTOS 实现多任务实时控制。"
        executor, user_id, retriever = await _executor_with_evidence(
            [_document("freertos.c", shared, EvidenceKind.REPO_FILE, 0.95)]
        )
        validation, _ = await validate_claim_text(
            executor,
            "基于 FreeRTOS 的多任务实时控制",
            retriever=retriever,
            user_id=user_id,
        )
        assert validation is not None
        assert validation.sources
        assert validation.sources[0].title == "freertos.c"
        assert validation.sources[0].locator.path == "freertos.c"

    async def test_trace_names_every_step(self) -> None:
        executor, user_id, _retriever = await _executor_with_evidence([])
        _, outcome = await validate_claim_text(executor, "使用 Docker", user_id=user_id)
        names = [step.name for step in outcome.record.steps]
        assert names == ["rules", "retrieve", "verdict", "decide"]

    async def test_is_deterministic(self) -> None:
        shared = "项目基于 FreeRTOS 实现多任务实时控制。"
        executor, user_id, _retriever = await _executor_with_evidence(
            [_document("freertos.c", shared, EvidenceKind.REPO_FILE, 0.95)]
        )
        first, _ = await validate_claim_text(executor, "基于 FreeRTOS 的控制系统", user_id=user_id)
        second, _ = await validate_claim_text(executor, "基于 FreeRTOS 的控制系统", user_id=user_id)
        assert first is not None and second is not None
        assert first.status == second.status
        assert first.confidence == second.confidence

    async def test_agent_exposes_its_workflow(self) -> None:
        workflow = ValidatorAgent().workflow()
        assert workflow.name == "claim_validate"
        assert workflow.agent == "validator"
