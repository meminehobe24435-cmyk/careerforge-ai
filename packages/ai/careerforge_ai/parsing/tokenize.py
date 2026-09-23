"""Shared tokenisation and technical-term handling.

This module is neutral infrastructure: retrieval, claim adjudication and
confidence scoring all need to agree on what a "token" is. Keeping one definition
in one place is what stops two subsystems from disagreeing about whether a claim
mentions ``I2C``.

Bilingual by design. Chinese characters are meaningful single units, so they are
kept as tokens; latin words shorter than two characters are dropped because a
stray ``c`` produces nothing but false positives. Getting this wrong is not a
cosmetic issue — an earlier version filtered every single-character token,
including CJK, which silently emptied the token set for Chinese text and made
every Chinese claim look unsupported.
"""

from __future__ import annotations

import re

__all__ = [
    "tokens",
    "token_overlap",
    "technical_tokens",
    "base_form",
    "missing_technical_tokens",
    "count_cjk_chars",
    "estimate_tokens",
]

_WORD_RE = re.compile(r"[a-z0-9+#._]+|[\u4e00-\u9fff]", re.IGNORECASE)
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_CJK_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "is",
        "are",
        "be",
        "as",
        "at",
        "by",
        "from",
        "that",
        "this",
        "it",
        "we",
        "you",
        "your",
        "our",
        "的",
        "了",
        "和",
        "与",
        "及",
        "或",
        "在",
        "是",
        "为",
        "并",
        "等",
        "对",
        "有",
        "能",
        "熟悉",
        "了解",
        "掌握",
        "要求",
        "负责",
        "参与",
        "具备",
        "优先",
        "加分",
        "以上",
    }
)


def tokens(text: str) -> list[str]:
    """Tokenise for overlap and lexical scoring."""
    out: list[str] = []
    for token in _WORD_RE.findall(text):
        lowered = token.lower()
        if lowered in _STOPWORDS:
            continue
        if len(token) == 1 and not _CJK_CHAR_RE.match(token):
            continue
        out.append(lowered)
    return out


def token_overlap(left: str, right: str) -> float:
    """How much of ``left`` is present in ``right``.

    Coverage of the claim dominates (0.70) over symmetric similarity (0.30). A
    higher Jaccard weight punished detailed evidence: a long, specific file
    description scored lower than a short vague one, and genuinely-supported
    claims were rejected because of it.
    """
    left_tokens = set(tokens(left))
    right_tokens = set(tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    jaccard = len(intersection) / len(left_tokens | right_tokens)
    coverage = len(intersection) / len(left_tokens)
    return round(0.30 * jaccard + 0.70 * coverage, 4)


#: Latin/technical tokens: identifiers, acronyms, versions. These carry the
#: specific content of a technical claim ("I2C", "pgvector", "pytest"), so one of
#: them missing from the evidence is a strong signal that the claim as written is
#: not fully supported — much stronger than a missing common word.
_TECHNICAL_RE = re.compile(r"[a-z][a-z0-9+#._-]{0,30}", re.IGNORECASE)

#: Trailing version markers (``C++11``, ``Python3``, ``heap_4``) are stripped
#: before comparison. Without this, a claim saying "C++11" is flagged as
#: unsupported by evidence that says "C++", which is a false negative on the most
#: ordinary kind of technical writing there is.
_VERSION_SUFFIX_RE = re.compile(r"[-._]?\d+$")


def technical_tokens(text: str) -> set[str]:
    """Distinctive latin/technical tokens in ``text``, lower-cased."""
    return {
        match.group(0).lower() for match in _TECHNICAL_RE.finditer(text) if len(match.group(0)) >= 2
    }


def base_form(token: str) -> str:
    """A technical token with its version suffix removed."""
    return _VERSION_SUFFIX_RE.sub("", token) or token


def missing_technical_tokens(claim: str, evidence_text: str) -> set[str]:
    """Technical tokens the claim asserts but the evidence never mentions.

    Comparison happens on :func:`base_form` on both sides, so a version suffix is
    never the reason a claim is rejected.
    """
    evidence_bases = {base_form(token) for token in technical_tokens(evidence_text)}
    return {token for token in technical_tokens(claim) if base_form(token) not in evidence_bases}


# ── Token counting ───────────────────────────────────────────────────────────

#: Rough characters-per-token for latin script prose and source code.
_LATIN_CHARS_PER_TOKEN = 4.0


def count_cjk_chars(text: str) -> int:
    return len(_CJK_PATTERN.findall(text))


def estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text``.

    Deliberately simple and stable: an estimate that is consistent between runs is
    more useful for cost dashboards and chunk sizing than a marginally more
    accurate one that is expensive to compute. Callers that need real usage get it
    from the provider and mark it ``estimated=False``.
    """
    if not text:
        return 0
    cjk = count_cjk_chars(text)
    latin_chars = len(text) - cjk
    return max(1, int(cjk + latin_chars / _LATIN_CHARS_PER_TOKEN + 0.5))
