"""Evaluation runner.

Runs measurable suites against the **real** production code paths
(``careerforge_ai``), writes ``reports/eval-report.json`` and prints a table.

Design rules:

* A suite never reimplements the thing it measures. It calls the same provider and
  the same normalisation the API calls.
* Every metric is reported with its sample size, and targets are compared
  honestly — an unmet target is printed as unmet.
* Failures are recorded with the input that produced them, so a regression can be
  reproduced rather than guessed at.

Usage::

    python evals/run.py                          # all suites, configured provider
    python evals/run.py --suite jd_extraction
    python evals/run.py --provider deepseek      # same suites, a real model
    python evals/run.py --json                   # machine-readable only
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / "evals" / "datasets"
REPORTS_DIR = REPO_ROOT / "reports"
REPORT_PATH = REPORTS_DIR / "eval-report.json"

sys.path.insert(0, str(REPO_ROOT / "packages" / "ai"))

from suites import SUITES, TARGETS, SuiteResult, dataset_for  # noqa: E402

from careerforge_ai.config import Settings, get_settings  # noqa: E402
from careerforge_ai.prompting.registry import load_prompt_registry  # noqa: E402
from careerforge_ai.providers.factory import build_provider  # noqa: E402

_MAX_RECORDED_FAILURES = 12


# ── plumbing ─────────────────────────────────────────────────────────────────


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


def _git_sha() -> str:
    try:
        return (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
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


# ── suite: JD extraction ─────────────────────────────────────────────────────


# ── suite: claim validation ──────────────────────────────────────────────────


# ── runner ───────────────────────────────────────────────────────────────────


async def run_suites(settings: Settings, suite_names: Sequence[str]) -> dict[str, SuiteResult]:
    provider = build_provider(settings)
    registry = load_prompt_registry(settings.resolved_prompts_dir)
    if registry.warnings:
        print(f"prompt registry warnings: {'; '.join(registry.warnings)}", file=sys.stderr)

    results: dict[str, SuiteResult] = {}
    for name in suite_names:
        rows = load_dataset(dataset_for(name))
        results[name] = await SUITES[name](provider, rows)
    return results


def _print_table(results: dict[str, SuiteResult]) -> None:
    print()
    print(f"{'metric':<42} {'value':>9}  {'target':>8}  status")
    print("-" * 78)
    for suite_name, result in results.items():
        print(f"[{suite_name}] {result.samples} samples, {result.duration_ms} ms")
        if result.skipped:
            print(f"  skipped: {result.skipped}")
            continue
        for metric, value in sorted(result.metrics.items()):
            target = TARGETS.get(metric)
            if target is None:
                print(f"  {metric:<40} {value:>9.4f}")
                continue
            # Lower is better for rates that describe an error.
            lower_is_better = (
                metric.endswith(("_rate", "_leakage_rate")) and "rejection" not in metric
            )
            ok = value <= target if lower_is_better else value >= target
            status = "PASS" if ok else "MISS"
            print(f"  {metric:<40} {value:>9.4f}  {target:>8.2f}  {status}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append", choices=sorted(SUITES), default=None)
    parser.add_argument("--provider", default=None, help="override LLM_PROVIDER")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--out", default=str(REPORT_PATH))
    args = parser.parse_args()

    if args.provider:
        os.environ["LLM_PROVIDER"] = args.provider
        get_settings.cache_clear()

    settings = get_settings()
    suite_names = args.suite or list(SUITES)

    import asyncio

    results = asyncio.run(run_suites(settings, suite_names))

    report = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "gitSha": _git_sha(),
        "provider": settings.llm_provider,
        "providerChain": settings.active_provider_chain(),
        "model": getattr(settings, f"{settings.llm_provider}_model", None),
        "pricingTableVersion": "pricing@1.0.0",
        "confidenceFormula": "confidence@1.0.0",
        "matchAlgorithm": "match@1.0.0",
        "datasets": _dataset_manifest().get("datasets", {}),
        "datasetCaveat": _dataset_manifest().get("note", ""),
        "targets": TARGETS,
        "suites": {name: result.to_dict() for name, result in results.items()},
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_table(results)
        print(f"report written to {out_path.relative_to(REPO_ROOT)}")

    # Non-zero exit only when a *safety* target is missed. Quality targets are
    # reported, not enforced: a number that is honestly below target is more
    # useful than a build that hides it.
    safety_metrics = {
        "claim.numeric_rejection_rate": 1.00,
        "jd.evidence_grounding_rate": 1.00,
    }
    for result in results.values():
        for metric, required in safety_metrics.items():
            if metric in result.metrics and result.metrics[metric] + 1e-9 < required:
                print(
                    f"SAFETY TARGET MISSED: {metric} = {result.metrics[metric]:.4f}",
                    file=sys.stderr,
                )
                return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
