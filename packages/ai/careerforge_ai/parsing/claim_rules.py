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

from careerforge_ai.parsing.skill_mentions import SkillPresence, presence_of
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
    "detect_ownership_gap",
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


def detect_missing_technical(
    claim: str, evidence_text: str, *, presence: SkillPresence | None = None
) -> list[ClaimReason]:
    """Flag technical nouns the claim asserts but the evidence never mentions.

    **Severity is decided by the skill vocabulary, not by the tokeniser** (PHASE 13). Two different
    facts used to look identical here, and the difference decides whether a candidate's sentence is
    refused outright:

    * a technology the *taxonomy* knows and the material does not carry (``Kafka`` claimed over a
      repository that only mentions Redis) — the product's documented rule says a technology nothing
      mentions makes a claim **unsupported**, so this is a ``blocker``;
    * a technical token the taxonomy cannot normalise (``Azure Pipelines``, ``RRF``) — its absence
      says more about the extractor than about the candidate, and hard-rejecting an honest claim
      because a synonym was missed is the failure this rule must not cause, so this stays a
      ``warning``.

    ``docs/QUALITY.md`` §7.4 recorded the gap ("``skill_not_in_graph`` is only a warning") and named
    the prerequisite: a false-positive audit of the extractor before raising severity. That audit is
    ``packages/ai/tests/test_skill_presence.py``, and the escalation is limited to the half the audit
    can support.
    """
    resolved = presence if presence is not None else presence_of(claim, evidence_text)
    if not resolved.any:
        return []

    confirmed = sorted(resolved.confirmed_absent.values())
    unconfirmed = sorted(resolved.unconfirmed_tokens)
    # Quote the candidate's own spelling where there is one: "Kafka" is what they wrote, even though
    # the judgement rests on the canonical skill the taxonomy resolved it to.
    named = [*confirmed, *unconfirmed[: max(1, 5 - len(confirmed))]]
    if not confirmed:
        message = (
            f"证据中未出现：{'、'.join(named[:5])}。"
            "句子里的每一项技术名词都需要在证据里出现，否则面试官一问就会露底。"
        )
    else:
        message = (
            f"证据中完全没有出现：{'、'.join(confirmed[:5])}。"
            "产品规则是：任何证据都没有提到的技术，断言即判为不支持——"
            "先补上能证明它的材料（代码、提交或文档），或把这句里的它删掉。"
        )
    return [
        ClaimReason(
            rule=ClaimRuleCode.SKILL_NOT_IN_GRAPH,
            severity="blocker" if resolved.blocked else "warning",
            message=message,
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


#: Phrases that assert *ownership or scope* rather than a capability. Narrower than
#: :data:`SUPERLATIVE_PATTERNS` on purpose: this list decides a status cap, so a false positive
#: silently downgrades an honest claim.
_OWNERSHIP_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"主导|led the|owned the", "主导"),
    (r"独立完成|独立负责|independently built", "独立完成/负责"),
    (r"负责整个|负责全部|整个.{0,6}(架构|系统|平台)的设计", "负责整体范围"),
    (r"带领\s*\d*\s*人?团队|牵头|作为技术负责人", "团队或项目主导权"),
    (r"从\s*0\s*到\s*1|from scratch", "从零到一的起点"),
)


def detect_ownership_gap(claim: str, evidence_text: str) -> ClaimReason | None:
    """An ownership claim the evidence never makes — and never should be waved through.

    The deterministic layer can already reject a number nothing measures. Role language was the
    remaining hole, and PHASE 12's evaluation walked straight into it: with a hand-authored golden
    set, four scope-inflated sentences ("主导了后端服务的重构" over evidence that says *参与*, and
    three more like it) came back **supported**, because token overlap between "主导了后端服务的重构"
    and "参与后端服务重构的技术方案讨论" is high and the confidence arithmetic has no opinion about
    who did what.

    The rule is deliberately literal: if the claim asserts ownership and the *evidence text never
    says the same thing*, the claim cannot be fully supported by that evidence. It caps the status
    rather than blocking it, because the underlying work is usually real — the sentence overstates
    the role, and "partially supported" is the honest answer to an overstated role, not "rejected".

    A claim with no ownership language returns ``None``: this rule says nothing about ordinary
    achievements, and pretending otherwise would make every resume bullet a suspect.
    """
    if not evidence_text.strip():
        # No material to check against. The caller's contract says it supplies this; inventing a
        # gap from an empty string would downgrade every claim in a misconfigured deployment.
        return None

    for pattern, label in _OWNERSHIP_PATTERNS:
        match = re.search(pattern, claim, re.IGNORECASE)
        if match is None:
            continue
        phrase = match.group(0)
        if phrase.lower() in evidence_text.lower():
            continue
        return ClaimReason(
            rule=ClaimRuleCode.SUPERLATIVE_LANGUAGE,
            severity="warning",
            message=(
                f"「{label}」是职责范围的断言，而证据中没有出现「{phrase}」——"
                "证据能支持你做过这件事，但支持不了「由你主导/独立完成」这个范围说法，"
                "因此最多只能判为 partially_supported。"
            ),
        )
    return None


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
            "severity": "blocker|warning",
            "description": (
                "断言中的技术名词必须在证据中出现。taxonomy 能归一化的技能（含别名/等价说法）"
                "在证据中完全不存在时为 blocker（判 unsupported）；taxonomy 无法识别的技术名词"
                "仅告警，避免把同义写法误判为编造"
            ),
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
#:
#: The lookahead matches a clause separator as well as the end of the string, because the verb
#: dangles mid-sentence too: dropping "300%" from "将部署效率提升了 300%，并主导了…" left
#: "将部署效率提升了 ，并主导了…". Requiring a separator (or the end) after the verb is what keeps
#: this from eating a verb that still has an object — "提升了部署效率" has text after it and is left
#: alone.
_DANGLING_MEASURE_RE = re.compile(
    r"[，,]?\s*(?:提升了?|提高了?|降低了?|减少了?|增长了?|下降了?|缩短了?|节省了?|达到|超过|"
    r"improved|increased|reduced|decreased|by|to)\s*(?=[，,；;、]|$)",
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
            candidate = _tidy(candidate)
            if candidate and candidate != claim:
                return candidate

    if not dropped_numbers:
        return ""

    stripped = claim
    for number in dropped_numbers:
        stripped = stripped.replace(number, "")
    stripped = _tidy(stripped)
    # Removing the number is not enough when the sentence also names a technology the evidence
    # does not carry: the result would still assert something unsupported, now with the figure
    # gone so the reader cannot even see what was removed. No safer rewrite exists for such a
    # sentence, and saying so is the honest answer.
    if missing_technical_tokens(stripped, evidence_text):
        return ""
    return stripped if stripped and stripped != claim else ""


def _tidy(text: str) -> str:
    """Whitespace, a dangling measure verb, and the punctuation it leaves behind.

    Shared by both rewrite branches because both can strand a verb: the clause branch drops
    numbers from the clauses it keeps, and the fallback drops them from the whole sentence.
    """
    tidied = re.sub(r"\s{2,}", " ", text)
    tidied = _DANGLING_MEASURE_RE.sub("", tidied)
    # "…效率 ，并主导" → the verb left a space before the separator.
    tidied = re.sub(r"\s+([，,；;、])", r"\1", tidied)
    return tidied.strip("，,。;； ")


def numeric_risk_summary(reasons: Sequence[ClaimReason]) -> str:
    """One-line summary of the numeric rules that fired, for the UI badge."""
    blockers = [reason for reason in reasons if reason.severity == "blocker"]
    if not blockers:
        return ""
    return f"{len(blockers)} 处量化数据缺乏证据支撑"
