"""Deterministic claim rules — the anti-hallucination layer that runs before any model.

These rules are the reason the product can promise anything. A language model asked
"is this claim supported?" will happily reason its way to "plausibly yes"; a rule
that says *this number appears nowhere in the evidence* will not.

They live in ``parsing`` rather than in an agent or a provider because two very
different callers need the identical definition:

* :mod:`careerforge_ai.providers.heuristic.handlers_claim` — the zero-key path;
* :mod:`careerforge_ai.agents.validator` — the gate that runs regardless of which
  provider produced the sentence.

If those two ever disagreed, a claim could pass one and fail the other, which is
the kind of inconsistency that destroys trust in a verification product.

Rule order matters and is fixed (ADR-014): numbers first, then missing technical
nouns, then support classification. A cheap deterministic rejection always
precedes anything expensive.
"""

from __future__ import annotations

from collections.abc import Sequence
import re

from careerforge_ai.parsing.tokenize import missing_technical_tokens, token_overlap
from careerforge_ai.schemas.claim import ClaimReason, NumericMention
from careerforge_ai.schemas.common import ClaimRuleCode

__all__ = [
    "NUMERIC_MENTION_RE",
    "build_safer_formulation",
    "numeric_risk_summary",
    "split_clauses",
    "SUPERLATIVE_PATTERNS",
    "find_quantified_mentions",
    "has_comparable_number",
    "has_superlative_language",
    "detect_numeric_risk",
    "detect_missing_technical",
    "detect_superlatives",
    "describe_rules",
]

#: Quantified fragments a candidate might claim. Matches a number plus a unit that
#: makes it a *measurement*: a bare "3" is a count, "3×" is a claim of improvement.
NUMERIC_MENTION_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>%|％|倍|万|亿|千|k|K|ms|us|μs|ns|fps|qps|tps|h|小时|天|人|次)"
)

#: Unit → how the mention is classified. Used for display and for the
#: "comparable number" test, which requires the same unit family.
_UNIT_KIND: dict[str, str] = {
    "%": "percentage",
    "％": "percentage",
    "倍": "multiple",
    "万": "absolute",
    "亿": "absolute",
    "千": "absolute",
    "k": "absolute",
    "K": "absolute",
    "ms": "duration",
    "us": "duration",
    "μs": "duration",
    "ns": "duration",
    "h": "duration",
    "小时": "duration",
    "天": "duration",
    "fps": "rate",
    "qps": "rate",
    "tps": "rate",
    "人": "scale",
    "次": "scale",
}

#: Phrases that assert more than evidence can support. Kept small on purpose: an
#: over-eager list produces false accusations, which are worse than a miss.
SUPERLATIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"精通|expert in|mastery of", "「精通」是最强的能力断言，需要非常充分的证据"),
    (r"主导|led the|owned the", "「主导」意味着主导权，需要有可验证的职责范围"),
    (r"独立完成|independently built", "「独立完成」需要有明确的范围界定"),
    (r"从\s*0\s*到\s*1|from scratch", "「从 0 到 1」需要能证明起点确实为空"),
    (r"业界领先|行业首创|world[- ]class|state of the art", "绝对化措辞无法用个人证据支撑"),
    (r"大幅|显著提升|dramatically|significantly", "「大幅/显著」需要量化对比才能成立"),
    (r"全栈|full[- ]stack", "「全栈」涵盖范围很广，需要分别给出证据"),
)


def find_quantified_mentions(text: str) -> list[NumericMention]:
    """Every quantified fragment in ``text``, with its unit family."""
    mentions: list[NumericMention] = []
    for match in NUMERIC_MENTION_RE.finditer(text):
        raw = match.group(0)
        unit = match.group("unit")
        try:
            value = float(match.group("value"))
        except ValueError:  # pragma: no cover - the regex guarantees a number
            value = None
        mentions.append(
            NumericMention(
                raw=raw,
                kind=_UNIT_KIND.get(unit, "absolute"),
                value=value,
                supported=False,
            )
        )
    return mentions


def has_comparable_number(mention: NumericMention, evidence_text: str) -> bool:
    """Whether the evidence contains a measurement of the same kind.

    Same *kind*, not same value: if a candidate claims "improved performance by
    70%" and the evidence contains a measured 45% improvement, the 70% is still
    unsupported. The rule deliberately does not try to judge closeness — that is
    the model's job, and the model is told the number must appear.
    """
    for candidate in find_quantified_mentions(evidence_text):
        if candidate.kind == mention.kind:
            return True
    return False


def has_superlative_language(text: str) -> list[tuple[str, str]]:
    """Over-claiming phrases present in ``text``, as ``(matched, explanation)``."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pattern, explanation in SUPERLATIVE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match and match.group(0) not in seen:
            seen.add(match.group(0))
            found.append((match.group(0), explanation))
    return found


def detect_numeric_risk(
    claim: str, evidence_text: str
) -> tuple[list[NumericMention], list[ClaimReason]]:
    """Flag quantified fragments the evidence cannot support."""
    mentions = find_quantified_mentions(claim)
    reasons: list[ClaimReason] = []
    for mention in mentions:
        supported = has_comparable_number(mention, evidence_text)
        mention.supported = supported
        if not supported:
            reasons.append(
                ClaimReason(
                    rule=ClaimRuleCode.NUMERIC_WITHOUT_EVIDENCE,
                    severity="blocker",
                    message=(
                        f"「{mention.raw}」在证据中找不到同类量化数据。"
                        "不能凭印象补数字，要么补上实测记录，要么删掉这个数字。"
                    ),
                )
            )
    return mentions, reasons


def detect_missing_technical(claim: str, evidence_text: str) -> list[ClaimReason]:
    """Flag technical nouns the claim asserts but the evidence never mentions."""
    missing = sorted(missing_technical_tokens(claim, evidence_text))
    if not missing:
        return []
    return [
        ClaimReason(
            rule=ClaimRuleCode.SKILL_NOT_IN_GRAPH,
            severity="warning",
            message=(
                f"证据中未出现：{'、'.join(missing[:5])}。"
                "句子里的每一项技术名词都需要在证据里出现，否则面试官一问就会露底。"
            ),
        )
    ]


def detect_superlatives(claim: str) -> list[ClaimReason]:
    """Flag over-claiming phrasing. Never blocking on its own — only advisory."""
    return [
        ClaimReason(
            rule=ClaimRuleCode.SUPERLATIVE_LANGUAGE,
            severity="warning",
            message=f"「{matched}」：{explanation}",
        )
        for matched, explanation in has_superlative_language(claim)
    ]


def describe_rules() -> Sequence[dict[str, str]]:
    """Serialisable description of the rule layer, for the API and the docs."""
    return (
        {
            "code": ClaimRuleCode.NUMERIC_WITHOUT_EVIDENCE.value,
            "severity": "blocker",
            "description": "断言中的量化数字必须在证据中出现同类量化数据",
        },
        {
            "code": ClaimRuleCode.SKILL_NOT_IN_GRAPH.value,
            "severity": "warning",
            "description": "断言中的技术名词必须在证据中出现",
        },
        {
            "code": ClaimRuleCode.SUPERLATIVE_LANGUAGE.value,
            "severity": "warning",
            "description": "绝对化与夸大措辞需要额外证据支撑",
        },
    )


# ── Safer rewrites ───────────────────────────────────────────────────────────

#: A measure verb left without its object once a number is removed.
#: "优化性能，提升 70%" minus the figure is "优化性能，提升" — broken text.
_DANGLING_MEASURE_RE = re.compile(
    r"[，,]?\s*(?:提升了?|提高了?|降低了?|减少了?|增长了?|下降了?|缩短了?|节省了?|达到|超过|"
    r"improved|increased|reduced|decreased|by|to)\s*$",
    re.IGNORECASE,
)

#: Clause separators used when downgrading a claim. A clause is the smallest unit
#: a candidate can meaningfully drop, in both Chinese and English.
_CLAUSE_SPLIT_RE = re.compile(r"[，,；;、]|(?:\s+and\s+)|(?:并(?=[\u4e00-\u9fff]))|以及|同时")


def split_clauses(claim: str) -> list[str]:
    """Split a claim into droppable clauses."""
    return [part.strip() for part in _CLAUSE_SPLIT_RE.split(claim) if part.strip()]


def build_safer_formulation(
    claim: str,
    evidence_text: str,
    dropped_numbers: Sequence[str] = (),
    *,
    partial_threshold: float = 0.30,
) -> str:
    """Keep only the clauses the evidence can carry.

    A rejection without an alternative just pushes the candidate back to writing it
    by hand, which is how a "safe" system ends up unused. Returns an empty string
    when nothing changed, so the caller can tell "no safer option exists" apart
    from "the safer option is identical".
    """
    clauses = split_clauses(claim)
    if len(clauses) > 1:
        kept = [
            clause
            for clause in clauses
            if not missing_technical_tokens(clause, evidence_text)
            and token_overlap(clause, evidence_text) >= partial_threshold
        ]
        if kept and len(kept) < len(clauses):
            candidate = "，".join(kept)
            for number in dropped_numbers:
                candidate = candidate.replace(number, "")
            candidate = re.sub(r"\s{2,}", " ", candidate).strip("，,。;； ")
            if candidate and candidate != claim:
                return candidate

    if not dropped_numbers:
        return ""

    stripped = claim
    for number in dropped_numbers:
        stripped = stripped.replace(number, "")
    stripped = re.sub(r"\s{2,}", " ", stripped)
    # A measure verb left without its object reads as broken text rather than as a
    # safer claim, which is the opposite of what a rewrite is for.
    stripped = _DANGLING_MEASURE_RE.sub("", stripped).strip("，,。;； ")
    return stripped if stripped and stripped != claim else ""


def numeric_risk_summary(reasons: Sequence[ClaimReason]) -> str:
    """One-line summary of the numeric rules that fired, for the UI badge."""
    blockers = [reason for reason in reasons if reason.severity == "blocker"]
    if not blockers:
        return ""
    return f"{len(blockers)} 处量化数据缺乏证据支撑"
