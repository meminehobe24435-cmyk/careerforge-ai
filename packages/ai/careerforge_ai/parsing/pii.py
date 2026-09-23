"""PII detection and redaction.

Used wherever text leaves its original context: the public candidate page, exports,
and log payloads. Deliberately regex-based rather than model-based, for the same
reason the claim rules are: a redaction step that a language model can be talked out
of is not a redaction step.

The patterns target the identifiers that actually appear in resumes and documents —
email, phone, national ID, bank card — and nothing else. Over-broad matching here
would corrupt legitimate content (a commit SHA looks like a hex string, a version
number looks like a short card number), so each pattern is anchored tightly and the
boundary behaviour is tested.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

__all__ = [
    "PiiKind",
    "PiiFinding",
    "PII_PATTERNS",
    "scan_pii",
    "redact_pii",
    "contains_pii",
    "mask_value",
]

#: Replacement text. Kept short and neutral so it reads as a deliberate redaction
#: rather than as corrupted content.
_REDACTION = "[已脱敏]"


class PiiKind(StrEnum):
    EMAIL = "email"
    PHONE_CN = "phone_cn"
    PHONE_INTL = "phone_intl"
    ID_CARD_CN = "id_card_cn"
    BANK_CARD = "bank_card"


@dataclass(frozen=True, slots=True)
class PiiFinding:
    """One detected identifier, with enough context to explain the redaction."""

    kind: PiiKind
    value: str
    masked: str
    start: int
    end: int


#: ``(kind, pattern)``. Ordered so that a longer, more specific pattern is tried
#: before a shorter one that could match inside it — the national ID before the bank
#: card, both of which are 16–18 digits.
PII_PATTERNS: tuple[tuple[PiiKind, re.Pattern[str]], ...] = (
    (
        PiiKind.EMAIL,
        re.compile(r"(?<![\w.+-])[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{2,63}){1,3}(?![\w.-])"),
    ),
    (
        PiiKind.ID_CARD_CN,
        # 18 digits, last may be X. Anchored so it cannot be a slice of a longer run.
        re.compile(r"(?<!\d)\d{17}[\dXx](?![\dXx])"),
    ),
    (
        PiiKind.BANK_CARD,
        # 16–19 digits, optionally grouped in fours.
        re.compile(r"(?<!\d)(?:\d{4}[ -]?){3}\d{4,7}(?!\d)"),
    ),
    (
        PiiKind.PHONE_CN,
        # Mainland mobile numbers, optionally prefixed with +86.
        re.compile(r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d{9}(?!\d)"),
    ),
    (
        PiiKind.PHONE_INTL,
        # International form with a country code and separators.
        re.compile(r"(?<!\d)\+\d{1,3}[ -]?\d{2,4}[ -]?\d{3,4}[ -]?\d{3,4}(?!\d)"),
    ),
)

#: Characters kept visible at each end of a masked value, so a human can recognise
#: which identifier was removed without the value being recoverable.
_VISIBLE_HEAD = 2
_VISIBLE_TAIL = 2


def mask_value(value: str, *, kind: PiiKind | None = None) -> str:
    """Mask an identifier, keeping a short prefix for recognisability.

    An email keeps its local part's first two characters; everything else keeps two
    characters at each end. Short values are fully masked — keeping two of six
    characters would leave too much.
    """
    if kind is PiiKind.EMAIL and "@" in value:
        local, _, domain = value.partition("@")
        head = local[:2]
        return f"{head}***@{domain}"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:_VISIBLE_HEAD]}{'*' * (len(value) - _VISIBLE_HEAD - _VISIBLE_TAIL)}{value[-_VISIBLE_TAIL:]}"


def _overlaps(span: tuple[int, int], taken: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(not (end <= s or start >= e) for s, e in taken)


def scan_pii(text: str) -> list[PiiFinding]:
    """Every identifier found, ordered by position, without overlaps.

    Overlaps are resolved by the pattern order in :data:`PII_PATTERNS`, so an
    18-digit national ID is reported as one finding rather than also as a bank card.
    """
    if not text:
        return []

    taken: list[tuple[int, int]] = []
    findings: list[PiiFinding] = []
    for kind, pattern in PII_PATTERNS:
        for match in pattern.finditer(text):
            span = (match.start(), match.end())
            if _overlaps(span, taken):
                continue
            taken.append(span)
            value = match.group(0)
            findings.append(
                PiiFinding(
                    kind=kind,
                    value=value,
                    masked=mask_value(value, kind=kind),
                    start=span[0],
                    end=span[1],
                )
            )

    findings.sort(key=lambda finding: finding.start)
    return findings


def redact_pii(text: str) -> tuple[str, list[PiiFinding]]:
    """Return ``(redacted_text, findings)``.

    Redaction is applied from the end so earlier offsets stay valid while the string
    is being rebuilt.
    """
    findings = scan_pii(text)
    if not findings:
        return text, []

    redacted = text
    for finding in reversed(findings):
        redacted = redacted[: finding.start] + _REDACTION + redacted[finding.end :]
    return redacted, findings


def contains_pii(text: str) -> bool:
    """Whether anything was detected — the cheap gate before a full scan."""
    return bool(scan_pii(text))
