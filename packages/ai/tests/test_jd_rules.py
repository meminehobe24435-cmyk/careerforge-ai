"""Tests for the JD section-classification rules.

The rule under test here was added because a measurement demanded it: with the
generated corpus in ``evals/datasets``, **100%** of postings that contained a
company blurb leaked a non-required technology into the required skill set.
Overstating requirements inflates every gap and every learning plan derived from
them, so this is a product-level bug, not a cosmetic one.
"""

from __future__ import annotations

from careerforge_ai.providers.heuristic.handlers_jd import (
    _in_ignored_section,
    extract_jd,
)


class TestIgnoredSections:
    def test_company_blurb_is_recognised(self) -> None:
        text = "公司简介\n我们使用 Kubernetes 与 React 构建内部平台。\n\n任职要求：\n熟悉 STM32。"
        offset = text.index("Kubernetes")
        assert _in_ignored_section(text, offset) is True

    def test_requirement_section_after_the_blurb_is_not_ignored(self) -> None:
        text = "公司简介\n我们使用 Kubernetes 构建内部平台。\n\n任职要求：\n熟悉 STM32。"
        assert _in_ignored_section(text, text.index("STM32")) is False

    def test_english_about_us_section(self) -> None:
        text = "About us\nOur internal tooling runs on Kubernetes.\n\nRequirements:\nSTM32\n"
        assert _in_ignored_section(text, text.index("Kubernetes")) is True
        assert _in_ignored_section(text, text.index("STM32")) is False

    def test_text_with_no_sections_is_never_ignored(self) -> None:
        text = "熟悉 STM32 与 FreeRTOS。"
        assert _in_ignored_section(text, text.index("STM32")) is False


class TestExtractionWithDistractors:
    def test_blurb_technology_is_not_extracted_as_a_requirement(self) -> None:
        text = (
            "某科技\n嵌入式软件工程师\n\n"
            "公司简介\n我们使用 Kubernetes 与 React 构建内部平台。\n\n"
            "任职要求：\n熟悉 STM32 与 FreeRTOS。\n"
        )
        parsed = extract_jd(text, {})
        required = {skill.name for skill in parsed.required_skills}
        assert "STM32" in required
        assert "Kubernetes" not in required
        assert "React" not in required

    def test_tech_stack_line_is_not_treated_as_a_requirement(self) -> None:
        text = "任职要求：\n熟悉 STM32。\n\n技术栈：Python、Docker、Kubernetes。\n"
        parsed = extract_jd(text, {})
        required = {skill.name for skill in parsed.required_skills}
        assert "STM32" in required
        assert "Kubernetes" not in required

    def test_a_skill_named_in_both_places_is_still_required(self) -> None:
        # Suppression must not be over-eager: a technology that appears in the
        # requirements section as well must survive.
        text = (
            "公司简介\n我们使用 Kubernetes 构建内部平台。\n\n"
            "任职要求：\n熟悉 Kubernetes 与 Docker。\n"
        )
        parsed = extract_jd(text, {})
        required = {skill.name for skill in parsed.required_skills}
        assert "Kubernetes" in required

    def test_every_extracted_skill_quotes_the_source(self) -> None:
        text = "某科技\n后端工程师\n任职要求：\n熟悉 Python 与 FastAPI，掌握 PostgreSQL。\n"
        parsed = extract_jd(text, {})
        assert parsed.required_skills
        for skill in parsed.required_skills:
            assert skill.evidence
            assert skill.evidence in text
