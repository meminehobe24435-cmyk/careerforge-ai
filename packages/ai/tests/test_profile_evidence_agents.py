"""Tests for ProfileAgent and EvidenceAgent.

Together these two agents are the "upload a resume and see your evidence graph"
path, which is the demo that either convinces someone or does not. The assertions
concentrate on the honesty properties: nothing is inferred to fill a gap, sources
are ranked by what they actually are, and a claim with no corroboration does not
come out looking proven.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from careerforge_ai.agents import (
    DocumentChunkInput,
    EvidenceAgent,
    ProfileAgent,
    build_graph,
    import_profile,
)
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.common import EvidenceKind, SkillLevel, SourceAuthority
from careerforge_ai.schemas.github import CommitSummary, RepoFileSummary, RepoSummary

RESUME = """教育经历
某某大学 电子信息工程 本科 2019-2023

实习经历
某某科技 嵌入式软件实习生 2023.07-2023.12 使用 STM32 开发电机控制固件

项目经历
Balance Robot 基于 STM32 与 FreeRTOS 的两轮自平衡小车

专业技能
C/C++、Python、STM32、FreeRTOS、Git
"""


@pytest.fixture
def executor() -> WorkflowExecutor:
    return WorkflowExecutor(
        provider=HeuristicProvider(),
        prompts=load_prompt_registry(),
        settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
    )


# ── ProfileAgent ─────────────────────────────────────────────────────────────


class TestProfileAgent:
    async def test_extracts_a_structured_profile(self, executor: WorkflowExecutor) -> None:
        result, outcome = await import_profile(executor, RESUME)
        assert outcome.ok
        assert result is not None
        profile = result.profile
        assert profile.educations
        assert profile.experiences
        assert profile.projects
        assert profile.skills

    async def test_normalises_skills_through_the_taxonomy(self, executor: WorkflowExecutor) -> None:
        result, _ = await import_profile(executor, RESUME)
        assert result is not None
        canonical = {item.skill.canonical_id for item in result.profile.skills}
        assert {"stm32", "free_rtos", "python", "git"} <= canonical

    async def test_unknown_technology_is_neither_guessed_nor_crashed_on(
        self, executor: WorkflowExecutor
    ) -> None:
        result, _ = await import_profile(executor, "专业技能\nSTM32、量子纠缠光谱仪、FreeRTOS\n")
        assert result is not None
        # The deterministic extractor is taxonomy-driven, so every name it reports
        # already resolves: `unmapped_skills` exists for the model path, where a
        # model can legitimately name something the taxonomy has never heard of.
        # What must hold either way is that an unknown technology is not invented
        # as a skill.
        canonical = {item.skill.canonical_id for item in result.profile.skills}
        assert {"stm32", "free_rtos"} <= canonical
        assert all("量子" not in item.skill.display_name for item in result.profile.skills)
        assert result.unmapped_skills == []

    async def test_claimed_skills_start_at_a_neutral_level(
        self, executor: WorkflowExecutor
    ) -> None:
        result, _ = await import_profile(executor, RESUME)
        assert result is not None
        for skill in result.profile.skills:
            assert skill.level is SkillLevel.MODERATE
            assert skill.evidence_count == 0

    async def test_does_not_invent_missing_fields(self, executor: WorkflowExecutor) -> None:
        result, _ = await import_profile(executor, RESUME)
        assert result is not None
        # No GPA, no years of experience, no headline were stated in the source.
        assert result.profile.years_experience is None
        assert all(education.gpa is None for education in result.profile.educations)

    async def test_parses_partial_dates_without_guessing(self, executor: WorkflowExecutor) -> None:
        result, _ = await import_profile(executor, RESUME)
        assert result is not None
        education = result.profile.educations[0]
        assert education.start_date is not None
        assert education.start_date.year == 2019

    async def test_empty_document_is_reported_not_silently_accepted(
        self, executor: WorkflowExecutor
    ) -> None:
        result, outcome = await import_profile(executor, "   ")
        assert result is not None
        assert result.warnings
        assert any("未能" in warning for warning in result.warnings)
        assert outcome.warnings

    async def test_trace_names_every_step(self, executor: WorkflowExecutor) -> None:
        _, outcome = await import_profile(executor, RESUME)
        assert [step.name for step in outcome.record.steps] == [
            "clean",
            "extract",
            "normalise",
            "assemble",
        ]

    async def test_agent_exposes_its_workflow(self) -> None:
        workflow = ProfileAgent().workflow()
        assert workflow.name == "profile_ingest"
        assert workflow.agent == "profile"


# ── EvidenceAgent ────────────────────────────────────────────────────────────


@pytest.fixture
def repository() -> tuple[RepoSummary, list[RepoFileSummary], list[CommitSummary]]:
    repo = RepoSummary(
        full_name="alexchen/stm32-balance-car",
        name="stm32-balance-car",
        owner="alexchen",
        html_url="https://github.com/alexchen/stm32-balance-car",
        default_branch="main",
        readme_text="基于 STM32 与 FreeRTOS 的两轮自平衡小车，包含 PID 电机控制。",
        pushed_at=datetime(2025, 6, 1, tzinfo=UTC),
    )
    files = [
        RepoFileSummary(
            path="Core/Src/motor_control.c",
            language="C",
            is_significant=True,
            significance_reason="核心控制逻辑",
            content_excerpt="void motor_control_task(void *args) { pid_update(&pid, encoder_read()); }",
        ),
        RepoFileSummary(path="docs/photo.png", is_significant=False),
    ]
    commits = [
        CommitSummary(
            sha="a1b2c3d4e5f6",
            message="feat(freertos): 任务划分与优先级配置",
            committed_at=datetime(2025, 5, 20, tzinfo=UTC),
            files_changed=3,
            is_significant=True,
            url="https://github.com/alexchen/stm32-balance-car/commit/a1b2c3d4e5f6",
        ),
        CommitSummary(sha="deadbee", message="fix typo", is_significant=False),
    ]
    return repo, files, commits


class TestEvidenceAgent:
    async def test_builds_evidence_from_a_repository(
        self, executor: WorkflowExecutor, repository
    ) -> None:
        repo, files, commits = repository
        result, outcome = await build_graph(
            executor,
            profile=_empty_profile(),
            repositories=[(repo, files, commits)],
        )
        assert outcome.ok
        assert result is not None
        kinds = {item.kind for item in result.evidence}
        assert EvidenceKind.REPO_FILE in kinds
        assert EvidenceKind.COMMIT in kinds
        assert EvidenceKind.README in kinds

    async def test_insignificant_files_are_not_ingested(
        self, executor: WorkflowExecutor, repository
    ) -> None:
        repo, files, commits = repository
        result, _ = await build_graph(
            executor, profile=_empty_profile(), repositories=[(repo, files, commits)]
        )
        assert result is not None
        titles = {item.title for item in result.evidence}
        assert "Core/Src/motor_control.c" in titles
        assert "docs/photo.png" not in titles

    async def test_code_outranks_documents_in_authority(
        self, executor: WorkflowExecutor, repository
    ) -> None:
        repo, files, commits = repository
        result, _ = await build_graph(
            executor,
            profile=_empty_profile(),
            repositories=[(repo, files, commits)],
            document_chunks=[
                DocumentChunkInput(document_id=uuid4(), chunk_index=0, content="简历里写的自我介绍")
            ],
        )
        assert result is not None
        by_kind = {item.kind: item for item in result.evidence}
        assert (
            by_kind[EvidenceKind.REPO_FILE].confidence
            > by_kind[EvidenceKind.DOCUMENT_CHUNK].confidence
        )

    async def test_self_reports_carry_the_weakest_counting_authority(
        self, executor: WorkflowExecutor
    ) -> None:
        profile = _profile_with_experience()
        result, _ = await build_graph(executor, profile=profile)
        assert result is not None
        experience = next(item for item in result.evidence if item.kind is EvidenceKind.EXPERIENCE)
        assert experience.source_authority is SourceAuthority.UPLOADED_DOCUMENT
        assert experience.confidence < 0.9

    async def test_evidence_links_to_skills_found_in_its_own_text(
        self, executor: WorkflowExecutor, repository
    ) -> None:
        repo, files, commits = repository
        result, _ = await build_graph(
            executor, profile=_empty_profile(), repositories=[(repo, files, commits)]
        )
        assert result is not None
        assert "stm32" in result.skill_evidence
        assert "free_rtos" in result.skill_evidence

    async def test_corroboration_raises_skill_confidence(
        self, executor: WorkflowExecutor, repository
    ) -> None:
        repo, files, commits = repository
        code_only, _ = await build_graph(
            executor,
            profile=_empty_profile(),
            repositories=[(repo, [files[0]], [])],
        )
        both, _ = await build_graph(
            executor, profile=_empty_profile(), repositories=[(repo, files, commits)]
        )
        assert code_only is not None and both is not None
        # FreeRTOS appears in the README and in a commit subject, so adding the
        # commits gives it a second independent source group. STM32 appears only in
        # the README, and its confidence correctly does not move.
        assert both.skill_confidence["free_rtos"] > code_only.skill_confidence["free_rtos"]
        assert both.skill_corroboration["free_rtos"] >= 2
        assert both.skill_corroboration["stm32"] == 1

    async def test_no_material_is_reported_rather_than_returning_an_empty_graph(
        self, executor: WorkflowExecutor
    ) -> None:
        result, outcome = await build_graph(executor, profile=_empty_profile())
        assert result is not None
        assert result.evidence == []
        assert any("没有" in warning or "材料" in warning for warning in outcome.warnings)

    async def test_document_chunks_keep_their_locator(self, executor: WorkflowExecutor) -> None:
        chunk = DocumentChunkInput(
            document_id=uuid4(),
            chunk_index=2,
            content="使用 UART DMA 完成不定长数据接收。",
            heading_path="项目经历 > Balance Robot",
            page_no=3,
        )
        result, _ = await build_graph(executor, profile=_empty_profile(), document_chunks=[chunk])
        assert result is not None
        item = result.evidence[0]
        assert item.locator.section == "项目经历 > Balance Robot"
        assert item.locator.page == 3

    async def test_trace_names_every_step(self, executor: WorkflowExecutor) -> None:
        _, outcome = await build_graph(executor, profile=_empty_profile())
        assert [step.name for step in outcome.record.steps] == ["gather", "graph", "summarise"]

    async def test_agent_exposes_its_workflow(self) -> None:
        workflow = EvidenceAgent().workflow()
        assert workflow.name == "evidence_build"
        assert workflow.agent == "evidence"

    async def test_is_deterministic(self, executor: WorkflowExecutor, repository) -> None:
        repo, files, commits = repository
        first, _ = await build_graph(
            executor, profile=_empty_profile(), repositories=[(repo, files, commits)]
        )
        second, _ = await build_graph(
            executor, profile=_empty_profile(), repositories=[(repo, files, commits)]
        )
        assert first is not None and second is not None
        assert {node.id for node in first.nodes} == {node.id for node in second.nodes}
        assert [item.confidence for item in first.evidence] == [
            item.confidence for item in second.evidence
        ]

    async def test_dated_profile_entities_carry_a_timezone_aware_timestamp(
        self, executor: WorkflowExecutor
    ) -> None:
        """A résumé says "2023-07", so the instant is midnight UTC on the first.

        The schema wants a ``datetime``, and Pydantic will happily coerce a ``date`` to
        a *naive* midnight. Recency does not crash on that — it falls back to treating
        naive values as UTC — but the conversion then happens by accident in a place
        that cannot say why. This pins the explicit behaviour at the boundary, because
        every recency number downstream depends on it.
        """
        result, _ = await build_graph(executor, profile=_profile_with_dates())
        assert result is not None
        dated = [item for item in result.evidence if item.occurred_at is not None]
        assert dated, "a profile with dates must produce timestamped evidence"
        for item in dated:
            assert item.occurred_at.tzinfo is not None
            assert item.occurred_at == item.occurred_at.replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        years = {item.occurred_at.year for item in dated}
        assert years == {2022, 2023}


def _empty_profile():
    from careerforge_ai.schemas.profile import CandidateProfile

    return CandidateProfile(slug="alex")


def _profile_with_experience():
    from careerforge_ai.schemas.profile import CandidateProfile, Experience

    return CandidateProfile(
        slug="alex",
        experiences=[
            Experience(
                company="某科技",
                title="嵌入式实习生",
                description="使用 STM32 与 FreeRTOS 开发电机控制固件",
            )
        ],
    )


def _profile_with_dates():
    """A profile whose entities carry the calendar dates a real résumé has."""
    from datetime import date

    from careerforge_ai.schemas.profile import (
        Achievement,
        CandidateProfile,
        Experience,
        Project,
    )

    return CandidateProfile(
        slug="alex",
        experiences=[
            Experience(
                company="某科技",
                title="嵌入式实习生",
                description="使用 STM32 开发电机控制固件",
                start_date=date(2023, 7, 1),
            )
        ],
        projects=[
            Project(name="Balance Robot", summary="两轮自平衡小车", start_date=date(2023, 3, 1))
        ],
        achievements=[
            Achievement(kind="competition", title="电赛省一等奖", awarded_on=date(2022, 10, 1))
        ],
    )
