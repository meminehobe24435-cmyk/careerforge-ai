"""Hybrid retrieval: dense + lexical search fused with Reciprocal Rank Fusion.

Filled in at PHASE 3. The reason both arms exist is domain-specific: job and
project vocabulary is full of exact technical nouns (``STM32F407``, ``heap_4``,
``CANopen``) that pure vector search generalises away, while intent-level queries
("multi-task real-time scheduling") need semantics that keyword search cannot
provide. See ADR-008.
"""

from __future__ import annotations

__all__: list[str] = []
