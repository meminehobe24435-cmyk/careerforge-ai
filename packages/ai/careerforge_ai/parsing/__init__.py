"""Parsing: turning messy real-world material into structured, checkable facts.

Nothing in this package calls a language model. Everything here is deterministic
by design, because the parse step decides *what the system believes exists*, and
a non-reproducible answer to that question would make every downstream score
non-reproducible too.
"""

from __future__ import annotations

from careerforge_ai.parsing.pii import (
    PiiFinding,
    PiiKind,
    contains_pii,
    redact_pii,
    scan_pii,
)
from careerforge_ai.parsing.skill_taxonomy import (
    ALIAS_INDEX,
    SKILL_BY_ID,
    SKILLS,
    TAXONOMY_VERSION,
    Skill,
    extract_skill_mentions,
    is_known_skill,
    normalize_skill,
    skill_categories,
)

__all__ = [
    "ALIAS_INDEX",
    "PiiFinding",
    "PiiKind",
    "SKILLS",
    "SKILL_BY_ID",
    "TAXONOMY_VERSION",
    "Skill",
    "contains_pii",
    "extract_skill_mentions",
    "redact_pii",
    "scan_pii",
    "is_known_skill",
    "normalize_skill",
    "skill_categories",
]
