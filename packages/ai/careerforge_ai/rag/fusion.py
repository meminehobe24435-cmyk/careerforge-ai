"""Reciprocal Rank Fusion.

Fusing two retrieval arms requires combining scores that are not comparable:
cosine similarity lives in ``[-1, 1]`` and BM25 is unbounded. Normalising them
against each other is fragile — the scale depends on the corpus and the query.

RRF sidesteps the problem entirely by using only *ranks*::

    score(d) = Σ_arms 1 / (k + rank_arm(d))

``k`` (60 by default) damps the influence of the very top ranks, which is what
makes the fusion stable across queries. This is the reason the project uses ranks
instead of scores, and it is worth being able to say so.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

__all__ = ["RRF_K", "reciprocal_rank_fusion", "fuse_with_ranks"]

#: Damping constant from the original RRF paper.
RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Mapping[str, Sequence[str]],
    *,
    k: int = RRF_K,
) -> dict[str, float]:
    """Fuse several ranked id lists into one score per id.

    Args:
        rankings: ``arm name → ids ordered best-first``. Ranks are 1-based.
        k: damping constant.
    """
    scores: dict[str, float] = {}
    for ids in rankings.values():
        for position, doc_id in enumerate(ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + position)
    return {doc_id: round(value, 8) for doc_id, value in scores.items()}


def fuse_with_ranks(
    rankings: Mapping[str, Sequence[str]],
    *,
    k: int = RRF_K,
) -> dict[str, tuple[float, dict[str, int]]]:
    """Like :func:`reciprocal_rank_fusion` but also returns each arm's rank.

    The per-arm ranks are what let the UI say *which* search found a piece of
    evidence, which is part of the product's explainability promise rather than a
    debugging nicety.
    """
    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}

    for arm, ids in rankings.items():
        for position, doc_id in enumerate(ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + position)
            ranks.setdefault(doc_id, {})[arm] = position

    return {doc_id: (round(value, 8), ranks.get(doc_id, {})) for doc_id, value in scores.items()}


def normalize_scores(scores: Mapping[str, float]) -> dict[str, float]:
    """Scale scores into ``[0, 1]`` by the maximum.

    Used for the display-level ``relevance`` on a hit. Explicitly *not* used for
    ranking, which is what RRF is for.
    """
    if not scores:
        return {}
    top = max(scores.values())
    if top <= 0:
        return dict.fromkeys(scores, 0.0)
    return {doc_id: round(value / top, 6) for doc_id, value in scores.items()}
