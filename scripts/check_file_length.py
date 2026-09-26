#!/usr/bin/env python
"""Guard the 500-line rule.

Small files are the cheapest structural defence against the "one giant module"
failure mode, and the rule is only credible if something checks it.

The scan covers the repository's own source (`.py`, `.ts`, `.tsx`) and deliberately excludes build
output, caches, local scratch and the generated Alembic migrations — the last of those because a
migration's length is a property of its schema change, not of somebody's module design. The count this
prints is therefore "tracked source minus the migrations" and should reconcile with
`git ls-files "*.py" "*.ts" "*.tsx"`: 542 tracked against 532 scanned at the time of writing.

Usage::

    python scripts/check_file_length.py            # check
    python scripts/check_file_length.py --list     # show the largest files
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

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
    ".mypy_cache",
    ".pytest_cache",
    "data",
    "reports",
    # Local scratch and generated trees. They are gitignored, so counting them made the reported
    # "files scanned" a number about this machine rather than about the repository — and a copy of a
    # package left in `.tmp/` was being scanned as if it were source.
    ".git",
    ".tmp",
    ".pytest-tmp",
    ".pytest-p14",
    "coverage",
    "test-results",
    "playwright-report",
}

#: Files that are legitimately long because they are data, not logic.
ALLOWLIST = {
    "packages/ai/careerforge_ai/parsing/skill_taxonomy.py",  # the taxonomy itself
    "packages/ai/careerforge_ai/schemas/__init__.py",  # a re-export barrel
    "pnpm-lock.yaml",
}


def _iter_sources() -> list[Path]:
    """Every source file under the repository, with build output pruned rather than filtered.

    `rglob("*")` used to enumerate first and filter afterwards, which is too late: it descends into
    every directory before the `SKIP_DIR_PARTS` check can skip it, and descending into
    `apps/web/.next/standalone/**/node_modules` raises `PermissionError` on Windows from a pnpm symlink
    before any filter runs. That became reachable the moment the web build started emitting standalone
    output (`output: 'standalone'`, needed by the image), so a guard documented in the README crashed
    for anyone who had built the web app. Pruning during the walk fixes the crash and stops the scanner
    from walking tens of thousands of dependency files.
    """
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT, onerror=lambda _: None):
        dirnames[:] = [name for name in dirnames if name not in SKIP_DIR_PARTS]
        for name in filenames:
            path = Path(dirpath) / name
            if path.suffix in SCAN_SUFFIXES:
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
        if count > MAX_LINES
        and str(path.relative_to(REPO_ROOT)).replace("\\", "/") not in ALLOWLIST
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
