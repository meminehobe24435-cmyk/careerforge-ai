"""Learning-plan generation without a language model.

Deterministic templates over the prioritised gap list. The structure encodes the
product's rule that a gap is only closed by an artefact: concept → mechanism →
mini project → evidence, one week each.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from careerforge_ai.providers.heuristic.registry import handles
from careerforge_ai.schemas.learning import (
    ExtractedLearningPlan,
    ExtractedLearningWeek,
    ExtractedMiniProject,
)

__all__ = ["generate_learning_plan"]

#: ``(theme, weekly output, how the week is verified as done)``
_WEEK_THEMES: tuple[tuple[str, str, str], ...] = (
    (
        "打基础：概念与最小可运行示例",
        "搭出可运行的最小示例，跑通工具链",
        "一个能在本机跑起来的 hello-world 级程序",
    ),
    (
        "补原理：把机制讲清楚",
        "能用自己的话解释核心机制与边界条件",
        "一份 500 字的技术笔记，含至少 3 个「为什么」",
    ),
    ("做小项目：把知识变成作品", "独立完成一个可演示的小项目", "一个可运行、可演示的 Mini Project"),
    (
        "上证据：把项目变成简历资产",
        "补 README、提交记录与可量化的验收说明",
        "GitHub 仓库 + 可被验证的成果描述",
    ),
)

_MAX_GAPS = 4
_MIN_WEEKS = 1
_MAX_WEEKS = 12
_DEFAULT_MINI_PROJECT_HOURS = 8.0


@handles(ExtractedLearningPlan)
def generate_learning_plan(text: str, context: Mapping[str, Any]) -> ExtractedLearningPlan:
    """Build a 30-day plan whose outputs are provable artefacts."""
    gaps: Sequence[Mapping[str, Any]] = context.get("gaps") or []
    horizon_days = int(context.get("horizon_days") or 30)
    weeks_count = max(_MIN_WEEKS, min(_MAX_WEEKS, horizon_days // 7))

    top_gaps = list(gaps)[:_MAX_GAPS]
    priority_order = [
        str(gap.get("canonical_id", "")) for gap in top_gaps if gap.get("canonical_id")
    ]

    weeks: list[ExtractedLearningWeek] = []
    for index in range(weeks_count):
        theme, output, verification = _WEEK_THEMES[min(index, len(_WEEK_THEMES) - 1)]
        focus = [str(top_gaps[index].get("display_name", ""))] if index < len(top_gaps) else []
        weeks.append(
            ExtractedLearningWeek(
                week=index + 1,
                theme=theme,
                goals=[f"{'、'.join(focus) if focus else '综合'}：{theme}"],
                focus_skills=focus,
                resources=["官方文档", "一个可运行的开源示例"],
                output=output,
                verification=verification,
            )
        )

    mini_projects: list[ExtractedMiniProject] = []
    for gap in top_gaps:
        name = str(gap.get("display_name", "")).strip()
        if not name:
            continue
        mini_projects.append(
            ExtractedMiniProject(
                title=f"{name} 实战小项目",
                skill_canonical_id=str(gap.get("canonical_id", "")),
                description=(
                    f"围绕 {name} 构建一个可独立运行、可演示的最小系统，"
                    "把用法、边界条件与失败模式都覆盖到。"
                ),
                deliverables=[f"{name} 的可运行 demo", "README 说明与运行步骤"],
                acceptance_criteria=["能在干净环境按 README 跑通", "有至少一次成功的演示记录"],
                evidence_potential=(
                    f"产出后即可在简历中真实地写：使用 {name} 完成 ___（附代码与提交）"
                ),
                estimated_hours=_DEFAULT_MINI_PROJECT_HOURS,
            )
        )

    return ExtractedLearningPlan(
        title=f"{horizon_days} 天补强计划",
        summary=f"针对 {len(top_gaps)} 个优先缺口，按「概念 → 原理 → 小项目 → 证据化」四段式推进。",
        weeks=weeks,
        mini_projects=mini_projects,
        priority_order=priority_order,
    )
