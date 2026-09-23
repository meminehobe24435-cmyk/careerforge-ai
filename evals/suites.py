"""Evaluation suites and their targets.

Each suite runs the real production code paths against a labelled dataset. The
runner in :mod:`evals.run` owns the CLI and the report artefact; the measurement
lives here so a metric can be read without wading through argument parsing.

Two kinds of target exist and they are treated differently on purpose:

* **Quality targets** are reported, never enforced. A number honestly below target
  is more useful than a build that hides it.
* **Safety targets** (:data:`SAFETY_TARGETS`) fail the run. Fabricated metrics
  being rejected, and extracted evidence being grounded in its source, are
  properties the product cannot ship without.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import time
from typing import Any
from uuid import UUID, uuid4

from careerforge_ai.parsing.skill_taxonomy import normalize_skill
from careerforge_ai.providers.base import ChatMessage, ChatRole, LLMProvider
from careerforge_ai.rag import HybridRetriever, InMemoryVectorStore, RetrievalDocument
from careerforge_ai.schemas.claim import ClaimLLMVerdict
from careerforge_ai.schemas.common import EvidenceKind
from careerforge_ai.schemas.job import ExtractedJD

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
    "retrieval.recall_at_5": 0.95,
    "retrieval.mrr": 0.85,
}

#: A miss here fails the run rather than being reported.
SAFETY_TARGETS: dict[str, float] = {
    "claim.numeric_rejection_rate": 1.00,
    "jd.evidence_grounding_rate": 1.00,
}

#: How many concrete input/response pairs to keep for debugging a regression.
_MAX_RECORDED_FAILURES = 12


def dataset_for(suite_name: str) -> str:
    """Dataset file stem used by a suite."""
    return DATASET_FOR_SUITE[suite_name]


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


async def suite_retrieval_recall(provider: LLMProvider, rows: list[dict[str, Any]]) -> SuiteResult:
    """Measure Recall@5 and MRR of the hybrid retriever.

    Runs the real retriever against a corpus whose relevant ids are known by
    construction, and reports both query styles separately — a single blended
    number would hide the fact that the lexical arm carries exact identifiers
    while the dense arm carries phrasing.
    """
    started = time.perf_counter()
    result = SuiteResult(name="retrieval", samples=sum(len(row["queries"]) for row in rows))

    top_1_hits = top_5_hits = 0
    reciprocal_rank_total = 0.0
    query_total = 0
    by_type: dict[str, dict[str, float]] = {}

    for row in rows:
        user_id = uuid4()
        retriever = HybridRetriever(vector_store=InMemoryVectorStore(), embedder=provider, top_k=5)
        await retriever.index(
            [
                RetrievalDocument(
                    evidence_id=UUID(document["evidence_id"]),
                    title=document["title"],
                    text=document["text"],
                    kind=EvidenceKind(document["kind"]),
                )
                for document in row["documents"]
            ],
            user_id=user_id,
        )

        for query_row in row["queries"]:
            gold = {UUID(gold_id) for gold_id in query_row["gold_ids"]}
            outcome = await retriever.retrieve(query_row["query"], user_id=user_id, top_k=5)
            ranked = [hit.evidence_id for hit in outcome.hits]
            query_total += 1

            bucket = by_type.setdefault(
                query_row["type"], {"queries": 0.0, "top1": 0.0, "top5": 0.0, "rr": 0.0}
            )
            bucket["queries"] += 1

            if ranked and ranked[0] in gold:
                top_1_hits += 1
                bucket["top1"] += 1

            found = len(gold & set(ranked[:5]))
            if found == len(gold):
                top_5_hits += 1
                bucket["top5"] += 1

            first_rank = next((index + 1 for index, doc in enumerate(ranked) if doc in gold), None)
            if first_rank is not None:
                reciprocal_rank_total += 1.0 / first_rank
                bucket["rr"] += 1.0 / first_rank
            elif len(result.failures) < _MAX_RECORDED_FAILURES:
                result.failures.append(
                    {
                        "kind": "retrieval_miss",
                        "query": query_row["query"],
                        "query_type": query_row["type"],
                        "gold_topic": query_row["topic"],
                        "returned": [hit.title for hit in outcome.hits],
                    }
                )

    result.metrics = {
        "retrieval.recall_at_1": (top_1_hits / query_total) if query_total else 0.0,
        "retrieval.recall_at_5": (top_5_hits / query_total) if query_total else 0.0,
        "retrieval.mrr": (reciprocal_rank_total / query_total) if query_total else 0.0,
    }
    result.counters = {
        "queries": query_total,
        "recall_at_1_hits": top_1_hits,
        "recall_at_5_hits": top_5_hits,
    }
    result.breakdown = {
        "by_query_type": {
            key: {
                "queries": value["queries"],
                "recall_at_1": round(value["top1"] / value["queries"], 4)
                if value["queries"]
                else 0.0,
                "recall_at_5": round(value["top5"] / value["queries"], 4)
                if value["queries"]
                else 0.0,
                "mrr": round(value["rr"] / value["queries"], 4) if value["queries"] else 0.0,
            }
            for key, value in by_type.items()
        }
    }
    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result


SUITES: dict[str, Callable[[LLMProvider, list[dict[str, Any]]], Any]] = {
    "jd_extraction": suite_jd_extraction,
    "claim_validation": suite_claim_validation,
    "retrieval_recall": suite_retrieval_recall,
}

DATASET_FOR_SUITE: dict[str, str] = {
    "jd_extraction": "jd_extraction",
    "claim_validation": "claim_validation",
    "retrieval_recall": "retrieval",
}
