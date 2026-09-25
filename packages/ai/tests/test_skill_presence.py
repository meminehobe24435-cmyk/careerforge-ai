"""The false-positive audit behind raising ``skill_not_in_graph`` from a warning to a blocker.

``docs/QUALITY.md`` §7.4 stated both the gap and the prerequisite: a technology nothing mentions
should make a claim unsupported, but **raising the severity needs a false-positive audit of the token
extractor first**, because hard-rejecting an honest claim is a worse failure than a soft verdict.

This file is that audit. It is written as a *labelled set of claims that must stay supported* —
counterexamples, in the sense that if the change had broken them, they would fail here — organised by
the extractor failure mode each one probes:

============================  ======================================  ==================
mode                          example                                 must stay
============================  ======================================  ==================
spelling variant              ``K8s`` vs ``Kubernetes``               supported
English/Chinese variant       ``实时操作系统`` vs ``FreeRTOS``          supported
the *other* party's wording   claim says ``CSS``, material says ``HTML/CSS``  supported
version / family suffix       ``C++17`` vs ``C++``, ``STM32F407`` vs ``STM32``   supported
case and spacing              ``free rtos`` vs ``FreeRTOS``            supported
technology outside the map    ``AWS Lambda``, ``RRF``                 warning, not blocker
============================  ======================================  ==================

**What the audit cannot distinguish, stated honestly.** The last row is where the rule deliberately
does not escalate, and the reason is the same for every entry in it: the claim's wording is the only
evidence available, so "the material never says it" cannot be separated from "the extractor never
recognised it". The taxonomy is the line — it is what makes ``K8s`` ⟷ ``Kubernetes`` a *known*
equivalence rather than a guess — and a technology the taxonomy has never heard of cannot be judged
by it. So those stay warnings. This test file measures where the line falls; it cannot move it, and
moving it would mean hard-rejecting claims that use an honest tool nobody has added to the vocabulary
yet.

The first three classes (and ``TestClaimsTheTaxonomyCannotJudge``) are the audit; the last two are the
rule keeping its teeth, because a blocker that fired on every sentence would be a worse failure than
the warning it replaced.
"""

from __future__ import annotations

import pytest

from careerforge_ai.agents.validator import rules_phase
from careerforge_ai.orchestrator import RunContext
from careerforge_ai.parsing.claim_rules import detect_missing_technical
from careerforge_ai.parsing.skill_mentions import (
    confirmed_absent_skills,
    presence_of,
)
from careerforge_ai.prompting.registry import PromptRegistry
from careerforge_ai.providers.heuristic import HeuristicProvider
from careerforge_ai.schemas.common import ClaimRuleCode

#: ``(claim, material, why)`` — every one of these must **not** become a blocker.
#:
#: The material is written the way a candidate's evidence really reads (a résumé line, a file
#: snippet, a commit subject), not as a list of the claim's own tokens: a test whose evidence is a
#: copy of the claim proves nothing about synonym handling.
MUST_NOT_BLOCK: tuple[tuple[str, str, str], ...] = (
    (
        "使用 K8s 完成集群的滚动升级与故障转移",
        "repo_file deploy/rollout.yaml\nKubernetes 集群的滚动升级策略与 Pod 故障转移配置。",
        "spelling variant: the claim uses the alias, the material the display name",
    ),
    (
        "基于实时操作系统实现多任务调度",
        "repo_file freertos_tasks.c\n基于 FreeRTOS 的多任务调度：创建 4 个任务，按优先级划分，"
        "共享资源用互斥量保护。",
        "English/Chinese variant: the taxonomy links 实时操作系统 and FreeRTOS to one skill",
    ),
    (
        "用 CSS 实现了看板的键盘可访问样式",
        "repo_file kanban-board.css\nHTML/CSS 看板样式：焦点环、对比度与 aria-live 状态播报。",
        "the material names the compound skill HTML/CSS, which the claim splits",
    ),
    (
        "使用 C++17 与 STM32F407 完成控制固件的重构",
        "repo_file control.cpp\n使用 C++ 与 STM32 重写控制固件，替换原有实现。",
        "version and family suffixes: C++17 ⊂ C++, STM32F407 ⊂ STM32 (both taxonomy aliases)",
    ),
    (
        "使用 free rtos 与 K8s 完成部署",
        "document_chunk ops.md\nFreeRTOS 任务划分，Kubernetes 集群部署。",
        "case and spacing variants of two skills, both present in the material",
    ),
    (
        "使用 Redis 做热点数据缓存",
        "repo_file cache.py\n使用 Redis 做热点数据缓存，设置 TTL 与淘汰策略。",
        "exact match — the control case for every other row here",
    ),
    (
        "用 PyTorch 训练了缺陷检测模型",
        "commit a1b2c3d\nfeat(model): torch 缺陷检测模型训练脚本与数据增强",
        "the material uses the shorter alias the claim does not",
    ),
    (
        "使用 pgvector 实现了证据片段语义检索",
        "repo_file vector_store.py\nPostgreSQL + pgvector 存储证据向量并做近邻检索。",
        "one skill, two names, the longer one in the material",
    ),
)

#: ``(claim, material, why)`` — these are *not* normalisable, so they stay warnings.
#:
#: Each is a real technology or a real gap whose wording the taxonomy does not know. Escalating them
#: would mean a candidate's honest use of an unmapped tool reads as fabrication.
WARNING_ONLY: tuple[tuple[str, str, str], ...] = (
    (
        "在 Azure Pipelines 上搭建了 CI 流水线",
        "repo_file azure-pipelines.yml\n构建、单元测试与部署三个阶段；触发条件与变量组定义。",
        "unmapped technology that is genuinely present — a blocker here would be a plain false positive",
    ),
    (
        "实现了 RRF 融合排序",
        "repo_file fusion.py\n把两路检索的排名按 k=60 融合后重新排序。",
        "unmapped abbreviation for an implemented mechanism",
    ),
    (
        "用 AWS Lambda 实现了服务端无服务器部署",
        "repo_file handler.py\nLambda 处理函数处理对象存储事件，冷启动用预留并发缓解。",
        "unmapped technology that is genuinely present — a blocker here would be a plain false positive",
    ),
)


def _presence(claim: str, material: str) -> object:
    return presence_of(claim, material)


def _context(claim: str, material: str) -> RunContext:
    return RunContext(
        user_id=None,
        request_id="audit",
        provider=HeuristicProvider(),
        prompts=PromptRegistry(),
        metadata={"claim": claim, "evidence_text": material},
    )


class TestClaimsThatMustNotBeBlocked:
    """The audit: an honest claim may never be refused by this rule."""

    @pytest.mark.parametrize(
        ("claim", "material", "why"), MUST_NOT_BLOCK, ids=lambda value: str(value)[:28]
    )
    def test_no_blocker_reason_is_produced(self, claim: str, material: str, why: str) -> None:
        reasons = detect_missing_technical(claim, material)
        blockers = [reason for reason in reasons if reason.severity == "blocker"]
        assert not blockers, f"{why}: the rule refused an honest claim -> {blockers}"

    @pytest.mark.parametrize(
        ("claim", "material", "why"), MUST_NOT_BLOCK, ids=lambda value: str(value)[:28]
    )
    def test_nothing_is_reported_as_confirmed_absent(
        self, claim: str, material: str, why: str
    ) -> None:
        absent = confirmed_absent_skills(claim, material)
        assert not absent, f"{why}: {absent}"

    async def test_the_rules_phase_does_not_block_them_either(self) -> None:
        """The audit has to hold where it is used, not only where it is defined."""
        for claim, material, why in MUST_NOT_BLOCK:
            rules = await rules_phase(_context(claim, material), {})
            assert rules["blocked"] is False, f"{why}: {rules['reasons']}"
            assert rules["absent_skills"] == [], why


class TestClaimsTheTaxonomyCannotJudge:
    """Unmapped technologies stay warnings — the line the audit can see but not move."""

    @pytest.mark.parametrize(
        ("claim", "material", "why"), WARNING_ONLY, ids=lambda value: str(value)[:28]
    )
    def test_severity_is_warning_not_blocker(self, claim: str, material: str, why: str) -> None:
        presence = presence_of(claim, material)
        assert presence.confirmed_absent == {}, why
        assert presence.blocked is False, why
        reasons = detect_missing_technical(claim, material)
        assert all(reason.severity == "warning" for reason in reasons), why
        assert all(reason.rule is ClaimRuleCode.SKILL_NOT_IN_GRAPH for reason in reasons)

    async def test_the_gate_still_judges_rather_than_refusing(self) -> None:
        """A warning is not a refusal: the path that produces a verdict is still reached."""
        claim, material, why = WARNING_ONLY[0]
        rules = await rules_phase(_context(claim, material), {})
        assert rules["blocked"] is False, why
        assert rules["unconfirmed_tokens"], why


class TestFabricatedTechnologiesAreStillRefused:
    """The rule kept its teeth, and it is not a hardcoded skill list."""

    @pytest.mark.parametrize(
        ("claim", "material", "absent"),
        [
            (
                "使用 Redis 与 Kafka 构建高并发消息架构",
                "repo_file cache.py\n使用 Redis 做热点数据缓存。",
                "kafka",
            ),
            (
                "使用 Kubernetes 完成集群运维与故障排查",
                "repo_file Dockerfile\n单机 Docker 构建与运行说明。",
                "kubernetes",
            ),
            (
                "主导 AUTOSAR 架构设计与集成",
                "document_chunk resume.md\n候选人材料中未出现相关平台内容。",
                "autosar",
            ),
            (
                "实现了基于 FPGA 的实时图像处理流水线",
                "repo_file image.py\n使用 Python 做离线图像处理。",
                "fpga",
            ),
            (
                "在项目中同时使用了 STM32 与 ESP32 完成双芯片通信",
                "repo_file stm32_main.c\nSTM32 主控固件：串口协议收发与状态机。",
                "esp32",
            ),
        ],
    )
    def test_a_taxonomy_known_technology_that_appears_nowhere_blocks(
        self, claim: str, material: str, absent: str
    ) -> None:
        presence = presence_of(claim, material)
        assert presence.blocked is True, claim
        assert absent in presence.confirmed_absent, presence.confirmed_absent
        reasons = detect_missing_technical(claim, material)
        assert [reason.severity for reason in reasons] == ["blocker"]

    def test_the_same_claim_becomes_supported_once_the_material_names_the_skill(self) -> None:
        """The rule is about the material, not about the sentence: change one and the verdict flips."""
        claim = "使用 Redis 与 Kafka 构建高并发消息架构"
        without = "repo_file cache.py\n使用 Redis 做热点数据缓存。"
        with_kafka = (
            "repo_file cache.py\n使用 Redis 做热点数据缓存。\n\n"
            "repo_file producer.py\nKafka 生产者把订单事件写入 topic，消费侧做幂等处理。"
        )
        assert presence_of(claim, without).blocked is True
        assert presence_of(claim, with_kafka).blocked is False
        assert detect_missing_technical(claim, with_kafka) == []

    def test_an_empty_material_is_not_treated_as_a_missing_skill(self) -> None:
        """The caller's contract supplies the material. A misconfigured caller would otherwise have
        every claim in the product refused, which is the failure mode PHASE 12 hit head-on."""
        assert presence_of("使用 Kafka 构建消息架构", "").blocked is False
        assert detect_missing_technical("使用 Kafka 构建消息架构", "") == []


class TestTheTwoHalvesStaySeparate:
    """The classification a reader (and the report) can audit: which half caused a refusal."""

    def test_a_mixed_claim_lists_the_confirmed_absence_only(self) -> None:
        presence = presence_of(
            "使用 Kafka 与 Azure Pipelines 构建流水线",
            "repo_file pipeline.yml\n流水线的构建与部署阶段定义。",
        )
        assert presence.confirmed_absent == {"kafka": "kafka"}
        assert "pipelines" in presence.unconfirmed_tokens
        assert presence.blocked is True

    def test_presence_is_empty_without_a_model_call_or_material(self) -> None:
        presence = _presence("", "")
        assert presence.any is False  # type: ignore[attr-defined]
        assert presence.blocked is False  # type: ignore[attr-defined]
