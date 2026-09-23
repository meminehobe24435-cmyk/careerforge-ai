"""BM25 lexical scoring.

The lexical arm of hybrid retrieval exists for a domain-specific reason: job and
project vocabulary is full of exact technical nouns (``STM32F407``, ``heap_4``,
``CANopen``) that dense retrieval generalises away. Losing them means losing the
evidence a claim depends on.

BM25 rather than plain TF-IDF because document lengths in this corpus vary by two
orders of magnitude — a commit message next to a full README.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
import math

from careerforge_ai.parsing.tokenize import tokens

__all__ = ["Bm25Index", "BM25_K1", "BM25_B"]

#: Standard BM25 saturation and length-normalisation parameters.
BM25_K1 = 1.5
BM25_B = 0.75


class Bm25Index:
    """In-memory BM25 index over ``(id, text)`` pairs."""

    __slots__ = (
        "_avg_length",
        "_b",
        "_df",
        "_doc_tokens",
        "_ids",
        "_k1",
        "_lengths",
        "_term_freqs",
    )

    def __init__(
        self,
        documents: Mapping[str, str] | Iterable[tuple[str, str]],
        *,
        k1: float = BM25_K1,
        b: float = BM25_B,
    ) -> None:
        pairs = list(documents.items()) if isinstance(documents, Mapping) else list(documents)
        self._ids: list[str] = []
        self._term_freqs: list[Counter[str]] = []
        self._doc_tokens: dict[str, set[str]] = {}
        self._lengths: list[int] = []
        self._df: Counter[str] = Counter()
        self._k1 = k1
        self._b = b

        for doc_id, text in pairs:
            token_list = tokens(text)
            counts = Counter(token_list)
            self._ids.append(doc_id)
            self._term_freqs.append(counts)
            self._doc_tokens[doc_id] = set(counts)
            self._lengths.append(len(token_list))
            for term in counts:
                self._df[term] += 1

        self._avg_length = (sum(self._lengths) / len(self._lengths)) if self._lengths else 0.0

    def __len__(self) -> int:
        return len(self._ids)

    @property
    def document_count(self) -> int:
        return len(self._ids)

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        if df == 0:
            return 0.0
        # The +0.5 smoothing keeps a term that appears in every document from
        # contributing a negative weight.
        return math.log(1.0 + (self.document_count - df + 0.5) / (df + 0.5))

    def score(self, query: str, doc_id: str) -> float:
        """BM25 score of one document for ``query``."""
        try:
            position = self._ids.index(doc_id)
        except ValueError:
            return 0.0
        return self._score_at(query, position)

    def _score_at(self, query: str, position: int) -> float:
        counts = self._term_freqs[position]
        length = self._lengths[position]
        avg = self._avg_length or 1.0
        total = 0.0
        for term in set(tokens(query)):
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = self._idf(term)
            if idf <= 0:
                continue
            denominator = tf + self._k1 * (1.0 - self._b + self._b * (length / avg))
            total += idf * (tf * (self._k1 + 1.0)) / denominator
        return round(total, 6)

    def search(self, query: str, *, limit: int = 20) -> list[tuple[str, float]]:
        """Ranked ``(doc_id, score)`` pairs, best first, zero-scoring docs dropped."""
        query_terms = set(tokens(query))
        if not query_terms:
            return []

        # Candidate set is the union of documents containing at least one query
        # term, which avoids scoring the whole corpus for every query.
        candidates: set[int] = set()
        for term in query_terms:
            for position, counts in enumerate(self._term_freqs):
                if term in counts:
                    candidates.add(position)

        scored: list[tuple[str, float]] = []
        for position in candidates:
            value = self._score_at(query, position)
            if value > 0:
                scored.append((self._ids[position], value))

        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:limit]

    def contains(self, doc_id: str) -> bool:
        return doc_id in self._doc_tokens


def document_frequency(documents: Sequence[str], term: str) -> int:
    """How many documents contain ``term`` — used by the gap-frequency analysis."""
    return sum(1 for text in documents if term in set(tokens(text)))
