#!/usr/bin/env python
"""Guard the 500-line rule.

Small files are the cheapest structural defence against the "one giant module"
failure mode, and the rule is only credible if something checks it.

Usage::

    python scripts/check_file_length.py            # check
    python scripts/check_file_length.py --list     # show the largest files
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

MAX_LINES = 500

SCAN_SUFFIXES = {".py", ".ts", ".tsx"}
SKIP_DIR_PARTS = {
    "node_modules",
    ".next",
    ".venv",
    "dist",
    "build",
    "alembic",
    "migrations",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    "data",
    "reports",
}

#: Files that are legitimately long because they are data, not logic.
ALLOWLIST = {
    "packages/ai/careerforge_ai/parsing/skill_taxonomy.py",  # the taxonomy itself
    "packages/ai/careerforge_ai/schemas/__init__.py",  # a re-export barrel
    "pnpm-lock.yaml",
}


def _iter_sources() -> list[Path]:
    out: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if any(part in SKIP_DIR_PARTS for part in path.parts):
            continue
        out.append(path)
    return out


def main() -> int:
    sources = _iter_sources()
    measured = [(len(path.read_text(encoding="utf-8").splitlines()), path) for path in sources]
    measured.sort(reverse=True)

    if "--list" in sys.argv:
        print(f"{'lines':>6}  file")
        for count, path in measured[:25]:
            print(f"{count:>6}  {path.relative_to(REPO_ROOT)}")
        return 0

    violations = [
        (count, path)
        for count, path in measured
        if count > MAX_LINES and str(path.relative_to(REPO_ROOT)).replace("\\", "/") not in ALLOWLIST
    ]

    if violations:
        print(f"Files over {MAX_LINES} lines:", file=sys.stderr)
        for count, path in violations:
            print(f"  - {path.relative_to(REPO_ROOT)}: {count} lines", file=sys.stderr)
        print(
            "\nSplit by responsibility rather than by line number: extract a module "
            "with a clear name and a single reason to change.",
            file=sys.stderr,
        )
        return 1

    longest = measured[0] if measured else (0, REPO_ROOT)
    print(
        f"file length ok: {len(measured)} files scanned, "
        f"longest is {longest[1].name} at {longest[0]} lines"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
