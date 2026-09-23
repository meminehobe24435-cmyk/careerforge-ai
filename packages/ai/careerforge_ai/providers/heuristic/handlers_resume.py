"""Resume rewriting without a language model.

Deliberately minimal. A rule engine cannot write a better sentence, and pretending
otherwise would produce exactly the polished-but-unverifiable bullet this product
exists to prevent. What it *can* do is remove the filler that makes a real bullet
harder to read, and say plainly when it changed nothing.

That restraint is the point. On the zero-key path the candidate gets a modest,
honest diff plus a full gate report; with a real model they get a better-written
one. Neither is allowed to add a fact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from careerforge_ai.parsing.skill_taxonomy import extract_skill_mentions
from careerforge_ai.providers.heuristic.registry import handles
from careerforge_ai.schemas.claim import ExtractedResumeOptimization, ResumeBullet

__all__ = ["optimize_resume"]

#: Leading filler that adds no information to a resume bullet. Removing a hedge is
#: safe in the direction that matters: it can only make the claim *smaller*.
_FILLER_PREFIXES: tuple[str, ...] = (
    "主要参与",
    "参与完成",
    "参与",
    "协助完成",
    "协助",
    "帮助",
    "配合完成",
    "配合",
    "独立完成了",
    "完成了",
    "做了",
)

#: Adverbs that weaken a specific statement without adding detail.
_FILLER_ADVERBS: tuple[str, ...] = ("非常", "十分", "很好地", "较好地", "有效地")

_TRAILING_PUNCTUATION = "。；;，, "
_WHITESPACE_RUN = re.compile(r"\s{2,}")

_NO_CHANGE_RATIONALE = "原文已经足够具体，确定性改写没有可安全改进之处"


def _strip_filler(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    result = text.strip()

    for prefix in _FILLER_PREFIXES:
        if result.startswith(prefix):
            candidate = result[len(prefix) :].lstrip("，,、。 ")
            # Only strip when a sentence still remains; a bullet that was *only* a
            # filler phrase should be left alone rather than emptied.
            if len(candidate) >= 6:
                removed.append(prefix)
                result = candidate
            break

    for adverb in _FILLER_ADVERBS:
        if adverb in result:
            result = result.replace(adverb, "")
            removed.append(adverb)

    return _WHITESPACE_RUN.sub(" ", result).strip(), removed


def _rewrite(original: str) -> tuple[str, str, list[str]]:
    """Return ``(optimized, rationale, keywords_added)``.

    ``keywords_added`` is always empty: this implementation never introduces a
    term, so reporting one would be a lie that the gate would then have to catch.
    """
    stripped, removed = _strip_filler(original)
    stripped = stripped.rstrip(_TRAILING_PUNCTUATION)

    if not removed or len(stripped) < 6:
        return original.strip(), _NO_CHANGE_RATIONALE, []

    mentions = [skill.display_name for skill, _, _ in extract_skill_mentions(stripped)]
    rationale = "去除了填充词：" + "、".join(removed[:3])
    if mentions:
        rationale += f"；保留全部技术要素（{'、'.join(mentions[:4])}），未新增任何事实"
    else:
        rationale += "；未新增任何事实"
    return stripped, rationale, []


@handles(ExtractedResumeOptimization)
def optimize_resume(text: str, context: Mapping[str, Any]) -> ExtractedResumeOptimization:
    """Rewrite the bullets supplied in ``context['bullets']``.

    The bullets arrive as structured data rather than being parsed out of the
    rendered prompt: the prompt is for the model, and reading it back would make
    this implementation depend on prose formatting.
    """
    bullets: Sequence[Mapping[str, Any]] = context.get("bullets") or []
    out: list[ResumeBullet] = []

    for item in bullets:
        original = str(item.get("text") or "").strip()
        if not original:
            continue
        optimized, rationale, keywords = _rewrite(original)
        out.append(
            ResumeBullet(
                section=str(item.get("section") or "project"),
                original=original,
                optimized=optimized,
                rationale=rationale,
                keywords_added=keywords,
            )
        )

    return ExtractedResumeOptimization(bullets=out)
