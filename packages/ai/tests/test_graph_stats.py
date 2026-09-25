"""``graph_stats``: the numbers on the evidence-graph summary strip.

Split from ``test_evidence_graph.py`` in PHASE 14 — that module had reached the 500-line guard, and
these two counts have their own reason to change: they are derived from whatever the view contains,
so "nothing was measured" and "zero was measured" are different statements about the same field.
"""

from __future__ import annotations

from uuid import uuid4

from careerforge_ai.graph import graph_stats
from careerforge_ai.schemas.common import GraphNodeType
from careerforge_ai.schemas.evidence import GraphNode


def test_an_empty_mean_is_null_rather_than_zero() -> None:
    """A graph in which nothing was scored reports ``None``, not ``0.0`` (PHASE 14).

    A node's confidence comes from the evidence behind it, so a candidate with a profile and no
    evidence has nodes and no confidences at all. ``mean_confidence: 0.0`` told a reader every node
    had been scored at zero — the opposite of "nothing has been scored yet". The two counts below
    stay ``0``, because "no node is high-confidence" is a true statement about such a view.
    """
    nodes = [
        GraphNode(id=uuid4(), type=GraphNodeType.CANDIDATE, label="Alex", confidence=None),
        GraphNode(id=uuid4(), type=GraphNodeType.SKILL, label="STM32", confidence=None),
    ]
    stats = graph_stats(nodes, [])

    assert stats["mean_confidence"] is None
    assert stats["high_confidence"] == 0
    assert stats["low_confidence"] == 0
    assert stats["nodes"] == 2


def test_a_measured_mean_is_a_number() -> None:
    """The other half of the pair: with one confidence present the mean is reported."""
    nodes = [
        GraphNode(id=uuid4(), type=GraphNodeType.SKILL, label="STM32", confidence=0.8),
        GraphNode(id=uuid4(), type=GraphNodeType.SKILL, label="CAN", confidence=None),
    ]
    stats = graph_stats(nodes, [])

    assert stats["mean_confidence"] == 0.8
    assert stats["high_confidence"] == 1
    assert stats["low_confidence"] == 0
