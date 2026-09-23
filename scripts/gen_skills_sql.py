"""Generate ``infra/db/init/002_skills.sql`` from the AI core's skill taxonomy.

``docs/DATABASE.md`` §6 requires the ``skills`` seed and
``careerforge_ai.parsing.skill_taxonomy`` to be **isomorphic**, with CI asserting it.
The only sustainable way to keep two representations of 126 skills in agreement is to
generate one from the other, which is what this script does — and which
``apps/api/tests/test_skills_sql.py`` verifies by parsing the generated file back.

Usage (from the repository root)::

    .\\.venv\\Scripts\\python.exe scripts\\gen_skills_sql.py
    .\\.venv\\Scripts\\python.exe scripts\\gen_skills_sql.py --check   # CI: fail on drift
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "ai"))

from careerforge_ai.parsing.skill_taxonomy import (  # noqa: E402
    SKILLS,
    TAXONOMY_VERSION,
)

__all__ = ["TARGET", "render", "main"]

TARGET = REPO_ROOT / "infra" / "db" / "init" / "002_skills.sql"

HEADER = """\
-- CareerForge AI - skill taxonomy seed (PostgreSQL).
--
-- GENERATED FILE - DO NOT EDIT BY HAND.
--   regenerate:  python scripts/gen_skills_sql.py
--   verify:      python scripts/gen_skills_sql.py --check
--
-- Source of truth: packages/ai/careerforge_ai/parsing/skill_taxonomy.py
-- (docs/DATABASE.md section 6 requires the two to stay isomorphic; the API mirrors the
-- same list into the `skills` table at startup through skill_taxonomy_service, and
-- apps/api/tests/test_skills_sql.py parses this file to keep it honest.)
--
-- taxonomy version: {version}
-- skill count:      {count}
--
-- Executed by the postgres container on first initialisation
-- (docker-compose mounts infra/db/init as /docker-entrypoint-initdb.d).

INSERT INTO skills (id, canonical_id, display_name, category, aliases, is_active, created_at, updated_at)
VALUES
"""

FOOTER = """\
ON CONFLICT (canonical_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    category     = EXCLUDED.category,
    aliases      = EXCLUDED.aliases,
    is_active    = true,
    updated_at   = now();
"""


def _sql_literal(value: str) -> str:
    """Escape for a single-quoted SQL string (also doubles backslashes for safety)."""
    return value.replace("\\", "\\\\").replace("'", "''")


def render() -> str:
    rows: list[str] = []
    for skill in SKILLS:
        # `json.dumps` keeps the alias array valid JSON; single quotes are escaped for SQL.
        aliases = _sql_literal(json.dumps(list(skill.aliases), ensure_ascii=False))
        rows.append(
            f"    (gen_random_uuid(), "
            f"'{_sql_literal(skill.canonical_id)}', "
            f"'{_sql_literal(skill.display_name)}', "
            f"'{skill.category.value}', "
            f"'{aliases}'::jsonb, "
            f"true, now(), now())"
        )
    body = ",\n".join(rows)
    header = HEADER.format(version=TAXONOMY_VERSION, count=len(SKILLS))
    return f"{header}{body}\n{FOOTER}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the committed file differs from the generated one",
    )
    args = parser.parse_args(argv)

    generated = render()
    if args.check:
        existing = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if existing != generated:
            print(f"{TARGET} is out of date with the taxonomy; re-run without --check")
            return 1
        print(f"{TARGET} matches {TAXONOMY_VERSION} ({len(SKILLS)} skills)")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(generated, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET} ({len(SKILLS)} skills, {TAXONOMY_VERSION})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
