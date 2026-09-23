"""Shared interview test data.

Kept apart from ``conftest`` on purpose: these are plain constants that tests import,
not pytest fixtures, and a data module cannot accidentally be re-imported as a second
conftest instance.
"""

from __future__ import annotations

#: A long answer that touches the concepts a good FreeRTOS answer contains.
LONG_ANSWER = (
    "我们使用 FreeRTOS 的队列在中断与任务之间传递数据，因为直接操作全局变量会带来竞态；"
    "任务按优先级划分，共享资源用互斥量保护以避免优先级反转，考虑过直接关中断但代价是延迟变大，"
    "所以最终选择了队列加信号量的方案。"
)

#: Deliberately thin, so the evaluator's low end is exercised.
SHORT_ANSWER = "用过。"
