#!/usr/bin/env python
"""Guard the layering rule: the AI core must not know about the web or the ORM.

``packages/ai`` is what makes this project's AI testable and evaluable in memory
(ADR-022). That property is easy to lose with a single convenient import, so it
is enforced here and in pre-commit rather than left to code review.

Exits non-zero and prints the offending lines when the rule is broken.

Usage::

    python scripts/check_layering.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_CORE = REPO_ROOT / "packages" / "ai" / "careerforge_ai"

#: Modules the AI core must never import. `careerforge_api` is included so the
#: dependency direction stays strictly one-way.
FORBIDDEN_ROOTS = frozenset(
    {
        "fastapi",
        "starlette",
        "uvicorn",
        "sqlalchemy",
        "alembic",
        "asyncpg",
        "aiosqlite",
        "redis",
        "careerforge_api",
    }
)


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import: still inside the package, nothing to check.
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def main() -> int:
    if not AI_CORE.exists():
        print(f"skip: {AI_CORE} does not exist", file=sys.stderr)
        return 0

    violations: list[str] = []
    checked = 0

    for path in sorted(AI_CORE.rglob("*.py")):
        checked += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:  # a syntax error is a different problem
            violations.append(f"{path.relative_to(REPO_ROOT)}: could not parse ({exc})")
            continue
        for root in sorted(_imported_roots(tree) & FORBIDDEN_ROOTS):
            violations.append(
                f"{path.relative_to(REPO_ROOT)}: imports '{root}', which the AI core must not depend on"
            )

    if violations:
        print("Layering violation(s) detected:", file=sys.stderr)
        for line in violations:
            print(f"  - {line}", file=sys.stderr)
        print(
            "\nThe AI core talks to the outside world through ports "
            "(packages/ai/careerforge_ai/ports.py). Pass plain data objects in "
            "instead of importing a framework. See ADR-022.",
            file=sys.stderr,
        )
        return 1

    print(f"layering ok: {checked} files in packages/ai, no framework or ORM imports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
