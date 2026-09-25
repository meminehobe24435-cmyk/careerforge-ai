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
    COMPANIES_EN,
    COMPANIES_ZH,
    DISTRACTOR_RATE,
    ENGLISH_RATE,
    FAMILIES,
    JD_SAMPLE_COUNT,
    LOCATIONS_EN,
    LOCATIONS_ZH,
    MIXED_RATE,
    SEED,
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
