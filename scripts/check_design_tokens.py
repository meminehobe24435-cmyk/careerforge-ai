#!/usr/bin/env python
"""Guard the design-token rule: no raw colour values inside components.

The theme (dark-first with a light variant) is driven entirely by CSS variables.
One hard-coded ``#7c3aed`` is enough to break the light theme, the contrast
audit and the "not another purple AI gradient" brief — so it is checked in CI
rather than trusted to discipline (ADR-019).

Token definition files are exempt: they are where the values are supposed to live.

Usage::

    python scripts/check_design_tokens.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = (REPO_ROOT / "apps" / "web" / "src", REPO_ROOT / "packages" / "ui" / "src")

#: Files that legitimately define raw colour values.
ALLOWED_FILES = {"tokens.css", "globals.css", "theme.css"}

SCAN_SUFFIXES = {".tsx", ".ts", ".css"}

_HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b")
_RGB_RE = re.compile(r"\b(?:rgba?|hsla?)\s*\(", re.IGNORECASE)

#: Values that are structural rather than chromatic.
_ALLOWED_VALUES = {
    "#000",
    "#000000",
    "#fff",
    "#ffffff",
    "#fff0",
    "#0000",
}

_SKIP_DIR_PARTS = {"node_modules", ".next", "dist", "build", "__snapshots__"}


def _looks_like_colour_usage(line: str) -> bool:
    """Ignore comments, svg ``fill="none"`` and token references."""
    stripped = line.strip()
    if stripped.startswith(("//", "/*", "*", "<!--")):
        return False
    if "var(--" in stripped:
        return False
    return True


def main() -> int:
    violations: list[str] = []
    checked = 0

    for directory in SCAN_DIRS:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            if any(part in _SKIP_DIR_PARTS for part in path.parts):
                continue
            if path.name in ALLOWED_FILES:
                continue

            checked += 1
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if not _looks_like_colour_usage(line):
                    continue
                for match in _HEX_RE.finditer(line):
                    value = match.group(0).lower()
                    if value in _ALLOWED_VALUES:
                        continue
                    # Design tokens are written as hex inside ``tokens.css`` only.
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{number}: hard-coded colour {match.group(0)}"
                    )
                if _RGB_RE.search(line):
                    violations.append(
                        f"{path.relative_to(REPO_ROOT)}:{number}: hard-coded colour function"
                    )

    if violations:
        print("Design-token violation(s) detected:", file=sys.stderr)
        for line in violations:
            print(f"  - {line}", file=sys.stderr)
        print(
            "\nUse a token instead (e.g. text-secondary, bg-surface, border-default, "
            "text-evidence). New colours are added once, in styles/tokens.css. "
            "See the design system in docs/UI.md.",
            file=sys.stderr,
        )
        return 1

    print(f"design tokens ok: {checked} component files scanned, no raw colours")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
