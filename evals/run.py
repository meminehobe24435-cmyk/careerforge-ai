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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
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

sys.path.insert(0, str(REPO_ROOT / "packages" / "ai"))

from careerforge_ai.config import Settings, get_settings  # noqa: E402
from careerforge_ai.parsing.skill_taxonomy import normalize_skill  # noqa: E402
from careerforge_ai.prompting.registry import load_prompt_registry  # noqa: E402
from careerforge_ai.providers.base import ChatMessage, ChatRole, LLMProvider  # noqa: E402
from careerforge_ai.providers.factory import build_provider  # noqa: E402
from careerforge_ai.schemas.claim import ClaimLLMVerdict  # noqa: E402
from careerforge_ai.schemas.job import ExtractedJD  # noqa: E402

#: Targets the project holds itself to. Reported as reached or not reached.
TARGETS: dict[str, float] = {
    "jd.required_skill_f1": 0.85,
    "jd.distractor_leakage_rate": 0.05,
    "jd.evidence_grounding_rate": 1.00,
    "jd.role_accuracy": 0.90,
    "jd.years_accuracy": 0.90,
    "claim.numeric_rejection_rate": 1.00,
    "claim.over_support_rate": 0.05,
    "claim.support_recall": 0.85,
}

_MAX_RECORDED_FAILURES = 12


# ── plumbing ─────────────────────────────────────────────────────────────────


@dataclass
class SuiteResult:
    name: str
    samples: int
    metrics: dict[str, float] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    failures: list[dict[str, Any]] = field(default_factory=list)
    skipped: str | None = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "samples": self.samples,
            "metrics": {key: round(value, 6) for key, value in sorted(self.metrics.items())},
            "counters": dict(sorted(self.counters.items())),
            "breakdown": self.breakdown,
            "failures": self.failures,
            "skipped": self.skipped,
            "duration_ms": self.duration_ms,
        }


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


def _canonical(name: str) -> str | None:
    """Normalise an extracted skill name the same way the service layer does."""
    skill = normalize_skill(name)
    return skill.canonical_id if skill else None


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


# ── suite: JD extraction ─────────────────────────────────────────────────────


async def suite_jd_extraction(provider: LLMProvider, rows: list[dict[str, Any]]) -> SuiteResult:
    started = time.perf_counter()
    result = SuiteResult(name="jd_extraction", samples=len(rows))

    role_hits = location_hits = years_hits = education_hits = 0
    evidence_grounded = evidence_total = 0

    skill_stats: dict[str, dict[str, int]] = {
        level: {"tp": 0, "fp": 0, "fn": 0} for level in ("required", "preferred", "bonus")
    }
    level_correct = level_total = 0
    distractor_leaks = distractor_cases = 0
    unmapped_names: dict[str, int] = {}

    by_family: dict[str, dict[str, float]] = {}
    by_language: dict[str, dict[str, float]] = {}
    family_accum: dict[str, list[int]] = {}
    language_accum: dict[str, list[int]] = {}

    for row in rows:
        gold = row["gold"]
        text = row["text"]
        parsed: ExtractedJD = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content=text)],
            ExtractedJD,
            context={"source_text": text},
        )

        if gold["role"] and gold["role"].lower() in parsed.role.lower():
            role_hits += 1

        if (gold["location"] is None and parsed.location is None) or (
            gold["location"] and parsed.location and gold["location"] in parsed.location
        ):
            location_hits += 1

        if (
            gold["years_experience_min"] is not None
            and parsed.years_experience_min is not None
            and abs(gold["years_experience_min"] - parsed.years_experience_min) < 0.01
        ):
            years_hits += 1

        if (
            gold["education_requirement"]
            and parsed.education_requirement
            and gold["education_requirement"].lower() in parsed.education_requirement.lower()
        ):
            education_hits += 1

        gold_by_level = {
            "required": {_canonical(name) for name in gold["required_skills"]},
            "preferred": {_canonical(name) for name in gold["preferred_skills"]},
            "bonus": {_canonical(name) for name in gold["bonus_skills"]},
        }
        parsed_by_level = {
            "required": set(),
            "preferred": set(),
            "bonus": set(),
        }
        all_gold = set().union(*gold_by_level.values())
        all_gold.discard(None)

        for level, skills in (
            ("required", parsed.required_skills),
            ("preferred", parsed.preferred_skills),
            ("bonus", parsed.bonus_skills),
        ):
            for skill in skills:
                canonical = _canonical(skill.name)
                if canonical is None:
                    unmapped_names[skill.name] = unmapped_names.get(skill.name, 0) + 1
                    continue
                parsed_by_level[level].add(canonical)
                if skill.evidence:
                    evidence_total += 1
                    if skill.evidence.rstrip("…") in text:
                        evidence_grounded += 1

        all_parsed = set().union(*parsed_by_level.values())

        for level in ("required", "preferred", "bonus"):
            target = gold_by_level[level] - {None}  # type: ignore[operator]
            found = parsed_by_level[level]
            skill_stats[level]["tp"] += len(target & found)
            skill_stats[level]["fp"] += len(found - all_gold)
            skill_stats[level]["fn"] += len(target - found)

        level_correct += len(
            (gold_by_level["required"] & parsed_by_level["required"])
            | (gold_by_level["preferred"] & parsed_by_level["preferred"])
            | (gold_by_level["bonus"] & parsed_by_level["bonus"])
        )
        level_total += len(all_gold & all_parsed)

        distractors = {_canonical(name) for name in gold["not_required_skills"]}
        distractors.discard(None)
        if distractors:
            distractor_cases += 1
            if parsed_by_level["required"] & distractors:
                distractor_leaks += 1

        for bucket, key in ((family_accum, row["family"]), (language_accum, row["language"])):
            stats = bucket.setdefault(key, [0, 0, 0, 0])
            stats[0] += len(gold_by_level["required"] & parsed_by_level["required"])
            stats[1] += len(parsed_by_level["required"] - all_gold)
            stats[2] += len(gold_by_level["required"] - parsed_by_level["required"])
            stats[3] += 1

    required = skill_stats["required"]
    precision, recall, f1 = _prf(required["tp"], required["fp"], required["fn"])
    _, _, pref_f1 = _prf(
        skill_stats["preferred"]["tp"],
        skill_stats["preferred"]["fp"],
        skill_stats["preferred"]["fn"],
    )
    _, _, bonus_f1 = _prf(
        skill_stats["bonus"]["tp"], skill_stats["bonus"]["fp"], skill_stats["bonus"]["fn"]
    )

    result.metrics = {
        "jd.role_accuracy": role_hits / len(rows),
        "jd.location_accuracy": location_hits / len(rows),
        "jd.years_accuracy": years_hits / len(rows),
        "jd.education_accuracy": education_hits / len(rows),
        "jd.required_skill_precision": precision,
        "jd.required_skill_recall": recall,
        "jd.required_skill_f1": f1,
        "jd.preferred_skill_f1": pref_f1,
        "jd.bonus_skill_f1": bonus_f1,
        "jd.requirement_level_accuracy": (level_correct / level_total) if level_total else 0.0,
        "jd.distractor_leakage_rate": (distractor_leaks / distractor_cases)
        if distractor_cases
        else 0.0,
        "jd.evidence_grounding_rate": (evidence_grounded / evidence_total)
        if evidence_total
        else 0.0,
    }
    result.counters = {
        "role_hits": role_hits,
        "location_hits": location_hits,
        "years_hits": years_hits,
        "education_hits": education_hits,
        "required_true_positive": required["tp"],
        "required_false_positive": required["fp"],
        "required_false_negative": required["fn"],
        "distractor_cases": distractor_cases,
        "distractor_leaks": distractor_leaks,
        "skills_with_evidence": evidence_total,
        "skills_grounded_in_source": evidence_grounded,
        "unmapped_skill_names": sum(unmapped_names.values()),
    }

    for key, stats in family_accum.items():
        tp, fp, fn, samples = stats
        _, _, family_f1 = _prf(tp, fp, fn)
        by_family[key] = {"samples": float(samples), "required_f1": round(family_f1, 4)}
    for key, stats in language_accum.items():
        tp, fp, fn, samples = stats
        _, _, language_f1 = _prf(tp, fp, fn)
        by_language[key] = {"samples": float(samples), "required_f1": round(language_f1, 4)}
    result.breakdown = {"by_family": by_family, "by_language": by_language}

    if unmapped_names:
        result.failures.append(
            {
                "kind": "unmapped_skill_names",
                "detail": dict(sorted(unmapped_names.items(), key=lambda item: -item[1])[:10]),
            }
        )

    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result


# ── suite: claim validation ──────────────────────────────────────────────────


async def suite_claim_validation(provider: LLMProvider, rows: list[dict[str, Any]]) -> SuiteResult:
    started = time.perf_counter()
    result = SuiteResult(name="claim_validation", samples=len(rows))

    supported_total = supported_hits = 0
    unsupported_total = over_support = 0
    numeric_total = numeric_rejected = numeric_rejection_failures = 0
    safer_offered = safer_expected = 0

    by_kind: dict[str, dict[str, float]] = {}

    for row in rows:
        claim = row["claim"]
        evidence = row["evidence"]
        gold = row["gold"]

        verdict: ClaimLLMVerdict = await provider.structured_output(
            [ChatMessage(role=ChatRole.USER, content=claim)],
            ClaimLLMVerdict,
            context={"source_text": claim, "evidence": evidence},
        )

        kind_stats = by_kind.setdefault(gold["kind"], {"samples": 0.0, "supported_correct": 0.0})
        kind_stats["samples"] += 1

        if gold["supported"]:
            supported_total += 1
            if verdict.supported:
                supported_hits += 1
                kind_stats["supported_correct"] += 1
        else:
            unsupported_total += 1
            if verdict.supported:
                over_support += 1
                if len(result.failures) < _MAX_RECORDED_FAILURES:
                    result.failures.append(
                        {
                            "kind": "over_support",
                            "claim": claim,
                            "gold_kind": gold["kind"],
                            "evidence": [item["snippet"][:120] for item in evidence],
                            "reasoning": verdict.reasoning,
                        }
                    )

        if gold["has_unsupported_number"]:
            numeric_total += 1
            if not verdict.supported:
                numeric_rejected += 1
            else:
                numeric_rejection_failures += 1

        if gold["kind"] != "supported":
            safer_expected += 1
            if verdict.safer_formulation:
                safer_offered += 1

    result.metrics = {
        "claim.support_recall": (supported_hits / supported_total) if supported_total else 0.0,
        "claim.over_support_rate": (over_support / unsupported_total) if unsupported_total else 0.0,
        "claim.numeric_rejection_rate": (
            numeric_rejected / numeric_total if numeric_total else 1.0
        ),
        "claim.safer_rewrite_rate": (safer_offered / safer_expected) if safer_expected else 0.0,
    }
    result.counters = {
        "gold_supported": supported_total,
        "gold_supported_detected": supported_hits,
        "gold_unsupported": unsupported_total,
        "over_supported": over_support,
        "numeric_claims": numeric_total,
        "numeric_rejected": numeric_rejected,
        "numeric_rejection_failures": numeric_rejection_failures,
        "safer_rewrite_expected": safer_expected,
        "safer_rewrite_offered": safer_offered,
    }

    for kind, stats in by_kind.items():
        samples = int(stats["samples"])
        by_kind[kind] = {
            "samples": float(samples),
            "correct": stats["supported_correct"],
            "rate": round(stats["supported_correct"] / samples, 4) if samples else 0.0,
        }
    result.breakdown = {"by_gold_kind": by_kind}

    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result


# ── runner ───────────────────────────────────────────────────────────────────

SUITES: dict[str, Callable[[LLMProvider, list[dict[str, Any]]], Any]] = {
    "jd_extraction": suite_jd_extraction,
    "claim_validation": suite_claim_validation,
}

DATASET_FOR_SUITE: dict[str, str] = {
    "jd_extraction": "jd_extraction",
    "claim_validation": "claim_validation",
}


async def run_suites(settings: Settings, suite_names: Sequence[str]) -> dict[str, SuiteResult]:
    provider = build_provider(settings)
    registry = load_prompt_registry(settings.resolved_prompts_dir)
    if registry.warnings:
        print(f"prompt registry warnings: {'; '.join(registry.warnings)}", file=sys.stderr)

    results: dict[str, SuiteResult] = {}
    for name in suite_names:
        rows = load_dataset(DATASET_FOR_SUITE[name])
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
