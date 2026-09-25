"""Suite: JD extraction.

Ported unchanged in behaviour from the pre-PHASE-12 ``evals/suites.py`` so the numbers stay
comparable across the refactor: the same corpus, the same comparisons, the same metric names.
The single addition is drift detection for the *dataset version*, so a future edit to the corpus
cannot silently change a benchmark number.

What it measures, and why those metrics:

* **required-skill precision/recall/F1** — the extraction's core job. Precision and recall are
  reported separately because the two failure modes are not equally bad: a missed requirement
  hides a gap from the candidate (bad), while an invented requirement sends them to study
  something the job never asked for (worse, because it is confidently wrong).
* **requirement-level accuracy** — "must have" vs "nice to have" is a promise about how hard to
  work for a skill, so confusing the two is a real error even when the skill set is right.
* **distractor leakage** — the corpus deliberately plants skills that appear in the posting but
  not in the requirements. Leakage means the extractor is reading proximity instead of meaning.
* **evidence grounding** — every extracted skill quotes a span that must appear verbatim in the
  source. This is the anti-fabrication metric for the extractor and it is gated at 1.00.
"""

from __future__ import annotations

import time
from typing import Any

from careerforge_ai.providers.base import ChatMessage, ChatRole, LLMProvider
from careerforge_ai.schemas.job import ExtractedJD
from evals.metrics import prf
from evals.report import SuiteOutcome
from evals.suites import canonical_skill

__all__ = ["SUITE_NAME", "suite_jd_extraction"]

SUITE_NAME = "jd_extraction"

_MAX_RECORDED_FAILURES = 12


async def suite_jd_extraction(provider: LLMProvider, rows: list[dict[str, Any]]) -> SuiteOutcome:
    started = time.perf_counter()
    result = SuiteOutcome(
        name=SUITE_NAME,
        dataset="jd_extraction",
        dataset_version=str(rows[0].get("fixture_version", "v1")) if rows else "v1",
        cases=len(rows),
    )

    role_hits = location_hits = company_hits = years_hits = education_hits = 0
    evidence_grounded = evidence_total = 0

    skill_stats: dict[str, dict[str, int]] = {
        level: {"tp": 0, "fp": 0, "fn": 0} for level in ("required", "preferred", "bonus")
    }
    level_correct = level_total = 0
    distractor_leaks = distractor_cases = 0
    unmapped_names: dict[str, int] = {}

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

        # Both directions are counted, because inventing a company for a posting that names none
        # is the error the rule exists to prevent.
        if (gold["company"] is None and parsed.company is None) or (
            gold["company"] and parsed.company and gold["company"] in parsed.company
        ):
            company_hits += 1

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
            "required": {canonical_skill(name) for name in gold["required_skills"]},
            "preferred": {canonical_skill(name) for name in gold["preferred_skills"]},
            "bonus": {canonical_skill(name) for name in gold["bonus_skills"]},
        }
        parsed_by_level: dict[str, set[str]] = {
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
                canonical = canonical_skill(skill.name)
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
            target = gold_by_level[level] - {None}
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

        distractors = {canonical_skill(name) for name in gold["not_required_skills"]}
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
    required_prf = prf(required["tp"], required["fp"], required["fn"])
    pref_f1 = prf(
        skill_stats["preferred"]["tp"],
        skill_stats["preferred"]["fp"],
        skill_stats["preferred"]["fn"],
    ).f1
    bonus_f1 = prf(
        skill_stats["bonus"]["tp"], skill_stats["bonus"]["fp"], skill_stats["bonus"]["fn"]
    ).f1

    result.metrics = {
        "jd.role_accuracy": role_hits / len(rows),
        "jd.location_accuracy": location_hits / len(rows),
        "jd.company_accuracy": company_hits / len(rows),
        "jd.years_accuracy": years_hits / len(rows),
        "jd.education_accuracy": education_hits / len(rows),
        "jd.required_skill_precision": required_prf.precision,
        "jd.required_skill_recall": required_prf.recall,
        "jd.required_skill_f1": required_prf.f1,
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
        "company_hits": company_hits,
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

    for label, accum in (("by_family", family_accum), ("by_language", language_accum)):
        rendered: dict[str, dict[str, float]] = {}
        for key, stats in accum.items():
            tp, fp, fn, samples = stats
            rendered[key] = {
                "cases": float(samples),
                "required_f1": round(prf(tp, fp, fn).f1, 4),
            }
        result.breakdown[label] = rendered

    if unmapped_names:
        result.failures.append(
            {
                "kind": "unmapped_skill_names",
                "detail": dict(sorted(unmapped_names.items(), key=lambda item: -item[1])[:10]),
            }
        )

    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result
