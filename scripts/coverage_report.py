"""Core-domain coverage, measured and summarised without a coverage-serving service.

What this answers: *which parts of the product's own logic does the test suite actually execute?*
Not "what percentage of the repository is covered" — that number is dominated by generated
migrations, routers and Pydantic schemas, and optimising it produces tests for getters.

So the report has two layers:

* **core domain** — the modules where a wrong answer is a wrong answer for the user: the claim
  gate, the confidence arithmetic, the match scoring, retrieval, profile/JD parsing, the interview
  planner, and the accounting that reports what the AI cost. This is the number the phase gates on.
* **everything measured** — reported beside it for honesty, never used as the target.

Two runs are combined because the two suites exercise different halves: the AI core suite drives
the pure logic directly, and the API suite drives it through the services and the database. Running
them together in one process would work too, but the API suite needs its own environment (SQLite,
test mode) and mixing the two environments is how a coverage number becomes unreproducible.

Usage::

    python scripts/coverage_report.py             # both suites (~3 min), writes the artefacts
    python scripts/coverage_report.py --fast      # AI core only (~10 s)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS = REPO_ROOT / "reports"
COVERAGE_JSON = REPORTS / "coverage.json"
COVERAGE_XML = REPORTS / "coverage.xml"
SUMMARY_MD = REPORTS / "coverage-summary.md"
PYTHON = sys.executable

#: The modules whose behaviour the product is. A miss here is a claim this project cannot make.
CORE_SCOPE: dict[str, tuple[str, ...]] = {
    "claim gate & confidence": (
        "careerforge_ai/agents/validator.py",
        "careerforge_ai/agents/validator_decide.py",
        "careerforge_ai/parsing/claim_rules.py",
        "careerforge_ai/scoring/confidence.py",
    ),
    "job matching & scoring": (
        "careerforge_ai/scoring/match.py",
        "careerforge_ai/scoring/weights.py",
        "careerforge_ai/agents/job.py",
        "careerforge_ai/agents/match.py",
    ),
    "retrieval (RAG)": (
        "careerforge_ai/rag/retriever.py",
        "careerforge_ai/rag/lexical.py",
        "careerforge_ai/rag/store.py",
        "careerforge_ai/rag/fusion.py",
    ),
    "profile & JD parsing": (
        "careerforge_ai/parsing/skill_taxonomy.py",
        "careerforge_ai/parsing/tokenize.py",
    ),
    "interview orchestration": (
        "careerforge_ai/agents/interview/plan.py",
        "careerforge_ai/agents/interview/turns.py",
        "careerforge_ai/agents/interview/scorecard.py",
    ),
    "AI accounting & observability": (
        "careerforge_api/services/metering.py",
        "careerforge_api/services/observability_service.py",
    ),
}


def _run(command: list[str], *, env: dict[str, str], append: bool, label: str) -> None:
    flags = [
        "-m",
        "coverage",
        "run",
        "--append" if append else "--source=careerforge_ai,careerforge_api",
    ]
    print(f"  running {label} …", flush=True)
    result = subprocess.run(
        [PYTHON, *flags, "-m", "pytest", *command, "-q", "-p", "no:cacheprovider"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    tail = [line for line in result.stdout.strip().splitlines() if line.strip()][-1:] or [
        "(no output)"
    ]
    print(f"    {tail[0]}")
    if result.returncode != 0:
        # A failing suite is reported, not swallowed: coverage of a red suite is not a result.
        print(f"    suite exited {result.returncode}", file=sys.stderr)
        for line in result.stdout.strip().splitlines()[-12:]:
            print(f"      {line}", file=sys.stderr)


def _measure(*, fast: bool) -> None:
    env = dict(os.environ)
    env.update(
        {
            "USE_SQLITE": "true",
            "ENVIRONMENT": "test",
            "JWT_SECRET": "local-verification-secret-000000000000",
            "TEMP": str(REPO_ROOT / ".tmp"),
            "TMP": str(REPO_ROOT / ".tmp"),
        }
    )
    base = ["--basetemp", str(REPO_ROOT / ".pytest-tmp")]
    _run(
        ["packages/ai/tests", "evals/tests", *base],
        env=env,
        append=False,
        label="AI core + eval metric tests",
    )
    if not fast:
        _run(["apps/api/tests", *base], env=env, append=True, label="API integration tests")


def _summarise() -> dict[str, object]:
    payload = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
    # Coverage reports paths the way the interpreter saw them (`packages/ai/careerforge_ai/...`, with
    # backslashes on Windows), while the scope below is declared relative to each package root. The
    # first version of this function looked the declared paths up directly and silently reported
    # 0/0 for every area — a summary that says "0% covered" when the tests ran is worse than no
    # summary, so matching is by normalised suffix and a miss is reported.
    files: dict[str, dict[str, object]] = {
        str(path).replace("\\", "/"): entry for path, entry in payload["files"].items()
    }

    def find(relative: str) -> dict[str, object] | None:
        wanted = relative.replace("\\", "/").lstrip("./")
        exact = files.get(wanted)
        if exact is not None:
            return exact
        for path, entry in files.items():
            if path.endswith(f"/{wanted}") or path == wanted:
                return entry
        return None

    def stat(paths: tuple[str, ...]) -> dict[str, object]:
        total = covered = missing_files = 0
        rows = []
        for relative in paths:
            entry = find(relative)
            if entry is None:
                # A path that does not exist is a broken scope declaration, and silently counting it
                # as 0% would make the summary report a failure the tests never caused.
                missing_files += 1
                print(f"    scope path not measured: {relative}", file=sys.stderr)
                continue
            summary = entry["summary"]  # type: ignore[index]
            total += summary["num_statements"]  # type: ignore[index]
            covered += summary["covered_lines"]  # type: ignore[index]
            rows.append(
                {
                    "path": relative,
                    "statements": summary["num_statements"],  # type: ignore[index]
                    "covered": summary["covered_lines"],  # type: ignore[index]
                    "percent": round(summary["percent_covered"], 1),  # type: ignore[index]
                }
            )
        percent = round(covered / total * 100, 1) if total else 0.0
        return {
            "statements": total,
            "covered": covered,
            "percent": percent,
            "files": rows,
            "declared_but_missing": missing_files,
        }

    areas = {name: stat(paths) for name, paths in CORE_SCOPE.items()}
    core_total = sum(area["statements"] for area in areas.values())
    core_covered = sum(area["covered"] for area in areas.values())
    overall = payload["totals"]
    return {
        "areas": areas,
        "core": {
            "statements": core_total,
            "covered": core_covered,
            "percent": round(core_covered / core_total * 100, 1) if core_total else 0.0,
        },
        "everything_measured": {
            "statements": overall["num_statements"],
            "covered": overall["covered_lines"],
            "percent": round(overall["percent_covered"], 1),
        },
    }


def _render(summary: dict[str, object]) -> str:
    core = summary["core"]  # type: ignore[index]
    everything = summary["everything_measured"]  # type: ignore[index]
    lines = [
        "# Core-domain coverage",
        "",
        f"- **core domain: {core['percent']}%** "
        f"({core['covered']}/{core['statements']} statements)",  # type: ignore[index]
        f"- everything measured: {everything['percent']}% "  # type: ignore[index]
        f"({everything['covered']}/{everything['statements']} statements) — "
        "reported, never the target",
        "",
        "| area | files | statements | covered | % |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for name, area in summary["areas"].items():  # type: ignore[union-attr]
        lines.append(
            f"| {name} | {len(area['files'])} | {area['statements']} | {area['covered']} | "
            f"{area['percent']}% |"
        )
    lines += [
        "",
        "## Per file",
        "",
        "| file | statements | covered | % |",
        "| --- | ---: | ---: | ---: |",
    ]
    for area in summary["areas"].values():  # type: ignore[union-attr]
        for row in area["files"]:
            lines.append(
                f"| `{row['path']}` | {row['statements']} | {row['covered']} | {row['percent']}% |"
            )
    lines += [
        "",
        "Generated by `python scripts/coverage_report.py` from `reports/coverage.xml`; the numbers "
        "come from the real test suites (AI core + eval metrics, and the API integration suite).",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true", help="AI core tests only")
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="re-summarise the coverage data already collected instead of re-running the suites",
    )
    parser.add_argument(
        "--min-core",
        type=float,
        default=None,
        help="exit 2 when core-domain coverage is below this percentage (CI gate)",
    )
    args = parser.parse_args()

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / ".tmp").mkdir(exist_ok=True)
    if args.reuse and (REPO_ROOT / ".coverage").exists():
        print("reusing the coverage data already collected")
    else:
        print("measuring coverage:")
        _measure(fast=args.fast)

    for command, target in (
        (["json", "-o", str(COVERAGE_JSON)], COVERAGE_JSON),
        (["xml", "-o", str(COVERAGE_XML)], COVERAGE_XML),
    ):
        result = subprocess.run(
            [PYTHON, "-m", "coverage", *command], cwd=REPO_ROOT, capture_output=True, text=True
        )
        if not target.exists():
            print(f"coverage {command[0]} failed: {result.stderr.strip()}", file=sys.stderr)
            return 1

    summary = _summarise()
    SUMMARY_MD.write_text(_render(summary), encoding="utf-8", newline="\n")
    core = summary["core"]
    print(
        f"core domain: {core['percent']}% ({core['covered']}/{core['statements']}) → "
        f"{SUMMARY_MD.relative_to(REPO_ROOT)}"  # type: ignore[index]
    )
    for name, area in summary["areas"].items():  # type: ignore[union-attr]
        flag = "" if area["percent"] >= 75 else "  <-- below 75%"
        print(
            f"  {name:34s} {area['percent']:5.1f}%  ({area['covered']}/{area['statements']}){flag}"
        )

    # The declared scope must have been measured: `0/0` is not "100% covered", it is a broken scope.
    declared_missing = sum(
        area["declared_but_missing"]
        for area in summary["areas"].values()  # type: ignore[union-attr]
    )
    if declared_missing:
        print(
            f"{declared_missing} declared file(s) were not measured — the coverage scope is stale",
            file=sys.stderr,
        )
        return 1

    if args.min_core is not None and core["percent"] < args.min_core:  # type: ignore[index]
        print(
            f"core-domain coverage {core['percent']}% is below the {args.min_core}% gate",  # type: ignore[index]
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
