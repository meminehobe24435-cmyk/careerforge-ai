"""Repository-intelligence narrative without a language model.

The technical elements and file lists are detected deterministically before this
runs; all this adds is a readable summary. It refuses to infer architecture or
domains from thin material, and says so instead of filling the gap with
plausible-sounding prose.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from careerforge_ai.providers.heuristic.registry import handles
from careerforge_ai.schemas.github import ExtractedProjectIntelligence

__all__ = ["project_intelligence"]

_MAX_ELEMENTS = 10
_MAX_FILES = 5
_MAX_HIGHLIGHTS = 5


@handles(ExtractedProjectIntelligence)
def project_intelligence(text: str, context: Mapping[str, Any]) -> ExtractedProjectIntelligence:
    """Turn deterministic detections into a short, factual description."""
    elements = [str(item) for item in (context.get("detected_elements") or [])]
    files = [str(item) for item in (context.get("files") or [])]
    readme = str(context.get("readme") or "")

    highlights: list[str] = []
    if elements:
        highlights.append("识别到的技术要素：" + "、".join(elements[:_MAX_ELEMENTS]))
    if files:
        highlights.append("关键实现文件：" + "、".join(files[:_MAX_FILES]))
    if readme:
        highlights.append("仓库包含 README 说明，可作为项目背景证据")

    return ExtractedProjectIntelligence(
        highlights=highlights[:_MAX_HIGHLIGHTS],
        architecture_hints=[],
        domains=[],
        summary="（本地规则引擎生成，仅基于检测到的技术要素，未做语义推断）",
    )
