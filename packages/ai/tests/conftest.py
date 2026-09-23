"""Shared fixtures for the AI core test suite.

The fixtures deliberately mirror real material (a Chinese embedded JD, a
candidate with a mix of evidenced and merely-claimed skills) because the bugs
that matter in this codebase show up on realistic input, not on ``"foo"``.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from careerforge_ai.graph import build_evidence_graph
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.common import (
    EvidenceKind,
    EvidenceStrength,
    RequirementLevel,
    SkillCategory,
    SkillLevel,
    SourceAuthority,
    utcnow,
)
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator
from careerforge_ai.schemas.job import JDAnalysis, JDSkill
from careerforge_ai.schemas.profile import (
    Achievement,
    CandidateProfile,
    Education,
    Experience,
    ProfileSkill,
    Project,
    SkillRef,
)

EMBEDDED_JD_TEXT = """某科技有限公司
嵌入式软件工程师
工作地点：深圳
薪资：15k-25k

岗位职责：
1. 负责嵌入式软件的设计、开发与调试；
2. 负责电机控制算法的实现与性能优化。

任职要求：
1. 本科及以上学历，3 年嵌入式开发经验；
2. 熟悉 STM32、FreeRTOS，掌握 C 语言；
3. 熟悉 CAN、SPI、I2C 等通信协议。

加分项：了解 AUTOSAR 或 Linux 驱动开发。
"""

HR_JD_TEXT = """We are hiring a Backend Engineer.

Requirements:
- 3+ years of experience with Python and FastAPI
- Strong SQL skills and experience with PostgreSQL
- Experience with Docker and CI/CD pipelines

Nice to have:
- Exposure to Kubernetes
- Familiar with Redis
"""


@pytest.fixture
def embedded_jd_text() -> str:
    return EMBEDDED_JD_TEXT


@pytest.fixture
def hr_jd_text() -> str:
    return HR_JD_TEXT


def _skill(
    canonical_id: str,
    display_name: str,
    category: SkillCategory,
    level: SkillLevel,
    *,
    evidence_count: int = 0,
    evidence_score: float = 0.0,
) -> ProfileSkill:
    return ProfileSkill(
        skill=SkillRef(canonical_id=canonical_id, display_name=display_name, category=category),
        level=level,
        evidence_count=evidence_count,
        evidence_score=evidence_score,
    )


@pytest.fixture
def candidate_profile() -> CandidateProfile:
    """A realistic candidate: three well-evidenced skills, one unproven claim."""
    return CandidateProfile(
        slug="alex",
        headline="Embedded & AI Application Engineer",
        summary=(
            "电子信息工程本科，做过两轮自平衡机器人与无人机控制链路，"
            "熟悉 STM32 平台的实时控制与通信调试。"
        ),
        location="深圳",
        github_username="alexchen",
        target_roles=["Embedded Engineer", "AI Application Engineer"],
        years_experience=1.0,
        educations=[
            Education(
                school="某某大学",
                degree="Bachelor of Engineering",
                major="电子信息工程",
                evidence_strength=EvidenceStrength.MEDIUM,
            )
        ],
        experiences=[
            Experience(
                company="某某科技",
                title="嵌入式软件实习生",
                kind="internship",
                description="使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。",
                highlights=["完成 PID 参数整定，控制周期稳定在 1kHz"],
                evidence_strength=EvidenceStrength.MEDIUM,
            )
        ],
        projects=[
            Project(
                name="Balance Robot",
                role="嵌入式负责人",
                summary="基于 STM32 的两轮自平衡小车",
                description="使用 FreeRTOS 划分任务，PID 控制电机，UART DMA 回传数据。",
                tech_stack=["STM32", "FreeRTOS", "PID", "UART", "DMA"],
                evidence_strength=EvidenceStrength.HIGH,
            )
        ],
        achievements=[
            Achievement(
                kind="competition",
                title="全国大学生电子设计竞赛省一等奖",
                issuer="教育部",
                evidence_strength=EvidenceStrength.MEDIUM,
            )
        ],
        skills=[
            _skill(
                "stm32",
                "STM32",
                SkillCategory.EMBEDDED,
                SkillLevel.STRONG,
                evidence_count=5,
                evidence_score=0.95,
            ),
            _skill(
                "free_rtos",
                "FreeRTOS",
                SkillCategory.EMBEDDED,
                SkillLevel.STRONG,
                evidence_count=3,
                evidence_score=0.90,
            ),
            _skill(
                "c",
                "C",
                SkillCategory.LANGUAGE,
                SkillLevel.STRONG,
                evidence_count=4,
                evidence_score=0.88,
            ),
            # Claimed but with no evidence behind it — the case the product exists to expose.
            _skill(
                "python", "Python", SkillCategory.LANGUAGE, SkillLevel.MODERATE, evidence_count=0
            ),
        ],
    )


@pytest.fixture
def embedding_jd() -> JDAnalysis:
    """A job with met, unproven, missing and genuinely-unknown requirements."""

    def skill(canonical_id: str, raw: str, requirement: RequirementLevel) -> JDSkill:
        return JDSkill(
            canonical_id=canonical_id, raw_text=raw, requirement=requirement, jd_evidence=f"…{raw}…"
        )

    return JDAnalysis(
        company="某科技",
        role="嵌入式软件工程师",
        location="深圳",
        education_requirement="本科",
        years_experience_min=1.0,
        required_skills=[
            skill("stm32", "STM32", RequirementLevel.REQUIRED),
            skill("free_rtos", "FreeRTOS", RequirementLevel.REQUIRED),
            skill("c", "C", RequirementLevel.REQUIRED),
            skill("can", "CAN", RequirementLevel.REQUIRED),
            skill("kubernetes", "Kubernetes", RequirementLevel.REQUIRED),
        ],
        preferred_skills=[skill("python", "Python", RequirementLevel.PREFERRED)],
        bonus_skills=[skill("autosar", "AUTOSAR", RequirementLevel.BONUS)],
        parse_confidence=0.9,
    )


@pytest.fixture
def fixture_evidence() -> EvidenceItem:
    return EvidenceItem(
        kind="repo_file",
        title="motor_control.c",
        snippet="void motor_control_task(void *args) { pid_update(&pid, encoder_read()); }",
        locator=EvidenceLocator(path="Core/Src/motor_control.c", line=42),
        source_authority=SourceAuthority.CODE_OR_COMMIT,
        confidence=0.95,
        occurred_at=utcnow() - timedelta(days=30),
    )


# ── interview fixtures ──────────────────────────────────────────────────────
# Shared by ``test_interview_agent`` and ``test_interview_signals``. They live in
# conftest because a fixture copied into two modules drifts, and a drifted fixture is a
# test that quietly stops testing the same thing.
#
# The ``iv_`` prefix is load-bearing: eight other modules define fixtures named
# ``executor`` / ``profile`` / ``job`` / ``graph`` with *different* data, so generic
# names here would let a module silently satisfy a missing fixture with the wrong input.
# The names are also kept short on purpose — the four of them travel together through
# every signature and call in the two interview modules, and a longer prefix pushes
# those call sites past the column limit, which the formatter answers by wrapping each
# one over four lines.


@pytest.fixture
def iv_exec() -> WorkflowExecutor:
    return WorkflowExecutor(
        provider=HeuristicProvider(),
        prompts=load_prompt_registry(),
        settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
    )


@pytest.fixture
def iv_profile() -> CandidateProfile:
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
                evidence_count=2,
            ),
            ProfileSkill(
                skill=SkillRef(
                    canonical_id="free_rtos",
                    display_name="FreeRTOS",
                    category=SkillCategory.EMBEDDED,
                ),
                level=SkillLevel.STRONG,
                evidence_count=2,
            ),
        ],
    )


@pytest.fixture
def iv_job() -> JDAnalysis:
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
        required_skills=[
            required("free_rtos", "FreeRTOS"),
            required("stm32", "STM32"),
            # Required but unevidenced, so the plan must flag it as a gap to probe.
            required("can", "CAN"),
        ],
    )


@pytest.fixture
def iv_graph(iv_profile: CandidateProfile):
    return build_evidence_graph(
        profile=iv_profile,
        evidence=[
            EvidenceItem(
                kind=EvidenceKind.REPO_FILE,
                title="freertos.c",
                snippet="基于 FreeRTOS 的任务划分与优先级配置，任务间通过队列通信，共享资源用互斥量保护。",
                locator=EvidenceLocator(path="Core/Src/freertos.c", line=18),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                confidence=0.0,
                occurred_at=utcnow(),
            ),
            EvidenceItem(
                kind=EvidenceKind.REPO_FILE,
                title="motor_control.c",
                snippet="在 STM32 上实现 PID 电机闭环控制。",
                locator=EvidenceLocator(path="Core/Src/motor_control.c", line=42),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                confidence=0.0,
                occurred_at=utcnow(),
            ),
        ],
    )
