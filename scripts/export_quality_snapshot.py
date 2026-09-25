"""Export the committed evaluation numbers into a TypeScript module the app can display.

Why not fetch them at runtime: the report is a file in the repository, not an endpoint. Serving it
would mean a new API surface whose only job is to echo a build artefact — and, worse, it would invite
the page to present *live* numbers, which is exactly the claim this project refuses to make. A
generated module keeps the provenance explicit: the snapshot states the commit it came from, and the
page prints that commit.

Why generated rather than hand-typed: a number typed into a component is a number nobody can check.
This script reads `reports/eval-report.json` + `reports/confidence-calibration.json` +
`reports/coverage-summary.md`, and refuses to write anything if a value it needs is missing.

Usage::

    python scripts/export_quality_snapshot.py
"""

from __future__ import annotations

import json
from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS = REPO_ROOT / "reports"
OUTPUT = REPO_ROOT / "apps" / "web" / "src" / "lib" / "quality-snapshot.ts"

#: (label, suite, metric, format, direction) — the numbers worth putting on screen.
#: Direction matters: `unsafe_support_rate` is good when it is *low*, and a UI that showed it
#: beside a green "higher is better" arrow would be lying about which way is healthy.
PICKS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "JD extraction · required-skill F1",
        "jd_extraction",
        "jd.required_skill_f1",
        "ratio",
        "higher",
    ),
    (
        "Evidence validation · macro F1",
        "evidence_validation",
        "evidence.macro_f1",
        "ratio",
        "higher",
    ),
    (
        "Unsafe support rate",
        "evidence_validation",
        "evidence.unsafe_support_rate",
        "ratio",
        "lower",
    ),
    ("RAG retrieval · Hit@5", "rag_retrieval", "retrieval.hit_at_5", "ratio", "higher"),
    ("RAG retrieval · MRR", "rag_retrieval", "retrieval.mrr", "ratio", "higher"),
    (
        "Interview · required-skill coverage",
        "interview_relevance",
        "interview.required_skill_coverage",
        "ratio",
        "higher",
    ),
)


def _coverage_percent() -> tuple[float, int, int]:
    """Read the core-domain line out of the generated markdown summary."""
    path = REPORTS / "coverage-summary.md"
    if not path.exists():
        raise SystemExit("reports/coverage-summary.md is missing — run scripts/coverage_report.py")
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"core domain: ([\d.]+)%\s*\**\s*\((\d+)/(\d+) statements\)", text.replace("**", "")
    )
    if not match:
        raise SystemExit("could not read the core-domain line from coverage-summary.md")
    return float(match.group(1)), int(match.group(2)), int(match.group(3))


def main() -> int:
    report = json.loads((REPORTS / "eval-report.json").read_text(encoding="utf-8"))
    calibration = json.loads((REPORTS / "confidence-calibration.json").read_text(encoding="utf-8"))
    coverage, covered_statements, total_statements = _coverage_percent()

    rows: list[str] = []
    for label, suite, metric, kind, direction in PICKS:
        value = report["suites"].get(suite, {}).get("metrics", {}).get(metric)
        if value is None:
            raise SystemExit(f"{suite}.{metric} is missing from the report — refusing to guess")
        rows.append(
            "  {\n"
            f"    label: {label!r},\n"
            f"    value: {value:.4f},\n"
            f"    kind: {kind!r},\n"
            f"    direction: {direction!r},\n"
            f"    suite: {suite!r},\n"
            f"    metric: {metric!r},\n"
            "  },"
        )

    body = "\n".join(rows)
    module = f"""/**
 * Evaluation snapshot — **generated, do not edit by hand**.
 *
 * Produced by `python scripts/export_quality_snapshot.py` from the committed reports, so every
 * number on the quality surface is traceable to an artefact in this repository. If a value is
 * missing from the report the generator fails instead of writing a default: a quality page that
 * shows a placeholder is worse than one that shows nothing.
 *
 * The commit is part of the data on purpose. These are *not* live production metrics, and the UI
 * must say so — they describe the evaluated commit, on the zero-key deterministic provider.
 */

export interface QualityMetric {{
  label: string;
  value: number;
  /** `ratio` renders as a percentage; kept explicit so a future `count` cannot be mis-formatted. */
  kind: 'ratio';
  /** Which way is healthy. `unsafe_support_rate` is good when it is low. */
  direction: 'higher' | 'lower';
  suite: string;
  metric: string;
}}

export interface QualitySnapshot {{
  commit: string;
  generatedAt: string;
  provider: string;
  providerChain: readonly string[];
  gitDirty: boolean;
  cases: number;
  suites: number;
  metrics: QualityMetric[];
  calibration: {{ ece: number; brier: number; cases: number }};
  coverage: {{ percent: number; covered: number; statements: number }};
}}

export const qualitySnapshot: QualitySnapshot = {{
  commit: {report["git_commit"]!r},
  generatedAt: {report["generated_at"]!r},
  provider: {report["provider"]!r},
  providerChain: {json.dumps(report["provider_chain"])},
  gitDirty: {str(bool(report.get("git_dirty"))).lower()},
  cases: {int(report["summary"]["cases"])},
  suites: {int(report["summary"]["suites_executed"])},
  metrics: [
{body}
  ],
  calibration: {{
    ece: {float(calibration["expected_calibration_error"]):.4f},
    brier: {float(calibration["brier_score"]):.4f},
    cases: {int(calibration["generated_from"]["cases"])},
  }},
  coverage: {{ percent: {coverage:.1f}, covered: {covered_statements}, statements: {total_statements} }},
}};
"""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(module, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} from commit {report['git_commit']}")
    for metric in PICKS:
        value = report["suites"][metric[1]]["metrics"][metric[2]]
        print(f"  {metric[0]:44s} {value:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
