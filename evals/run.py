"""Evaluation runner.

Runs the suites in :mod:`evals.suites` against the **real** production code paths
(``careerforge_ai``), writes the report artefacts and prints a table.

Usage::

    python evals/run.py                                  # all suites, configured provider
    python evals/run.py --suite evidence_validation      # one suite
    python evals/run.py --provider heuristic             # same suites, a specific provider
    python evals/run.py --out reports/eval-report.json   # explicit artefact path
    python evals/run.py --json                           # machine-readable on stdout too

Artefacts (all generated, none hand-written):

* ``reports/eval-report.json`` — the machine-readable report (``schema_version`` 1.0)
* ``reports/eval-report.md`` — the same content for GitHub
* ``reports/confidence-calibration.json`` / ``.md`` — written whenever the evidence suite ran,
  because that is the suite whose verdicts carry a confidence

Exit codes, because CI has to be able to fail:

* ``0`` — every executed suite passed its **gate** thresholds
* ``2`` — at least one gate threshold was missed (the metrics refused to pass quietly)
* ``1`` — infrastructure failure: a dataset is missing, or a suite raised

Thresholds live in :mod:`evals.config` and each one says whether missing it is a gate or merely
reported. A quality metric the project has not earned yet is reported, never silently lowered.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "evals" / "datasets"
REPORTS_DIR = REPO_ROOT / "reports"
REPORT_PATH = REPORTS_DIR / "eval-report.json"
REPORT_MD_PATH = REPORTS_DIR / "eval-report.md"
CALIBRATION_PATH = REPORTS_DIR / "confidence-calibration.json"
CALIBRATION_MD_PATH = REPORTS_DIR / "confidence-calibration.md"

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "ai"))
sys.path.insert(0, str(REPO_ROOT / "evals"))

from careerforge_ai.config import Settings, get_settings  # noqa: E402
from careerforge_ai.prompting.registry import load_prompt_registry  # noqa: E402
from careerforge_ai.providers.factory import build_provider  # noqa: E402
from careerforge_ai.scoring.confidence import CONFIDENCE_FORMULA_VERSION  # noqa: E402
from evals.config import DEFAULT_BINS  # noqa: E402
from evals.report import (  # noqa: E402
    SCHEMA_VERSION,
    SuiteOutcome,
    build_report,
    calibration_artifacts,
    calibration_metrics,
    render_markdown,
)
from evals.suites import DATASET_FOR_SUITE, SUITES  # noqa: E402

#: Suite whose per-case confidence feeds the calibration artefact.
_CALIBRATED_SUITE = "evidence_validation"


def load_dataset(name: str) -> list[dict[str, Any]]:
    path = DATASET_DIR / f"{name}.jsonl"
    if not path.exists():
        raise SystemExit(f"dataset {name} is missing — run: python evals/generate_datasets.py")
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _dataset_manifest() -> dict[str, Any]:
    path = DATASET_DIR / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _git(*args: str) -> str:
    try:
        return (
            subprocess.run(
                ["git", *args],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            ).stdout.strip()
            or "unknown"
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover - git may be absent
        return "unknown"


async def run_suites(settings: Settings, suite_names: list[str]) -> dict[str, SuiteOutcome]:
    provider = build_provider(settings)
    registry = load_prompt_registry(settings.resolved_prompts_dir)
    if registry.warnings:
        print(f"prompt registry warnings: {'; '.join(registry.warnings)}", file=sys.stderr)

    manifest = _dataset_manifest().get("datasets", {})
    outcomes: dict[str, SuiteOutcome] = {}
    for name in suite_names:
        rows = load_dataset(DATASET_FOR_SUITE[name])
        outcome = await SUITES[name](provider, rows)
        # The manifest is the authority on the fixture version: a suite cannot report a version
        # the dataset file does not carry.
        declared = manifest.get(name, {}).get("fixture_version")
        if declared:
            outcome.dataset_version = str(declared)
        outcomes[name] = outcome
    return outcomes


def _print_table(outcomes: dict[str, SuiteOutcome]) -> None:
    print()
    for name, outcome in outcomes.items():
        head = (
            f"[{name}] {outcome.cases} cases · {outcome.duration_ms} ms · "
            f"dataset {outcome.dataset}@{outcome.dataset_version}"
        )
        print(head)
        print("-" * len(head))
        if outcome.skipped:
            print(f"  skipped: {outcome.skipped}\n")
            continue
        entries = outcome.threshold_entries()
        print(f"  {'metric':<44} {'value':>9}  {'threshold':>9}  status")
        for metric, value in sorted(outcome.metrics.items()):
            entry = entries.get(metric)
            if entry is None:
                print(f"  {metric:<44} {value:>9.4f}  {'—':>9}  measured")
                continue
            sign = "≥" if entry["direction"] == "min" else "≤"
            mark = "PASS" if entry["status"] == "pass" else "MISS"
            scope = "" if entry["severity"] == "gate" else "  (report only)"
            print(f"  {metric:<44} {value:>9.4f}  {sign}{entry['threshold']:>8.2f}  {mark}{scope}")
        print()
        gates = outcome.gate_failures()
        misses = outcome.reported_misses()
        if gates:
            print(f"  GATE FAILED: {', '.join(gates)}")
        if misses:
            print(f"  reported below threshold: {', '.join(misses)}")
        if gates or misses:
            print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append", choices=sorted(SUITES), default=None)
    parser.add_argument("--provider", default=None, help="override LLM_PROVIDER")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--out", default=str(REPORT_PATH), help="report path")
    parser.add_argument("--md-out", default=str(REPORT_MD_PATH), help="markdown report path")
    parser.add_argument(
        "--bins", type=int, default=DEFAULT_BINS, help="reliability buckets for calibration"
    )
    parser.add_argument(
        "--no-calibration",
        action="store_true",
        help="skip writing the calibration artefacts even when the evidence suite ran",
    )
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
        get_settings.cache_clear()

    settings = get_settings()
    suite_names = args.suite or list(SUITES)
    started_at = datetime.now(UTC)
    started = time.perf_counter()

    try:
        outcomes = asyncio.run(run_suites(settings, suite_names))
    except SystemExit:
        raise
    except Exception as exc:
        print(f"evaluation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    duration_ms = int((time.perf_counter() - started) * 1000)
    manifest = _dataset_manifest()

    # Calibration is computed *before* the report is built, because ECE and Brier belong in the
    # compared metric set and not only in the side artefact.
    #
    # They were missing from `metrics` until PHASE 14, which made them un-comparable: `compare.py`
    # carries explicit lower-is-better rules for the names `ece` and `brier`, so the tool was
    # written expecting these metrics in the report and nothing emitted them. A calibration change
    # could therefore not appear in a diff or fail a gate — the numbers were published in
    # `reports/confidence-calibration.md` and invisible to every automated check. Measured on the
    # release candidate: ECE 0.0316 and Brier 0.0904.
    calibrated = outcomes.get(_CALIBRATED_SUITE)
    calibration: tuple[dict[str, Any], str] | None = None
    if calibrated is not None and not args.no_calibration and calibrated.confidence_rows:
        payload, markdown = calibration_artifacts(calibrated, bins=args.bins)
        calibration = (payload, markdown)
        calibrated.metrics.update(calibration_metrics(payload))

    report = build_report(
        outcomes=list(outcomes.values()),
        provider=settings.llm_provider,
        provider_chain=settings.active_provider_chain(),
        model=getattr(settings, f"{settings.llm_provider}_model", None),
        git_commit=_git("rev-parse", "--short", "HEAD"),
        git_dirty=bool(_git("status", "--porcelain")),
        datasets=manifest.get("datasets", {}),
        dataset_caveat=str(manifest.get("note", "")),
        versions={
            "report_schema": SCHEMA_VERSION,
            "confidence_formula": CONFIDENCE_FORMULA_VERSION,
            "pricing": "pricing@1.0.0",
            "match": "match@1.0.0",
        },
        started_at=started_at,
        duration_ms=duration_ms,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    md_path = Path(args.md_out)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")

    calibration_written = False
    if calibration is not None:
        payload, markdown = calibration
        payload["git_commit"] = report["git_commit"]
        payload["generated_at"] = report["generated_at"]
        CALIBRATION_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        CALIBRATION_MD_PATH.write_text(markdown, encoding="utf-8", newline="\n")
        calibration_written = True

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_table(outcomes)
        print(
            f"report → {out_path.relative_to(REPO_ROOT)} · {md_path.relative_to(REPO_ROOT)}"
            + (f" · {CALIBRATION_PATH.relative_to(REPO_ROOT)}" if calibration_written else "")
        )

    failed = [
        f"{name}: {', '.join(outcome.gate_failures())}"
        for name, outcome in outcomes.items()
        if not outcome.passed
    ]
    if failed:
        print("\nGATE THRESHOLDS MISSED", file=sys.stderr)
        for line in failed:
            print(f"  {line}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
