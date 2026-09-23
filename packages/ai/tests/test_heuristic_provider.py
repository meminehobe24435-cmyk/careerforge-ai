"""Tests for the deterministic heuristic provider.

This provider is the reason the project is reviewable and demoable with no API
key, so its behaviour is pinned by tests in both directions: it must produce
useful output on realistic material, and it must *refuse* to accept claims the
evidence does not support.
"""

from __future__ import annotations

import pytest

from careerforge_ai.providers.base import ChatMessage, ChatRole
from careerforge_ai.providers.heuristic import (
    HEURISTIC_HANDLERS,
    HeuristicProvider,
    heuristic_embedding,
)
from careerforge_ai.schemas.claim import ClaimLLMVerdict
from careerforge_ai.schemas.common import DegradationReason, DifficultyLevel
from careerforge_ai.schemas.interview import ExtractedQuestion
from careerforge_ai.schemas.job import ExtractedJD
from careerforge_ai.schemas.profile import ExtractedProfile


@pytest.fixture
def provider() -> HeuristicProvider:
    return HeuristicProvider()


class TestCapabilities:
    def test_declares_itself_deterministic_and_keyless(self, provider: HeuristicProvider) -> None:
        caps = provider.capabilities
        assert caps.requires_api_key is False
        assert caps.deterministic is True
        assert caps.supports_streaming is True

    def test_name(self, provider: HeuristicProvider) -> None:
        assert provider.name == "heuristic"


class TestChat:
    async def test_marks_results_as_degraded(self, provider: HeuristicProvider) -> None:
        result = await provider.chat([ChatMessage(role=ChatRole.USER, content="hello")])
        # Honesty requirement: nothing served without a model may pose as a model result.
        assert result.degraded is True
        assert result.degradation_reason is DegradationReason.NO_API_KEY
        assert result.cost.usd == 0.0

    async def test_reports_estimated_tokens(self, provider: HeuristicProvider) -> None:
        result = await provider.chat([ChatMessage(role=ChatRole.USER, content="分析这个 JD" * 20)])
        assert result.tokens.total_tokens > 0
        assert result.tokens.estimated is True

    async def test_stream_ends_with_a_done_chunk(self, provider: HeuristicProvider) -> None:
        chunks = [
            chunk
            async for chunk in provider.stream([ChatMessage(role=ChatRole.USER, content="hi")])
        ]
        assert chunks
        assert chunks[-1].done is True
        assert (
            "".join(chunk.delta for chunk in chunks)
            == (await provider.chat([ChatMessage(role=ChatRole.USER, content="hi")])).content
        )


class TestEmbeddings:
    async def test_is_deterministic(self, provider: HeuristicProvider) -> None:
        first = await provider.embed(["基于 STM32 的电机控制"])
        second = await provider.embed(["基于 STM32 的电机控制"])
        assert first.vectors == second.vectors

    async def test_vectors_are_normalised(self) -> None:
        vector = heuristic_embedding("STM32 FreeRTOS 电机控制", dim=128)
        norm = sum(value * value for value in vector) ** 0.5
        assert norm == pytest.approx(1.0, abs=1e-6)
        assert len(vector) == 128

    def test_similar_text_scores_higher_than_unrelated(self) -> None:
        def cosine(left: list[float], right: list[float]) -> float:
            return sum(a * b for a, b in zip(left, right, strict=True))

        query = heuristic_embedding("FreeRTOS 任务调度 优先级")
        near = heuristic_embedding("FreeRTOS 中任务调度与优先级反转")
        far = heuristic_embedding("React 前端组件设计")
        assert cosine(query, near) > cosine(query, far)

    def test_empty_text_does_not_crash(self) -> None:
        assert len(heuristic_embedding("", dim=32)) == 32


class TestJDExtraction:
    async def test_extracts_structure_from_chinese_jd(
        self, provider: HeuristicProvider, embedded_jd_text: str
    ) -> None:
        result = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content=embedded_jd_text)],
            ExtractedJD,
            context={"source_text": embedded_jd_text},
        )
        assert "嵌入式" in result.role
        assert result.location == "深圳"
        assert result.years_experience_min == 3.0
        assert result.education_requirement == "本科"

    async def test_classifies_skills_by_section(
        self, provider: HeuristicProvider, embedded_jd_text: str
    ) -> None:
        result = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content=embedded_jd_text)],
            ExtractedJD,
            context={"source_text": embedded_jd_text},
        )
        required = {skill.name for skill in result.required_skills}
        bonus = {skill.name for skill in result.bonus_skills}

        assert {"STM32", "FreeRTOS", "C"} <= required
        # "加分项：了解 AUTOSAR…" must not be promoted to a hard requirement.
        assert "AUTOSAR" in bonus
        assert "AUTOSAR" not in required

    async def test_every_skill_carries_verbatim_jd_evidence(
        self, provider: HeuristicProvider, embedded_jd_text: str
    ) -> None:
        result = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content=embedded_jd_text)],
            ExtractedJD,
            context={"source_text": embedded_jd_text},
        )
        assert result.required_skills
        for skill in result.required_skills:
            assert skill.evidence
            assert skill.evidence in embedded_jd_text

    async def test_does_not_invent_a_company_name(
        self, provider: HeuristicProvider, embedded_jd_text: str
    ) -> None:
        # No explicit "公司:" label in the source, so the field must stay empty
        # rather than guess. This is the behaviour the whole schema is built for.
        result = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content=embedded_jd_text)],
            ExtractedJD,
            context={"source_text": embedded_jd_text},
        )
        assert result.company is None

    async def test_english_jd(self, provider: HeuristicProvider, hr_jd_text: str) -> None:
        result = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content=hr_jd_text)],
            ExtractedJD,
            context={"source_text": hr_jd_text},
        )
        required = {skill.name for skill in result.required_skills}
        assert {"Python", "FastAPI", "SQL", "PostgreSQL", "Docker"} <= required


class TestClaimValidation:
    async def test_rejects_a_quantified_claim_with_no_numeric_evidence(
        self, provider: HeuristicProvider
    ) -> None:
        verdict = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content="优化系统性能，提升 70%")],
            ClaimLLMVerdict,
            context={
                "source_text": "优化系统性能，提升 70%",
                "evidence": [
                    {"title": "README.md", "snippet": "重构控制回路，降低单周期计算开销。"}
                ],
            },
        )
        assert verdict.supported is False
        assert any("70%" in part for part in verdict.unsupported_parts)

    async def test_accepts_a_claim_the_evidence_supports(self, provider: HeuristicProvider) -> None:
        verdict = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content="基于 FreeRTOS 开发多任务实时控制系统")],
            ClaimLLMVerdict,
            context={
                "source_text": "基于 FreeRTOS 开发多任务实时控制系统",
                "evidence": [
                    {
                        "title": "freertos.c",
                        "snippet": "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分并实时调度。",
                    }
                ],
            },
        )
        assert verdict.supported is True

    async def test_offers_a_safer_formulation_when_a_number_is_dropped(
        self, provider: HeuristicProvider
    ) -> None:
        verdict = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content="优化算法性能提升 70%")],
            ClaimLLMVerdict,
            context={
                "source_text": "优化算法性能提升 70%",
                "evidence": [{"title": "notes.md", "snippet": "优化算法性能。"}],
            },
        )
        assert verdict.safer_formulation
        assert "70%" not in verdict.safer_formulation

    async def test_no_evidence_means_unsupported(self, provider: HeuristicProvider) -> None:
        verdict = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content="熟练使用 Redis 与 Kafka 构建高并发架构")],
            ClaimLLMVerdict,
            context={"source_text": "熟练使用 Redis 与 Kafka 构建高并发架构", "evidence": []},
        )
        assert verdict.supported is False


class TestProfileExtraction:
    async def test_extracts_projects_and_skills(self, provider: HeuristicProvider) -> None:
        text = (
            "教育经历\n某某大学 电子信息工程 本科 2019-2023\n"
            "实习经历\n某某科技 嵌入式软件实习生 2023.07-2023.12 使用 STM32 开发电机控制固件\n"
            "项目经历\nBalance Robot 基于 STM32 与 FreeRTOS 的两轮自平衡小车\n"
            "专业技能\nC/C++、Python、STM32、FreeRTOS、Git\n"
        )
        result = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content=text)],
            ExtractedProfile,
            context={"source_text": text},
        )
        assert result.educations
        assert result.experiences
        assert result.projects
        assert "STM32" in result.skills
        # Must not fabricate a summary or a years-of-experience figure.
        assert result.years_experience is None


class TestInterviewHandlers:
    async def test_question_escalates_with_level(self, provider: HeuristicProvider) -> None:
        concept = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content="")],
            ExtractedQuestion,
            context={"topic": "free_rtos", "level": 1, "mode": "technical"},
        )
        debugging = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content="")],
            ExtractedQuestion,
            context={"topic": "free_rtos", "level": 3, "mode": "technical"},
        )
        assert concept.level is DifficultyLevel.CONCEPT
        assert debugging.level is DifficultyLevel.DEBUGGING
        assert concept.question != debugging.question

    async def test_hr_mode_uses_hr_questions(self, provider: HeuristicProvider) -> None:
        question = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content="")],
            ExtractedQuestion,
            context={"mode": "hr", "asked_count": 0},
        )
        assert question.topic == "hr"


class TestGenericSynthesiser:
    async def test_unknown_schema_still_produces_valid_output(
        self, provider: HeuristicProvider
    ) -> None:
        """No handler exists for this schema, so the generic path must cope.

        The fallback returns an empty-but-valid object on purpose: guessing
        content in a product about verifiable evidence would defeat the point.
        """
        from pydantic import Field

        from careerforge_ai.schemas.common import StrictModel

        class SomethingNew(StrictModel):
            title: str = Field(description="a title")
            items: list[str] = Field(default_factory=list)
            score: float = Field(default=0.0)

        result = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content="whatever")], SomethingNew
        )
        assert isinstance(result, SomethingNew)
        assert result.title == ""
        assert result.items == []


class TestHandlerRegistry:
    def test_registry_covers_the_core_schemas(self) -> None:
        for name in (
            "ExtractedJD",
            "ClaimLLMVerdict",
            "ExtractedProfile",
            "ExtractedQuestion",
            "ExtractedTurnEvaluation",
            "ExtractedLearningPlan",
            "ExtractedProjectIntelligence",
        ):
            assert name in HEURISTIC_HANDLERS, name
