"""Tests for PII scanning and the public Recruiter View.

The PII patterns are tested against the two failure modes that matter: missing a
real identifier, and corrupting legitimate content. Both directions have examples,
because an over-broad redactor is as damaging as a leaky one.
"""

from __future__ import annotations

import pytest

from careerforge_ai.agents import RecruiterAgent, publish_profile
from careerforge_ai.graph import build_evidence_graph
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.parsing.pii import (
    PiiKind,
    contains_pii,
    mask_value,
    redact_pii,
    scan_pii,
)
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.common import (
    EvidenceKind,
    SkillCategory,
    SkillLevel,
    SourceAuthority,
    utcnow,
)
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator
from careerforge_ai.schemas.profile import (
    CandidateProfile,
    ProfileSkill,
    Project,
    SkillRef,
)
from careerforge_ai.schemas.public import PublicSectionVisibility

EMAIL = "zhang.san@example.com"
PHONE = "13812345678"
ID_CARD = "11010519491231002X"


@pytest.fixture
def executor() -> WorkflowExecutor:
    return WorkflowExecutor(
        provider=HeuristicProvider(),
        prompts=load_prompt_registry(),
        settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
    )


# ── PII ──────────────────────────────────────────────────────────────────────


class TestPiiDetection:
    def test_finds_an_email(self) -> None:
        findings = scan_pii(f"联系方式：{EMAIL}")
        assert len(findings) == 1
        assert findings[0].kind is PiiKind.EMAIL
        assert findings[0].value == EMAIL

    def test_finds_a_mainland_mobile_number(self) -> None:
        findings = scan_pii(f"电话 {PHONE}")
        assert any(finding.kind is PiiKind.PHONE_CN for finding in findings)

    def test_finds_a_national_id_once(self) -> None:
        findings = scan_pii(f"身份证 {ID_CARD}")
        kinds = [finding.kind for finding in findings]
        assert PiiKind.ID_CARD_CN in kinds
        # An 18-digit ID must not also be reported as a bank card.
        assert PiiKind.BANK_CARD not in kinds

    def test_finds_a_grouped_bank_card(self) -> None:
        findings = scan_pii("卡号 6222 0212 3456 7890")
        assert any(finding.kind is PiiKind.BANK_CARD for finding in findings)

    def test_empty_text(self) -> None:
        assert scan_pii("") == []

    def test_no_findings_in_ordinary_text(self) -> None:
        text = "基于 STM32 与 FreeRTOS 完成电机控制，控制周期 1kHz。"
        assert scan_pii(text) == []
        assert contains_pii(text) is False

    def test_a_commit_sha_is_not_pii(self) -> None:
        # 40 hex characters, and the bank-card pattern requires digits only.
        assert not any(
            finding.kind is PiiKind.BANK_CARD
            for finding in scan_pii("commit a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0")
        )

    def test_a_version_number_is_not_a_phone(self) -> None:
        assert scan_pii("版本 1.2.3456") == []

    def test_a_short_number_is_not_a_phone(self) -> None:
        assert scan_pii("周期 1000ms") == []


class TestPiiRedaction:
    def test_redacts_every_identifier(self) -> None:
        text = f"邮箱 {EMAIL}，电话 {PHONE}"
        redacted, findings = redact_pii(text)
        assert EMAIL not in redacted
        assert PHONE not in redacted
        assert "已脱敏" in redacted
        assert len(findings) == 2

    def test_redaction_preserves_surrounding_text(self) -> None:
        redacted, _ = redact_pii(f"联系 {EMAIL} 获取更多信息")
        assert redacted.startswith("联系 ")
        assert redacted.endswith(" 获取更多信息")

    def test_text_without_pii_is_returned_unchanged(self) -> None:
        text = "使用 STM32 完成电机控制。"
        redacted, findings = redact_pii(text)
        assert redacted == text
        assert findings == []

    def test_mask_keeps_a_recognisable_prefix(self) -> None:
        masked = mask_value(EMAIL, kind=PiiKind.EMAIL)
        assert masked.startswith("zh")
        assert "***" in masked
        assert masked.endswith("@example.com")

    def test_short_values_are_fully_masked(self) -> None:
        assert mask_value("12345") == "*****"


# ── RecruiterAgent ───────────────────────────────────────────────────────────


@pytest.fixture
def profile() -> CandidateProfile:
    return CandidateProfile(
        slug="alex",
        headline="Embedded & AI Application Engineer",
        summary="电子信息工程本科，做过两轮自平衡机器人与无人机控制链路。",
        location="深圳",
        github_username="alexchen",
        website="https://alex.example.com",
        target_roles=["Embedded Engineer", "AI Application Engineer"],
        projects=[
            Project(
                name="Balance Robot",
                role="嵌入式负责人",
                summary="基于 STM32 的两轮自平衡小车，联系邮箱 leak@example.com",
                tech_stack=["STM32", "FreeRTOS", "PID"],
                links={"github": "https://github.com/alexchen/stm32-balance-car"},
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
                evidence_count=0,
            ),
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
                snippet="基于 STM32 的 PID 电机闭环控制实现。",
                locator=EvidenceLocator(
                    path="Core/Src/motor_control.c",
                    line=42,
                    url="https://github.com/alexchen/stm32-balance-car/blob/main/Core/Src/motor_control.c#L42",
                ),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                confidence=0.0,
                occurred_at=utcnow(),
            )
        ],
    )


class TestPublicProfile:
    async def test_builds_a_payload(self, executor: WorkflowExecutor, profile, graph) -> None:
        result, outcome = await publish_profile(executor, profile=profile, graph=graph)
        assert outcome.ok
        assert result is not None
        assert result.slug == "alex"
        assert result.skills
        assert result.projects

    async def test_skills_carry_evidence_links(
        self, executor: WorkflowExecutor, profile, graph
    ) -> None:
        result, _ = await publish_profile(executor, profile=profile, graph=graph)
        assert result is not None
        stm32 = next(skill for skill in result.skills if skill.canonical_id == "stm32")
        assert stm32.evidence
        assert stm32.evidence[0].url
        assert stm32.confidence > 0

    async def test_unbacked_skills_are_still_shown_but_not_claimed_as_backed(
        self, executor: WorkflowExecutor, profile, graph
    ) -> None:
        result, _ = await publish_profile(executor, profile=profile, graph=graph)
        assert result is not None
        free_rtos = next(skill for skill in result.skills if skill.canonical_id == "free_rtos")
        assert free_rtos.is_backed is False
        assert free_rtos.confidence == 0.0

    async def test_evidence_coverage_is_reported(
        self, executor: WorkflowExecutor, profile, graph
    ) -> None:
        result, _ = await publish_profile(executor, profile=profile, graph=graph)
        assert result is not None
        # One of the two declared skills has evidence.
        assert result.evidence_coverage == pytest.approx(0.5, abs=0.01)

    async def test_incidental_pii_is_redacted(
        self, executor: WorkflowExecutor, profile, graph
    ) -> None:
        result, outcome = await publish_profile(executor, profile=profile, graph=graph)
        assert result is not None
        assert "leak@example.com" not in result.projects[0].summary
        assert result.redactions
        assert any("脱敏" in warning for warning in outcome.warnings)

    async def test_contact_is_hidden_by_default(
        self, executor: WorkflowExecutor, profile, graph
    ) -> None:
        result, _ = await publish_profile(executor, profile=profile, graph=graph)
        assert result is not None
        assert result.visibility.contact is False
        assert result.contact == {}
        assert result.website_url is None
        assert result.location is None

    async def test_contact_is_published_on_opt_in(
        self, executor: WorkflowExecutor, profile, graph
    ) -> None:
        result, _ = await publish_profile(
            executor,
            profile=profile,
            graph=graph,
            visibility=PublicSectionVisibility(contact=True),
        )
        assert result is not None
        assert result.contact
        assert result.website_url == "https://alex.example.com"

    async def test_a_hidden_section_is_omitted(
        self, executor: WorkflowExecutor, profile, graph
    ) -> None:
        result, _ = await publish_profile(
            executor,
            profile=profile,
            graph=graph,
            visibility=PublicSectionVisibility(skills=False, projects=False, evidence=False),
        )
        assert result is not None
        assert result.skills == []
        assert result.projects == []

    async def test_requires_a_slug(self, executor: WorkflowExecutor, graph) -> None:
        with pytest.raises(ValueError):
            await RecruiterAgent().run(
                executor, profile=CandidateProfile(headline="No slug"), graph=graph
            )

    async def test_trace_names_every_step(self, executor: WorkflowExecutor, profile, graph) -> None:
        _, outcome = await publish_profile(executor, profile=profile, graph=graph)
        assert [step.name for step in outcome.record.steps] == [
            "gather",
            "summarise",
            "redact",
            "assemble",
        ]

    async def test_agent_exposes_its_workflow(self) -> None:
        assert RecruiterAgent().workflow().name == "recruiter_publish"

    async def test_is_deterministic(self, executor: WorkflowExecutor, profile, graph) -> None:
        first, _ = await publish_profile(executor, profile=profile, graph=graph)
        second, _ = await publish_profile(executor, profile=profile, graph=graph)
        assert first is not None and second is not None
        assert [s.canonical_id for s in first.skills] == [s.canonical_id for s in second.skills]
        assert first.evidence_coverage == second.evidence_coverage
        assert first.redactions == second.redactions
