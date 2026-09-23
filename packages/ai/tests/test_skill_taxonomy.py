"""Tests for the deterministic skill taxonomy.

Alias handling here is load-bearing: a false positive ("C" matching inside every
word that contains the letter c) would inflate skill counts across the entire
product, and a false negative would silently drop a candidate's best evidence.
"""

from __future__ import annotations

import pytest

from careerforge_ai.parsing.skill_taxonomy import (
    SKILL_BY_ID,
    SKILLS,
    extract_skill_mentions,
    is_known_skill,
    normalize_skill,
    skill_categories,
)
from careerforge_ai.schemas.common import SkillCategory


class TestTaxonomyIntegrity:
    def test_ids_are_unique(self) -> None:
        ids = [skill.canonical_id for skill in SKILLS]
        assert len(ids) == len(set(ids))

    def test_index_matches_the_list(self) -> None:
        assert set(SKILL_BY_ID) == {skill.canonical_id for skill in SKILLS}

    def test_every_skill_has_a_display_name_and_category(self) -> None:
        for skill in SKILLS:
            assert skill.display_name.strip()
            assert isinstance(skill.category, SkillCategory)

    def test_covers_the_target_domains(self) -> None:
        categories = {skill.category for skill in SKILLS}
        for expected in (
            SkillCategory.LANGUAGE,
            SkillCategory.EMBEDDED,
            SkillCategory.BACKEND,
            SkillCategory.AI,
            SkillCategory.FRONTEND,
            SkillCategory.DEVOPS,
            SkillCategory.TOOL,
        ):
            assert expected in categories


class TestNormalisation:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("STM32", "stm32"),
            ("stm32", "stm32"),
            ("STM32F407", "stm32"),
            ("FreeRTOS", "free_rtos"),
            ("free rtos", "free_rtos"),
            ("RTOS", "free_rtos"),
            ("C++", "cplusplus"),
            ("cpp", "cplusplus"),
            ("C", "c"),
            ("Python3", "python"),
            ("TypeScript", "typescript"),
            ("CAN总线", "can"),
            ("CANopen", "can"),
            ("PID控制", "pid"),
            ("电机控制", "motor_control"),
            ("姿态解算", "sensor_fusion"),
            ("pgvector", "postgresql"),
            ("ROS2", "ros"),
            ("next.js", "nextjs"),
        ],
    )
    def test_aliases_resolve(self, text: str, expected: str) -> None:
        skill = normalize_skill(text)
        assert skill is not None, text
        assert skill.canonical_id == expected

    def test_c_does_not_match_inside_words(self) -> None:
        # The classic failure mode of a naive substring matcher.
        for text in ("cache", "concurrency", "basic", "class"):
            skill = normalize_skill(text)
            assert skill is None or skill.canonical_id != "c", text

    def test_unknown_skill_returns_none(self) -> None:
        assert normalize_skill("Quantum Flux Welding") is None

    def test_empty_input_returns_none(self) -> None:
        assert normalize_skill("") is None

    def test_is_known_skill(self) -> None:
        assert is_known_skill("FreeRTOS") is True
        assert is_known_skill("nonexistent-tech-xyz") is False


class TestMentionExtraction:
    def test_finds_multiple_skills_in_one_sentence(self) -> None:
        text = "基于 STM32 与 FreeRTOS，通过 UART DMA 与 IMU 完成姿态解算。"
        found = {skill.canonical_id for skill, _, _ in extract_skill_mentions(text)}
        assert {"stm32", "free_rtos", "uart", "dma", "imu", "sensor_fusion"} <= found

    def test_returns_offsets_in_ascending_order(self) -> None:
        text = "Python 和 STM32 和 Docker"
        offsets = [offset for _, _, offset in extract_skill_mentions(text)]
        assert offsets == sorted(offsets)

    def test_deduplicates_one_skill_mentioned_twice(self) -> None:
        text = "STM32 项目里用了 STM32 的 HAL 库，仍然是 STM32。"
        mentions = [skill.canonical_id for skill, _, _ in extract_skill_mentions(text)]
        assert mentions.count("stm32") == 1

    def test_cpp_does_not_also_report_c(self) -> None:
        found = {skill.canonical_id for skill, _, _ in extract_skill_mentions("使用 C++ 开发")}
        assert "cplusplus" in found
        assert "c" not in found

    def test_compound_phrase_reports_both_skills(self) -> None:
        # Taxonomy hygiene rule: no alias may embed another skill's canonical
        # name, otherwise the longest-match rule silently swallows the shorter
        # skill. "UART DMA" must yield both, not one.
        found = {skill.canonical_id for skill, _, _ in extract_skill_mentions("UART DMA")}
        assert found == {"uart", "dma"}

    def test_jd_shaped_text(self) -> None:
        text = (
            "岗位职责：负责嵌入式软件设计与调试。\n"
            "任职要求：熟悉 STM32、FreeRTOS，掌握 CAN 与 SPI 通信；\n"
            "加分项：了解 AUTOSAR 或 Linux 驱动开发。"
        )
        found = {skill.canonical_id for skill, _, _ in extract_skill_mentions(text)}
        # "驱动开发" resolves to the generic device-driver skill while "Linux"
        # remains a separate, independently required skill.
        assert {"stm32", "free_rtos", "can", "spi", "autosar", "linux", "device_driver"} <= found

    def test_empty_text_yields_nothing(self) -> None:
        assert extract_skill_mentions("") == []


class TestCategoryLookup:
    def test_maps_ids_to_categories(self) -> None:
        categories = skill_categories(["stm32", "python", "docker"])
        assert categories["stm32"] is SkillCategory.EMBEDDED
        assert categories["python"] is SkillCategory.LANGUAGE
        assert categories["docker"] is SkillCategory.DEVOPS

    def test_unknown_ids_are_skipped(self) -> None:
        assert skill_categories(["not_a_skill"]) == {}
