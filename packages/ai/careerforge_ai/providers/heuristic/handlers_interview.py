"""Interview question generation and answer evaluation without a language model.

A topic-keyed question bank with a three-level ladder, plus a keyword-coverage
evaluator. The evaluator is explicit about its own limits: without a real model
it can measure *coverage* (did the answer touch the concepts a good answer
contains?) but not *correctness*, and it says so in the feedback it returns.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from careerforge_ai.providers.heuristic.registry import handles
from careerforge_ai.schemas.common import DifficultyLevel
from careerforge_ai.schemas.interview import ExtractedQuestion, ExtractedTurnEvaluation

__all__ = ["generate_question", "evaluate_turn"]

#: ``topic → (concept, engineering, debugging)``. Each triple is one topic's
#: difficulty ladder, so adaptivity has somewhere to go.
_QUESTION_BANK: Mapping[str, tuple[str, str, str]] = {
    "free_rtos": (
        "你在项目里用了 FreeRTOS，为什么选择它而不是裸机前后台架构？",
        "Task 与 ISR 之间你怎么传递数据？为什么不直接用一个全局变量？",
        "如果系统偶发出现任务长时间得不到调度，你会怎么定位？",
    ),
    "stm32": (
        "STM32 启动到进入 main 之间发生了什么？",
        "你的外设初始化顺序是怎么安排的？如果时钟没使能会发生什么？",
        "某次上电后 SPI 读不到数据但偶尔正常，你会怎么排查？",
    ),
    "spi": (
        "SPI 的四种模式由什么决定？",
        "你怎么保证 SPI 通信的时序与片选控制正确？",
        "逻辑分析仪上看到 CLK 有波形但 MISO 一直是高电平，可能是什么原因？",
    ),
    "i2c": (
        "I2C 与 SPI 相比的取舍是什么？",
        "总线被从机拉死（SDA 持续为低）你怎么恢复？",
        "通信偶发 NACK，你会按什么顺序排查？",
    ),
    "can": (
        "CAN 总线为什么适合车载场景？",
        "你如何处理总线仲裁与错误帧？",
        "总线上出现大量错误帧，你如何定位是哪个节点的问题？",
    ),
    "pid": (
        "为什么你的控制回路选 PID 而不是更复杂的控制器？",
        "参数是怎么整定的？积分饱和怎么处理？",
        "阶跃响应出现过冲和持续振荡，你会先调哪个参数，为什么？",
    ),
    "dma": (
        "什么时候值得用 DMA 而不是中断搬运？",
        "DMA 与 CPU 访问同一块内存时你怎么保证一致性？",
        "数据出现偶发错位，你怎么判断是不是 DMA 配置问题？",
    ),
    "rtos_scheduler": (
        "RTOS 的任务优先级你是怎么划分的？",
        "优先级反转是什么？FreeRTOS 提供了什么机制缓解？",
        "系统出现偶发死锁，你会用哪些手段定位？",
    ),
    "uart": (
        "UART 通信你如何处理不定长数据帧？",
        "波特率不匹配会表现出什么现象？",
        "接收偶尔丢字节，你会检查哪些环节？",
    ),
    "performance_tuning": (
        "你如何评估一个嵌入式系统的性能瓶颈？",
        "在资源受限的 MCU 上你做过哪些优化，代价是什么？",
        "如果要求你把控制周期再缩短一半，你会从哪里入手？",
    ),
    "_default": (
        "请介绍一个你最有代表性的项目，重点说你负责的部分。",
        "这个项目里最难的技术问题是什么？你是怎么解决的？",
        "如果重新做一次，你会在哪些地方做出不同的技术选择？",
    ),
}

_HR_QUESTIONS: tuple[str, ...] = (
    "请用两分钟介绍一下你自己，以及你为什么投这个岗位。",
    "你过去遇到的最大挫折是什么？你从中学到了什么？",
    "你为什么想加入我们公司？你了解我们做什么吗？",
    "你未来三年的职业规划是什么？",
    "你如何看待加班和项目压力？",
)

_TOPIC_TERMS: Mapping[str, frozenset[str]] = {
    "free_rtos": frozenset({"任务", "优先级", "调度", "队列", "信号量", "中断", "task", "queue"}),
    "rtos_scheduler": frozenset(
        {"任务", "优先级", "调度", "队列", "信号量", "中断", "task", "queue"}
    ),
    "spi": frozenset({"时序", "时钟", "波形", "总线", "从机", "错误", "逻辑分析仪"}),
    "i2c": frozenset({"时序", "时钟", "波形", "总线", "从机", "错误", "逻辑分析仪"}),
    "uart": frozenset({"时序", "时钟", "波形", "总线", "从机", "错误", "逻辑分析仪"}),
    "can": frozenset({"时序", "时钟", "波形", "总线", "从机", "错误", "逻辑分析仪"}),
    "pid": frozenset({"比例", "积分", "微分", "整定", "超调", "稳态误差"}),
}

_BASE_TERMS: frozenset[str] = frozenset({"因为", "所以", "考虑", "权衡", "trade", "cost", "为什么"})

#: Answer length (characters) at which length-based sub-scores saturate.
_LENGTH_SATURATION = 220.0
_SHORT_ANSWER = 120


@handles(ExtractedQuestion)
def generate_question(text: str, context: Mapping[str, Any]) -> ExtractedQuestion:
    """Produce the next interview question for the requested topic and level."""
    raw_level = context.get("level")
    target_level = (
        DifficultyLevel.from_level(int(raw_level))
        if raw_level is not None
        else DifficultyLevel.CONCEPT
    )
    topic = str(context.get("topic") or "").strip().lower()
    mode = str(context.get("mode") or "technical")

    if mode == "hr":
        asked = int(context.get("asked_count") or 0)
        return ExtractedQuestion(
            question=_HR_QUESTIONS[asked % len(_HR_QUESTIONS)],
            topic="hr",
            level=DifficultyLevel.CONCEPT,
            rationale="HR 面试标准问题序列",
            follow_up_hints=["用 STAR 结构组织回答"],
        )

    bank = _QUESTION_BANK.get(topic) or _QUESTION_BANK["_default"]
    index = max(0, min(len(bank) - 1, target_level.level - 1))
    return ExtractedQuestion(
        question=bank[index],
        topic=topic or "_default",
        level=target_level,
        rationale=f"依据岗位要求与证据图谱中的 {topic or '项目'} 相关内容",
        follow_up_hints=list(bank[index + 1 :]),
    )


@handles(ExtractedTurnEvaluation)
def evaluate_turn(text: str, context: Mapping[str, Any]) -> ExtractedTurnEvaluation:
    """Score an answer by concept coverage, and be honest about the method."""
    answer = str(context.get("answer") or text)
    topic = str(context.get("topic") or "").lower()

    expected_terms = set(_BASE_TERMS) | set(_TOPIC_TERMS.get(topic, frozenset()))
    answer_lower = answer.lower()
    hits = [term for term in expected_terms if term in answer_lower]
    coverage = len(hits) / max(1, len(expected_terms))

    length_factor = min(1.0, len(answer) / _LENGTH_SATURATION)
    base = 40.0 + 45.0 * coverage * length_factor

    missing = [
        term for term in sorted(expected_terms) if term not in answer_lower and len(term) > 1
    ][:4]

    return ExtractedTurnEvaluation(
        technical_accuracy=round(min(88.0, base), 1),
        depth=round(min(85.0, base * (0.85 if len(answer) < _SHORT_ANSWER else 1.0)), 1),
        communication=round(min(90.0, 55.0 + 35.0 * length_factor), 1),
        confidence=round(_confidence_proxy(answer, hits, length_factor), 1),
        problem_solving=round(min(85.0, base * 0.95), 1),
        engineering_thinking=round(min(85.0, base * 0.9), 1),
        missing_knowledge=[f"未提及「{term}」" for term in missing],
        strong_points=[f"覆盖了「{hit}」" for hit in hits[:3]],
        feedback=(
            f"回答长度 {len(answer)} 字，覆盖了 {len(hits)}/{len(expected_terms)} 个期望要点。"
            "（本地规则引擎评估，仅反映要点覆盖度，不代表技术正确性）"
        ),
        follow_up_topics=missing[:3],
        suggested_answer="",
        evidence_conflicts=[],
    )


#: Hedging that reads as low confidence in *delivery*, as opposed to low accuracy.
_HEDGES: tuple[str, ...] = (
    "可能",
    "大概",
    "也许",
    "好像",
    "不太确定",
    "应该是吧",
    "记不清",
    "maybe",
    "i think",
    "probably",
    "not sure",
)

#: Markers of an answer delivered from experience rather than recited.
_ASSERTIVE: tuple[str, ...] = ("我实现", "我用", "我们使用", "因为我", "具体来说", "实际")


def _confidence_proxy(answer: str, hits: list[str], length_factor: float) -> float:
    """A deterministic stand-in for "how assured was the delivery".

    Labelled a proxy because that is what it is: it reads hedging and assertiveness
    markers, which is what the dimension is about, but it cannot hear tone. Reporting
    it as one of seven dimensions rather than as a verdict keeps that honest.
    """
    lowered = answer.lower()
    hedges = sum(1 for marker in _HEDGES if marker in lowered)
    assertive = sum(1 for marker in _ASSERTIVE if marker in lowered)
    score = 45.0 + 30.0 * length_factor + 4.0 * min(4, assertive) + 2.0 * min(5, len(hits))
    score -= 12.0 * hedges
    return max(0.0, min(100.0, score))
