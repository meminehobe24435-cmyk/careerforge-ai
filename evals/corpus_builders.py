"""Corpus assembly.

Turns the seeded data in :mod:`corpus_data` and :mod:`corpus_retrieval` into
labelled datasets. Pure functions of the seed: no I/O, no clock, no randomness
beyond the seeded ``random.Random`` instances. That is what makes
``generate_datasets.py --check`` a meaningful guard — if assembly were
non-deterministic the hash comparison could never pass twice.

Everything here is intentionally literal about ground truth. A JD's gold skill set
is the set of skills the generator *put in the requirements section*, and the
retrieval corpus labels relevance per query. When a metric moves, the cause is a
code change rather than a change of mind about what the labels meant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from corpus_data import (
    BLURBS_EN,
    BLURBS_ZH,
    CLAIM_SAMPLE_COUNT,
    COMPANIES_EN,
    COMPANIES_ZH,
    DISTRACTOR_RATE,
    ENGLISH_RATE,
    FAMILIES,
    JD_SAMPLE_COUNT,
    LOCATIONS_EN,
    LOCATIONS_ZH,
    MIXED_RATE,
    NO_EVIDENCE_CLAIM_TEMPLATES,
    NUMERIC_CLAIM_TEMPLATES,
    PARTIAL_CLAIM_TEMPLATES,
    SEED,
    SUPPORTED_CLAIM_TEMPLATES,
    RoleFamily,
)
from corpus_retrieval import RETRIEVAL_TOPICS

# ── JD rendering ─────────────────────────────────────────────────────────────


@dataclass
class _JDDraft:
    text: str = ""
    gold: dict[str, Any] = field(default_factory=dict)
    family: str = ""
    language: str = ""
    has_distractor: bool = False


def _join_skills(skills: list[str], language: str) -> str:
    separator = "、" if language == "zh" else ", "
    if len(skills) == 1:
        return skills[0]
    return separator.join(skills[:-1]) + (" 和 " if language == "zh" else " and ") + skills[-1]


def _pick(rng: random.Random, pool: tuple[str, ...], low: int, high: int) -> list[str]:
    count = rng.randint(low, min(high, len(pool)))
    return rng.sample(list(pool), count)


def _compose_zh(rng: random.Random, family: RoleFamily, distractors: list[str]) -> _JDDraft:
    required = _pick(rng, family.core, 3, 5)
    preferred = _pick(rng, family.preferred, 1, 3)
    bonus = _pick(rng, family.bonus, 0, 2)
    company = rng.choice(COMPANIES_ZH)
    title = rng.choice(family.titles_zh)
    location = rng.choice(LOCATIONS_ZH)
    years = rng.choice([0.0, 1.0, 2.0, 3.0, 5.0])
    degree = rng.choice(["本科", "本科", "硕士", "大专"])
    salary_low = rng.randint(10, 30)
    salary_high = salary_low + rng.randint(5, 15)

    lines: list[str] = [
        company,
        title,
        f"工作地点：{location}",
        f"薪资：{salary_low}k-{salary_high}k",
        "",
    ]

    if distractors:
        lines += [
            "公司简介",
            rng.choice(BLURBS_ZH).format(tech=_join_skills(distractors, "zh")),
            "",
        ]

    lines.append("岗位职责：")
    for index, duty in enumerate(
        rng.sample(list(family.responsibilities_zh), k=min(3, len(family.responsibilities_zh)))
    ):
        lines.append(f"{index + 1}. {duty}；")
    lines.append("")

    lines.append("任职要求：")
    lines.append(f"1. {degree}及以上学历，{years:g} 年以上相关工作经验；")
    lines.append(f"2. 熟悉 {_join_skills(required[:3], 'zh')}；")
    if len(required) > 3:
        lines.append(f"3. 掌握 {_join_skills(required[3:], 'zh')}。")
    lines.append("")

    if preferred:
        lines.append(f"优先条件：有 {_join_skills(preferred, 'zh')} 相关经验者优先。")
    if bonus:
        lines.append(f"加分项：了解 {_join_skills(bonus, 'zh')}。")

    return _JDDraft(
        text="\n".join(lines) + "\n",
        gold={
            "role": title,
            "company": company,
            "location": location,
            "education_requirement": degree,
            "years_experience_min": years,
            "required_skills": required,
            "preferred_skills": preferred,
            "bonus_skills": bonus,
            "not_required_skills": distractors,
        },
        family=family.key,
        language="zh",
        has_distractor=bool(distractors),
    )


def _compose_en(rng: random.Random, family: RoleFamily, distractors: list[str]) -> _JDDraft:
    required = _pick(rng, family.core, 3, 5)
    preferred = _pick(rng, family.preferred, 1, 3)
    bonus = _pick(rng, family.bonus, 0, 2)
    company = rng.choice(COMPANIES_EN)
    title = rng.choice(family.titles_en)
    location = rng.choice(LOCATIONS_EN)
    years = rng.choice([0.0, 2.0, 3.0, 5.0])
    degree = rng.choice(["Bachelor", "Bachelor", "Master"])

    lines: list[str] = [f"{company} — {title}", f"Location: {location}", ""]

    if distractors:
        lines += [
            "About us",
            rng.choice(BLURBS_EN).format(tech=_join_skills(distractors, "en")),
            "",
        ]

    lines.append("Responsibilities:")
    for duty in rng.sample(
        list(family.responsibilities_en), k=min(3, len(family.responsibilities_en))
    ):
        lines.append(f"- {duty}")
    lines.append("")

    lines.append("Requirements:")
    lines.append(f"- {degree}'s degree and {years:g}+ years of relevant experience")
    lines.append(f"- Hands-on experience with {_join_skills(required, 'en')}")
    lines.append("")

    if preferred:
        lines.append(f"Preferred: {_join_skills(preferred, 'en')}")
    if bonus:
        lines.append(f"Nice to have: {_join_skills(bonus, 'en')}")

    return _JDDraft(
        text="\n".join(lines) + "\n",
        gold={
            "role": title,
            "company": company,
            "location": location,
            "education_requirement": degree,
            "years_experience_min": years,
            "required_skills": required,
            "preferred_skills": preferred,
            "bonus_skills": bonus,
            "not_required_skills": distractors,
        },
        family=family.key,
        language="en",
        has_distractor=bool(distractors),
    )


def _compose_mixed(rng: random.Random, family: RoleFamily, distractors: list[str]) -> _JDDraft:
    """A Chinese posting with an English tech-stack line — extremely common."""
    required = _pick(rng, family.core, 3, 5)
    preferred = _pick(rng, family.preferred, 1, 2)
    bonus = _pick(rng, family.bonus, 0, 2)
    company = rng.choice(COMPANIES_ZH)
    title = rng.choice(family.titles_zh)
    location = rng.choice(LOCATIONS_ZH)
    years = rng.choice([1.0, 3.0])
    degree = rng.choice(["本科", "硕士"])

    lines: list[str] = [company, title, f"工作地点：{location}", ""]
    lines.append("岗位职责：")
    for index, duty in enumerate(rng.sample(list(family.responsibilities_zh), k=2)):
        lines.append(f"{index + 1}. {duty}；")
    lines.append("")
    lines.append("任职要求：")
    lines.append(f"1. {degree}及以上学历，{years:g} 年以上经验；")
    lines.append(f"2. 熟悉 {_join_skills(required, 'zh')}；")
    lines.append(
        "3. 英文技术文档阅读能力（Tech stack: " + _join_skills(distractors, "en") + "）。"
        if distractors
        else "3. 具备良好的英文技术文档阅读能力。"
    )
    lines.append("")
    if preferred:
        lines.append(f"优先条件：{_join_skills(preferred, 'en')} 经验者优先。")
    if bonus:
        lines.append(f"加分项：了解 {_join_skills(bonus, 'zh')}。")

    return _JDDraft(
        text="\n".join(lines) + "\n",
        gold={
            "role": title,
            "company": company,
            "location": location,
            "education_requirement": degree,
            "years_experience_min": years,
            "required_skills": required,
            "preferred_skills": preferred,
            "bonus_skills": bonus,
            "not_required_skills": distractors,
        },
        family=family.key,
        language="mixed",
        has_distractor=bool(distractors),
    )


def build_jd_dataset() -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    rows: list[dict[str, Any]] = []

    for index in range(JD_SAMPLE_COUNT):
        family = FAMILIES[index % len(FAMILIES)]
        roll = rng.random()
        use_distractor = roll < DISTRACTOR_RATE
        distractors = _pick(rng, family.distractors, 1, 2) if use_distractor else []

        language_roll = rng.random()
        if language_roll < MIXED_RATE:
            draft = _compose_mixed(rng, family, distractors)
        elif language_roll < MIXED_RATE + ENGLISH_RATE:
            draft = _compose_en(rng, family, distractors)
        else:
            draft = _compose_zh(rng, family, distractors)

        rows.append(
            {
                "id": f"jd-{index:04d}",
                "family": draft.family,
                "language": draft.language,
                "has_distractor": draft.has_distractor,
                "text": draft.text,
                "gold": draft.gold,
            }
        )

    return rows


# ── Claim validation dataset ─────────────────────────────────────────────────

#: Cases where the claim is fully backed by the evidence.
_SUPPORTED_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    (
        "基于 FreeRTOS 开发多任务实时控制系统",
        "freertos.c",
        "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分并周期调度，"
        "任务间通过队列通信，关键共享资源使用互斥量保护。",
    ),
    (
        "使用 STM32 HAL 库完成 UART DMA 不定长接收",
        "uart_dma.c",
        "在 STM32 上使用 HAL 库配置 UART DMA 接收，采用空闲中断加环形缓冲区的方式"
        "处理不定长数据帧，接收过程不占用 CPU 轮询。",
    ),
    (
        "实现基于编码器反馈的 PID 闭环电机控制",
        "motor_control.c",
        "通过编码器读取转速，使用 PID 控制器计算占空比并输出到电机驱动，"
        "完成闭环调速，积分项做了抗饱和处理。",
    ),
    (
        "使用 Docker Compose 编排后端服务与数据库",
        "docker-compose.yml",
        "使用 Docker Compose 编排 FastAPI 服务、PostgreSQL 与 Redis，"
        "通过 healthcheck 控制启动顺序，数据卷持久化数据库文件。",
    ),
    (
        "基于 pgvector 实现证据片段的语义检索",
        "retrieval.py",
        "使用 pgvector 存储证据向量，查询时按余弦相似度检索 Top-K 片段，"
        "并与关键词检索结果做 RRF 融合。",
    ),
    (
        "使用 pytest 编写后端单元测试与集成测试",
        "tests/test_match.py",
        "使用 pytest 覆盖匹配评分与证据验证逻辑，包含确定性断言与边界用例，"
        "集成测试基于 httpx ASGI transport 直接调用应用。",
    ),
)

#: Cases where only part of the claim is backed. Gold: partially supported.
_PARTIAL_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    (
        "基于 FreeRTOS 开发多任务实时控制系统，并完成 CAN 总线节点通信",
        "freertos.c",
        "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分并周期调度。",
    ),
    (
        "使用 STM32 完成 SPI 传感器驱动与 I2C EEPROM 读写",
        "spi_sensor.c",
        "在 STM32 上完成 SPI 传感器驱动的读写与寄存器配置。",
    ),
    (
        "设计并实现整站后端架构，负责数据库、缓存与消息队列选型",
        "notes.md",
        "负责后端服务开发与数据库表结构设计。",
    ),
)

#: Cases with a hard number that no evidence supports. Gold: unsupported.
#: These are the ones the gate must reject, so they dominate the suite.
_NUMERIC_TEMPLATES: tuple[tuple[str, str, str], ...] = (
    ("优化算法性能，提升 70%", "notes.md", "对控制回路做了重构，减少了单周期内的重复计算。"),
    ("重构后端接口，响应时间降低 3 倍", "refactor.md", "重构了接口的参数校验与数据库查询逻辑。"),
    ("支撑 10 万 QPS 的高并发架构设计", "arch.md", "参与后端服务架构讨论与接口设计。"),
    ("将系统内存占用降低 45%", "opt.md", "调整了缓冲区大小与任务栈配置。"),
    ("测试覆盖率提升至 90%", "ci.md", "补充了部分单元测试并接入 CI。"),
    ("负责的系统日均处理 500 万次请求", "ops.md", "负责线上服务的日常维护与问题排查。"),
    ("把固件启动时间从 800ms 优化到 120ms", "boot.md", "调整了外设初始化顺序，简化了启动流程。"),
    ("带领 8 人团队完成平台重构", "team.md", "参与平台重构的技术方案讨论。"),
)

#: Cases with no evidence at all. Gold: unsupported.
_NO_EVIDENCE_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("熟练使用 Redis 与 Kafka 构建高并发架构", "项目材料中未涉及任何消息队列或缓存组件。"),
    ("精通 Kubernetes 集群运维与故障排查", "候选材料中只有单机 Docker 使用记录。"),
    ("主导 AUTOSAR 架构设计与集成", "候选材料中未出现 AUTOSAR 相关内容。"),
    ("独立完成芯片级驱动开发与流片验证", "候选材料中未涉及芯片设计或流片。"),
    ("作为技术负责人管理 20 人研发团队", "候选材料中无团队管理经历。"),
)


# ── Claim validation dataset ────────────────────────────────────────────────


def build_claim_dataset() -> list[dict[str, Any]]:
    """Build claim cases with explicit gold labels.

    Labels describe *intent*, not the engine's rules: a claim is ``supported``
    because the evidence genuinely backs all of it, ``partially_supported``
    because it backs only part, and ``unsupported`` because it does not.
    """
    rng = random.Random(SEED + 1)
    rows: list[dict[str, Any]] = []
    index = 0

    def add(
        claim: str,
        evidence: list[dict[str, str]],
        gold_supported: bool,
        gold_kind: str,
        *,
        has_unsupported_number: bool = False,
    ) -> None:
        nonlocal index
        rows.append(
            {
                "id": f"claim-{index:04d}",
                "claim": claim,
                "evidence": evidence,
                "gold": {
                    "supported": gold_supported,
                    "kind": gold_kind,
                    "has_unsupported_number": has_unsupported_number,
                },
            }
        )
        index += 1

    # Repeat the core templates with light variation to reach a usable sample
    # size without inventing new semantics.
    target_per_kind = CLAIM_SAMPLE_COUNT // 4

    for _ in range(target_per_kind):
        claim, title, snippet = rng.choice(SUPPORTED_CLAIM_TEMPLATES)
        add(claim, [{"title": title, "snippet": snippet}], True, "supported")

    for _ in range(target_per_kind):
        claim, title, snippet = rng.choice(PARTIAL_CLAIM_TEMPLATES)
        add(claim, [{"title": title, "snippet": snippet}], False, "partially_supported")

    for _ in range(target_per_kind):
        claim, title, snippet = rng.choice(NUMERIC_CLAIM_TEMPLATES)
        add(
            claim,
            [{"title": title, "snippet": snippet}],
            False,
            "unsupported",
            has_unsupported_number=True,
        )

    for _ in range(CLAIM_SAMPLE_COUNT - 3 * target_per_kind):
        claim, note = rng.choice(NO_EVIDENCE_CLAIM_TEMPLATES)
        add(claim, [{"title": "resume.md", "snippet": note}], False, "unsupported")

    return rows


# ── Retrieval corpus ─────────────────────────────────────────────────────────


def build_retrieval_dataset() -> list[dict[str, Any]]:
    """Build one corpus with per-query gold relevance.

    Evidence ids are derived with ``uuid5`` from the topic and fragment index, so
    they are stable across regenerations and a Recall@5 number stays comparable
    between commits.
    """
    documents: list[dict[str, Any]] = []
    queries: list[dict[str, Any]] = []

    for topic, fragments, query_specs in RETRIEVAL_TOPICS:
        fragment_ids = [
            str(uuid5(NAMESPACE_URL, f"careerforge-eval:{topic}:{index}"))
            for index in range(len(fragments))
        ]
        for index, fragment in enumerate(fragments):
            documents.append(
                {
                    "evidence_id": fragment_ids[index],
                    "topic": topic,
                    "title": f"{topic}/evidence_{index}.md",
                    "kind": "document_chunk",
                    "text": fragment,
                }
            )
        for query, style, gold_indices in query_specs:
            queries.append(
                {
                    "query": query,
                    "topic": topic,
                    "type": style,
                    "gold_ids": [fragment_ids[index] for index in gold_indices],
                }
            )

    return [{"id": "retrieval-corpus", "documents": documents, "queries": queries}]
