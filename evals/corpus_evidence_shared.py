"""Shared plumbing for the hand-authored evidence cases: stable ids and the row shape."""

from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

__all__ = ["FIXTURE_VERSION", "evidence_rows"]

FIXTURE_VERSION = "ev2.1"

#: Evidence kinds that exist in the schema. A typo here fails at generation time rather than
#: producing a case whose evidence silently never indexes.
_KINDS = frozenset(
    {
        "repo_file",
        "commit",
        "readme",
        "document_chunk",
        "experience",
        "project",
        "achievement",
        "manual",
        "llm_inference",
    }
)


def evidence_rows(
    case_id: str,
    claim: str,
    group: str,
    evidence: list[tuple[str, str, str]],
    description: str,
    label: str,
    *,
    quantified: bool = False,
) -> dict[str, Any]:
    """One dataset row: the case, its label, and stable evidence ids.

    Ids are derived from the case and the fragment position, so re-generating the dataset does not
    move a single id and a Recall@5 comparison across commits stays meaningful.
    """
    rendered = []
    for index, (kind, title, text) in enumerate(evidence):
        assert kind in _KINDS, f"{case_id}: unknown evidence kind {kind!r}"
        rendered.append(
            {
                "evidence_id": str(uuid5(NAMESPACE_URL, f"{case_id}:{index}:{title}")),
                "kind": kind,
                "title": title,
                "text": text,
            }
        )
    return {
        "id": case_id,
        "fixture_version": FIXTURE_VERSION,
        "claim": claim,
        "expected_label": label,
        "group": group,
        "description": description,
        "has_unsupported_number": quantified,
        "evidence": rendered,
    }
