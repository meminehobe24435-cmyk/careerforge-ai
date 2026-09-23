"""Lexical helpers for the heuristic provider.

Everything here is deterministic and dependency-free: tokenisation, overlap
scoring, a feature-hash embedding and the section splitter used for resume-like
text. No language model is involved, and none of it is random.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import math
import re

__all__ = [
    "HEURISTIC_EMBEDDING_DIM",
    "tokens",
    "token_overlap",
    "heuristic_embedding",
    "split_sections",
    "bullets",
    "first_date",
    "SECTION_HEADERS",
]

#: Deterministic embedding width. Small on purpose: the vector is a lexical
#: feature hash, not a semantic embedding, and a larger width would only make
#: the pretence more convincing without making retrieval better.
HEURISTIC_EMBEDDING_DIM = 256

_WORD_RE = re.compile(r"[a-z0-9+#._]+|[\u4e00-\u9fff]", re.IGNORECASE)
_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")

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
    """Tokenise for overlap scoring.

    CJK characters are kept as individual tokens — for Chinese text they are the
    meaningful unit, and dropping single characters (as a naive "length > 1"
    filter does for latin words) would empty the token set entirely and make
    every Chinese claim look unsupported.
    """
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

    Weighted towards coverage rather than symmetric similarity: the question is
    "is *this claim* supported by the evidence", so a long evidence document
    should not be penalised for containing extra material.
    """
    left_tokens = set(tokens(left))
    right_tokens = set(tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    jaccard = len(intersection) / len(left_tokens | right_tokens)
    coverage = len(intersection) / len(left_tokens)
    return round(0.25 * jaccard + 0.75 * coverage, 4)


def _ngrams(text: str, n: int = 3) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text.lower().strip())
    if len(cleaned) < n:
        return [cleaned] if cleaned else []
    return [cleaned[i : i + n] for i in range(len(cleaned) - n + 1)]


def heuristic_embedding(text: str, *, dim: int = HEURISTIC_EMBEDDING_DIM) -> list[float]:
    """Deterministic, L2-normalised feature-hash embedding.

    Character n-grams are hashed into ``dim`` buckets with a signed weight, then
    normalised. Texts that share vocabulary land near each other, which is enough
    for the zero-key retrieval path to be genuinely useful for near-duplicate and
    keyword-adjacent queries.
    """
    vector = [0.0] * dim
    grams = _ngrams(text) or [text]
    for gram in grams:
        digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


# ── Resume / document sections ───────────────────────────────────────────────

SECTION_HEADERS: Mapping[str, tuple[str, ...]] = {
    "education": ("教育", "学历", "education", "academic"),
    "experience": ("实习", "工作经历", "工作经验", "experience", "employment", "internship"),
    "project": ("项目", "project", "projects"),
    "achievement": ("获奖", "荣誉", "证书", "奖项", "award", "honor", "certificat", "competition"),
    "skill": ("技能", "专业技能", "skills", "technical skills"),
}

_DATE_RE = re.compile(r"(?P<year>20\d{2}|19\d{2})\s*[./年-]?\s*(?P<month>0?[1-9]|1[0-2])?")


def split_sections(text: str) -> dict[str, list[str]]:
    """Split resume-like text into candidate sections by header keywords."""
    sections: dict[str, list[str]] = {key: [] for key in SECTION_HEADERS}
    sections["_other"] = []
    current = "_other"

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()

        matched_header: str | None = None
        # A header is a short line containing a known header keyword.
        if len(line) <= 24:
            for key, keywords in SECTION_HEADERS.items():
                if any(keyword in lowered for keyword in keywords):
                    matched_header = key
                    break

        if matched_header:
            current = matched_header
            remainder = line
            for keyword in SECTION_HEADERS[matched_header]:
                if keyword in lowered:
                    remainder = line[lowered.index(keyword) + len(keyword) :].strip(" :：-—")
                    break
            if remainder:
                sections[current].append(remainder)
            continue

        sections[current].append(line)

    return sections


def bullets(lines: Sequence[str]) -> list[str]:
    """Strip list markers and drop fragments too short to be meaningful."""
    out: list[str] = []
    for line in lines:
        cleaned = re.sub(r"^[\-\u2022*·▪◦>\d.)\s]+", "", line).strip()
        if len(cleaned) >= 6:
            out.append(cleaned)
    return out


def first_date(text: str) -> str | None:
    """Best-effort ISO date from a line, keeping the source's own precision."""
    match = _DATE_RE.search(text)
    if not match:
        return None
    year = match.group("year")
    month = match.group("month")
    return f"{year}-{int(month):02d}-01" if month else f"{year}-01-01"
