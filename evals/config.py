"""Evaluation thresholds, in one typed place.

Two rules shaped this file:

1. **A threshold is a claim about what the product must do**, so it is written down with its
   reason. Scattering `if score > 0.7` through the suites makes every number unfalsifiable.
2. **Gates and reports are different things.** A ``gate`` that is missed fails the process (CI,
   and anyone running the suite locally); a ``report`` that is missed is printed as ``MISS`` and
   the run still succeeds. Quality metrics the project has not yet earned stay ``report`` — a
   threshold quietly lowered until it always passes is worse than no threshold, because it
   converts an honest gap into a green check.

Numbers are anchored to the measured baseline (``reports/baseline-eval-report.json``) with a
margin: tight enough that a real regression fails (the retrieval fusion dropping a query, the
gate letting one fabricated number through), loose enough that run-to-run noise does not.

``evidence.unsafe_support_rate`` is the strictest gate in the project, and deliberately so. A
resume system that marks an invented achievement as *supported* has done the one thing this
product exists to prevent; a false negative (an honest bullet marked partial) merely costs the
candidate a review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "DEFAULT_BINS",
    "SUITE_THRESHOLDS",
    "Severity",
    "Threshold",
    "thresholds_for",
]

Severity = Literal["gate", "report"]

#: Reliability-diagram resolution. Ten buckets is the convention in the calibration literature
#: and is coarse enough that each bucket holds a meaningful number of cases at this sample size.
DEFAULT_BINS = 10


@dataclass(frozen=True)
class Threshold:
    """One metric's acceptable range, and what missing it means."""

    metric: str
    minimum: float | None = None
    maximum: float | None = None
    severity: Severity = "report"
    rationale: str = ""

    def __post_init__(self) -> None:
        if (self.minimum is None) == (self.maximum is None):
            raise ValueError(f"{self.metric}: exactly one of minimum/maximum must be set")

    @property
    def direction(self) -> Literal["min", "max"]:
        return "min" if self.minimum is not None else "max"

    @property
    def bound(self) -> float:
        bound = self.minimum if self.minimum is not None else self.maximum
        assert bound is not None  # guarded by __post_init__
        return bound

    def status(self, value: float) -> Literal["pass", "miss"]:
        """Compare with a small tolerance so float noise is not reported as a regression."""
        if self.minimum is not None:
            return "pass" if value + 1e-9 >= self.minimum else "miss"
        assert self.maximum is not None
        return "pass" if value - 1e-9 <= self.maximum else "miss"

    def to_dict(self, value: float) -> dict[str, object]:
        return {
            "value": round(value, 6),
            "threshold": self.bound,
            "direction": self.direction,
            "severity": self.severity,
            "status": self.status(value),
            "rationale": self.rationale,
        }


SUITE_THRESHOLDS: dict[str, tuple[Threshold, ...]] = {
    "jd_extraction": (
        Threshold(
            "jd.evidence_grounding_rate",
            minimum=1.00,
            severity="gate",
            rationale=(
                "每一段被抽取为技能证据的文字都必须能在 JD 原文中找到。"
                "1.00 是唯一可接受的取值：编造引用比漏掉技能严重得多。"
            ),
        ),
        Threshold(
            "jd.distractor_leakage_rate",
            maximum=0.05,
            severity="gate",
            rationale=(
                "语料中刻意埋了「不要在 required 里出现」的干扰技能。"
                "基线实测 0.0000；留 5% 余量以容纳启发式的分词波动。"
            ),
        ),
        Threshold(
            "jd.required_skill_f1",
            minimum=0.85,
            severity="gate",
            rationale="基线 0.8832（precision 0.7908 / recall 1.0000）。低于 0.85 视为抽取质量回归。",
        ),
        Threshold(
            "jd.role_accuracy",
            minimum=0.90,
            severity="report",
            rationale="基线 1.0000；岗位名识别属于展示层，不作为门禁。",
        ),
        Threshold(
            "jd.required_skill_precision",
            minimum=0.75,
            severity="report",
            rationale=(
                "基线 0.7908 —— 已知弱项：提取器会多报技能（recall 1.0 / precision 0.79）。"
                "记录而非门禁，避免为了变绿而收紧到掩盖问题。"
            ),
        ),
        Threshold(
            "jd.bonus_skill_f1",
            minimum=0.70,
            severity="report",
            rationale="基线 0.7758；加分项边界模糊，仅记录趋势。",
        ),
    ),
    "evidence_validation": (
        Threshold(
            "evidence.unsafe_support_rate",
            maximum=0.075,
            severity="gate",
            rationale=(
                "最严格的一条：把「无证据」判成「有证据」的比例。"
                "2026-09-25 实测 0.0500（40 个非 supported 用例里漏过 2 个：ev-0036「吞吐提升明显」、"
                "ev-0039「整机调试」——都是无关键词可挂的范围/模糊表述）。"
                "门禁设在 0.075（即 3/40）：比实测留一个用例的抖动余量，任何真实回归都会失败。"
                "本项目的目标是 0.02，**尚未达到**，缺口与对策记录在 docs/QUALITY.md。"
            ),
        ),
        Threshold(
            "evidence.unsafe_numeric_support_rate",
            maximum=0.00,
            severity="gate",
            rationale=(
                "带无法核实的量化数字的断言被判 supported 的比例，必须是 0："
                "「性能提升 70%」而没有任何 benchmark，任何情况下都不该通过。"
                "实测 0.0000（4 个量化用例全部被规则层拦下，模型根本没被调用）。"
            ),
        ),
        Threshold(
            "evidence.macro_f1",
            minimum=0.78,
            severity="gate",
            rationale=(
                "三分类（supported / partially_supported / unsupported）宏平均 F1。"
                "实测 0.8306；门槛 0.78 留约 5 个点余量，让真实的结构性回归失败、噪声不失败。"
            ),
        ),
        Threshold(
            "evidence.support_recall",
            minimum=0.80,
            severity="report",
            rationale=(
                "实测 0.9500（20 个 supported 里 19 个判对）。"
                "只记录不门禁：门禁宁可把有证据的句子判成 partially_supported，"
                "也不轻易给 supported —— 这是刻意的保守方向。"
            ),
        ),
        Threshold(
            "evidence.accuracy",
            minimum=0.80,
            severity="report",
            rationale="实测 0.8833；类别不均衡时它不如 macro F1 有信息量，仅作对照。",
        ),
        Threshold(
            "evidence.ece",
            maximum=0.05,
            severity="report",
            rationale=(
                "期望校准误差（10 桶：置信度 vs 实际正确率）。实测 0.0316（"
                "reports/confidence-calibration.md）。"
                "PHASE 14 之前这个数字只写在旁路产物里、不进 metrics，因此 compare 看不见它，"
                "校准漂移既不会出现在 diff 里也不会失败——本阶段把它并入被比较的指标集。"
                "仅记录不门禁：60 个用例上的校准指标做门禁会把噪声当回归；"
                "0.05 是文献里常用的宽松界，越过它才值得讨论。"
            ),
        ),
        Threshold(
            "evidence.brier",
            maximum=0.15,
            severity="report",
            rationale=(
                "Brier 分数（概率预测的均方误差），实测 0.0904。"
                "与 ECE 互补：它对单个高置信度的错误惩罚更重。同样只记录。"
            ),
        ),
    ),
    "rag_retrieval": (
        Threshold(
            "retrieval.hit_at_5",
            minimum=0.93,
            severity="gate",
            rationale="基线 recall_at_5 = 0.9661；Hit@5 不低于 0.93 表示「相关证据基本都能进前五」。",
        ),
        Threshold(
            "retrieval.mrr",
            minimum=0.85,
            severity="gate",
            rationale="基线 0.9011；MRR 掉下 0.85 意味着相关文档的排序明显变差。",
        ),
        Threshold(
            "retrieval.hit_at_1",
            minimum=0.80,
            severity="report",
            rationale="基线 recall_at_1 = 0.8475；首位命中受分词影响，记录而不门禁。",
        ),
        Threshold(
            "retrieval.recall_at_5",
            minimum=0.90,
            severity="report",
            rationale="基线与 Hit@5 接近（多相关文档的查询占少数），记录以观察多文档查询的变化。",
        ),
    ),
    "interview_relevance": (
        Threshold(
            "interview.forbidden_leakage_rate",
            maximum=0.05,
            severity="gate",
            rationale=(
                "「嵌入式岗位不该问 React Hooks」这类串岗问题的比例。"
                "门禁的存在是为了让 prompt 或技能映射的漂移立刻可见。"
            ),
        ),
        Threshold(
            "interview.required_skill_coverage",
            minimum=0.75,
            severity="gate",
            rationale="JD 必备技能中至少被一道题或一个话题覆盖的比例。",
        ),
        Threshold(
            "interview.duplicate_rate",
            maximum=0.10,
            severity="gate",
            rationale="语义重复问题（token Jaccard ≥ 0.8）的比例：重复提问会浪费候选人的时间预算。",
        ),
        Threshold(
            "interview.evidence_awareness_rate",
            minimum=0.50,
            severity="report",
            rationale=(
                "问题指向的技能确实是候选人有证据的技能的比例。"
                "记录而非门禁：追问弱点（gap 题）是刻意设计的一部分。"
            ),
        ),
        Threshold(
            "interview.difficulty_match_rate",
            minimum=0.60,
            severity="report",
            rationale="声明难度与请求难度一致的比例；自适应难度会偏离目标，故仅记录。",
        ),
    ),
}


def thresholds_for(suite: str) -> tuple[Threshold, ...]:
    """Thresholds declared for a suite; an unknown suite has none rather than an error.

    A suite added without thresholds is visible in the report as a suite with no gates —
    which is the honest state of affairs, and better than silently inheriting another
    suite's numbers.
    """
    return SUITE_THRESHOLDS.get(suite, ())
