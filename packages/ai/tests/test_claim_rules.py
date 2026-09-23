"""Tests for the deterministic claim rules.

The last test in this file is the important one: it re-derives the decision
threshold from the labelled dataset and fails if the two classes ever stop being
separable. A threshold is only meaningful if something checks that it still
separates anything — otherwise it silently becomes a number someone tuned once.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from careerforge_ai.parsing.claim_rules import build_safer_formulation, split_clauses
from careerforge_ai.providers.heuristic.handlers_claim import (
    SUPPORT_OVERLAP_THRESHOLD,
    validate_claim,
)
from careerforge_ai.providers.heuristic.text import (
    missing_technical_tokens,
    technical_tokens,
    token_overlap,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
CLAIM_DATASET = REPO_ROOT / "evals" / "datasets" / "claim_validation.jsonl"


def _evidence_text(evidence: list[dict[str, str]]) -> str:
    return "\n".join(f"{item['title']}\n{item['snippet']}" for item in evidence)


class TestTechnicalTokens:
    def test_extracts_latin_and_technical_tokens(self) -> None:
        assert technical_tokens("使用 STM32 与 FreeRTOS，配合 I2C") == {
            "stm32",
            "freertos",
            "i2c",
        }

    def test_ignores_single_characters(self) -> None:
        # "C" as a language name is two orders of magnitude more common than a
        # stray "c", but a one-letter token produces nothing but false positives.
        assert "c" not in technical_tokens("编写 C 代码")

    def test_keeps_plus_plus_and_version_suffixes(self) -> None:
        assert technical_tokens("使用 C++11 开发") == {"c++11"}

    def test_version_suffix_is_tolerated_when_matching(self) -> None:
        # "C++11" against evidence that says "C++" is not a missing technology;
        # failing this would reject the most ordinary technical phrasing there is.
        assert missing_technical_tokens("使用 C++11 开发", "使用 C++ 开发") == set()
        assert missing_technical_tokens("使用 Python3 编写脚本", "使用 Python 编写脚本") == set()

    def test_version_tolerance_does_not_hide_a_different_technology(self) -> None:
        assert missing_technical_tokens("使用 C++ 开发", "使用 C 开发") == {"c++"}

    def test_missing_detects_unsupported_noun(self) -> None:
        missing = missing_technical_tokens(
            "使用 STM32 完成 SPI 与 I2C 读写", "在 STM32 上完成 SPI 驱动的读写"
        )
        assert missing == {"i2c"}

    def test_no_missing_when_all_present(self) -> None:
        assert missing_technical_tokens("使用 pgvector 检索", "基于 pgvector 的向量检索") == set()


class TestValidateClaim:
    def test_unsupported_technical_noun_blocks_the_claim(self) -> None:
        """Coverage alone would pass this: two missing tokens out of twenty."""
        verdict = validate_claim(
            "使用 STM32 完成 SPI 传感器驱动与 I2C EEPROM 读写",
            {
                "evidence": [
                    {
                        "title": "spi_sensor.c",
                        "snippet": "在 STM32 上完成 SPI 传感器驱动的读写与寄存器配置。",
                    }
                ]
            },
        )
        assert verdict.supported is False
        assert "i2c" in verdict.unsupported_parts
        assert "eeprom" in verdict.unsupported_parts

    def test_quantified_claim_without_matching_unit_is_rejected(self) -> None:
        verdict = validate_claim(
            "优化算法性能，提升 70%",
            {"evidence": [{"title": "notes.md", "snippet": "对控制回路做了重构，减少重复计算。"}]},
        )
        assert verdict.supported is False
        assert any("70%" in part for part in verdict.unsupported_parts)

    def test_quantified_claim_with_matching_unit_is_not_rejected_for_that_reason(self) -> None:
        verdict = validate_claim(
            "将控制周期缩短 30% 并完成 PID 参数整定",
            {
                "evidence": [
                    {
                        "title": "motor_control.c",
                        "snippet": "完成 PID 参数整定，将控制周期缩短 30%，闭环调速稳定。",
                    }
                ]
            },
        )
        assert verdict.supported is True

    def test_well_supported_claim_passes(self) -> None:
        verdict = validate_claim(
            "基于 FreeRTOS 开发多任务实时控制系统",
            {
                "evidence": [
                    {
                        "title": "freertos.c",
                        "snippet": "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分并周期调度。",
                    }
                ]
            },
        )
        assert verdict.supported is True
        assert verdict.reasoning

    def test_empty_evidence_is_never_supported(self) -> None:
        verdict = validate_claim("熟练使用 Redis 与 Kafka", {"evidence": []})
        assert verdict.supported is False


class TestSaferFormulation:
    def test_drops_the_clause_that_has_no_evidence(self) -> None:
        safer = build_safer_formulation(
            "基于 FreeRTOS 开发多任务实时控制系统，并完成 CAN 总线节点通信",
            "项目基于 FreeRTOS 实现多任务实时控制，任务按优先级划分。",
            [],
        )
        assert "CAN" not in safer
        assert "FreeRTOS" in safer

    def test_strips_an_unsupported_number(self) -> None:
        safer = build_safer_formulation("优化算法性能，提升 70%", "优化算法性能。", ["70%"])
        assert "70%" not in safer
        assert safer

    def test_a_dangling_measure_verb_is_removed_with_the_number(self) -> None:
        # "优化算法性能，提升 70%" minus the figure is "优化算法性能，提升", which reads as
        # broken text rather than as a safer claim.
        safer = build_safer_formulation("优化算法性能，提升 70%", "优化算法性能。", ["70%"])
        assert "70%" not in safer
        assert not safer.endswith("提升")
        assert "优化算法性能" in safer

    def test_english_measure_verb_is_removed_too(self) -> None:
        safer = build_safer_formulation("Improved latency by 40%", "Latency was measured.", ["40%"])
        assert "40%" not in safer
        assert not safer.rstrip().lower().endswith("by")

    def test_a_measure_verb_dangling_mid_sentence_is_removed(self) -> None:
        """The verb dangles inside a sentence too, not only at its end.

        Dropping "40%" from "响应时间缩短了 40%，并完成了压测" used to leave
        "响应时间缩短了 ，并完成了压测": the regex was anchored at the end of the string, so the
        mid-sentence case went straight through. Both clauses here are evidenced, so the rewrite
        is the whole sentence with the figure and its verb gone.
        """
        evidence = "响应时间缩短，并完成了压测。响应时间通过压测验证。"
        safer = build_safer_formulation("响应时间缩短了 40%，并完成了压测", evidence, ["40%"])
        assert "40%" not in safer
        assert "缩短了 ，" not in safer, safer
        # The verb leaves with its number rather than staying behind without an object, which is
        # why the clause reads as a noun phrase afterwards ("响应时间，"). Tidy handles spacing and
        # punctuation; rebuilding the grammar of a sentence whose predicate was removed is not
        # something a rule can do honestly, so the candidate finishes the clause.
        assert "压测" in safer

    def test_no_rewrite_is_offered_when_a_technology_is_still_unsupported(self) -> None:
        """Removing the number is not enough if the sentence still names unevidenced technology.

        The live case: "使用 Kubernetes 将部署效率提升了 300%，并主导了 TensorFlow 模型上线" with
        neither technology anywhere in the candidate's evidence. A rewrite that keeps both names
        and merely deletes the figure would assert the same unsupported things, now with the
        number gone so the reader cannot see what was removed. No safer version exists, and
        saying so is the honest answer.
        """
        evidence = "使用 STM32 与 FreeRTOS 开发电机控制固件。"
        safer = build_safer_formulation(
            "使用 Kubernetes 将部署效率提升了 300%，并主导了 TensorFlow 模型上线",
            evidence,
            ["300%"],
        )
        assert safer == ""

    def test_a_supported_sentence_still_gets_its_numbers_stripped(self) -> None:
        # The guard above must not swallow the ordinary case: the sentence names an evidenced
        # technology, so dropping the figure and its verb leaves a claim the evidence can carry.
        evidence = "使用 STM32 开发电机控制固件，延迟表现见测试记录。"
        safer = build_safer_formulation(
            "使用 STM32 开发电机控制固件，延迟降低了 30%", evidence, ["30%"]
        )
        assert "30%" not in safer
        assert "STM32" in safer
        assert not safer.rstrip().endswith("降低了")

    def test_returns_empty_when_nothing_can_be_improved(self) -> None:
        assert build_safer_formulation("完全无关的一句话", "另一个完全无关的句子。", []) == ""

    def test_clause_splitter_handles_both_languages(self) -> None:
        assert len(split_clauses("A，B；C 以及 D")) == 4


@pytest.mark.skipif(
    not CLAIM_DATASET.exists(),
    reason="labelled dataset missing — run: python evals/generate_datasets.py",
)
class TestMeasuredSeparation:
    """Regression guard derived from the labelled dataset, not hand-written.

    If a future change to tokenisation or thresholds collapses the separation
    between supported and unsupported claims, these assertions fail — which is the
    only reason a hand-tuned threshold is defensible at all.
    """

    @staticmethod
    def _cases() -> list[dict[str, object]]:
        rows = [
            json.loads(line)
            for line in CLAIM_DATASET.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        seen: set[tuple[str, str]] = set()
        out: list[dict[str, object]] = []
        for row in rows:
            key = (row["gold"]["kind"], row["claim"])
            if key in seen:
                continue
            seen.add(key)
            evidence = _evidence_text(row["evidence"])
            out.append(
                {
                    "claim": row["claim"],
                    "evidence": evidence,
                    "gold_supported": row["gold"]["supported"],
                    "kind": row["gold"]["kind"],
                    "has_unsupported_number": row["gold"]["has_unsupported_number"],
                    "overlap": token_overlap(row["claim"], evidence),
                    "missing_technical": missing_technical_tokens(row["claim"], evidence),
                }
            )
        return out

    def test_threshold_sits_between_the_two_classes(self) -> None:
        cases = self._cases()
        supported = [c for c in cases if c["gold_supported"]]
        unsupported = [c for c in cases if not c["gold_supported"] and not c["missing_technical"]]
        assert supported and unsupported

        lowest_supported = min(float(c["overlap"]) for c in supported)
        highest_unsupported = max(float(c["overlap"]) for c in unsupported)

        assert highest_unsupported < SUPPORT_OVERLAP_THRESHOLD <= lowest_supported, (
            f"threshold {SUPPORT_OVERLAP_THRESHOLD} no longer separates the classes: "
            f"unsupported tops out at {highest_unsupported}, "
            f"supported bottoms out at {lowest_supported}"
        )

    def test_every_supported_case_is_detected(self) -> None:
        for case in self._cases():
            if not case["gold_supported"]:
                continue
            verdict = validate_claim(
                str(case["claim"]),
                {"evidence": [{"title": "e", "snippet": str(case["evidence"])}]},
            )
            assert verdict.supported is True, case["claim"]

    def test_no_unsupported_case_is_accepted(self) -> None:
        for case in self._cases():
            if case["gold_supported"]:
                continue
            verdict = validate_claim(
                str(case["claim"]),
                {"evidence": [{"title": "e", "snippet": str(case["evidence"])}]},
            )
            assert verdict.supported is False, case["claim"]

    def test_every_unsupported_number_is_rejected(self) -> None:
        numeric = [c for c in self._cases() if c["has_unsupported_number"]]
        assert numeric, "the dataset must contain quantified claims"
        for case in numeric:
            verdict = validate_claim(
                str(case["claim"]),
                {"evidence": [{"title": "e", "snippet": str(case["evidence"])}]},
            )
            assert verdict.supported is False, case["claim"]
