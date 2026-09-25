"""Suite: evidence validation — the claim gate, measured.

This is the evaluation the product's promise rests on, so it is worth being precise about what it
does and does not measure.

**What it runs.** Not the model in isolation: the *whole gate*, in the order it ships (ADR-014) —
deterministic rules, then hybrid retrieval over the case's own evidence, then the configured
provider's verdict, then the arithmetic in ``validator_decide``. A case is scored on the final
``ClaimValidation.status``, which is what a candidate would see. An evaluation that called the
provider directly would measure a component and call it a product.

**The caller contract it reproduces.** The rules phase runs *before* retrieval and reads
``evidence_text``, so a caller that supplies only a retriever has every technology in the claim
reported as unmentioned. Production passes both (``resume_service.validate``), and so does this
suite: the case's evidence is rendered the same way the API renders the candidate's material
(``title\\ntext`` blocks) and handed to the gate alongside the retriever. The first version of this
suite omitted it and produced ``support_recall`` 0.0000 — a number about a configuration the
product never uses. Retrieval then augments the rules rather than replacing them, which is what the
report's numbers describe.

**What the labels mean.** `supported` = the evidence carries the claim as written;
`partially_supported` = something in it is evidenced and something is not (a shared credit, a
weaker role, one of two technologies); `unsupported` = key parts have no support at all.

**Why one error is treated differently.** A false negative costs the candidate a review — the
gate says "we could not confirm this", they add a link, done. A false positive writes an invented
achievement onto a resume in the candidate's own voice, and it is the failure mode of every
generative resume tool on the market. So ``unsafe_support_rate`` (gold ≠ supported but the gate
said supported) and ``unsafe_numeric_support_rate`` (a fabricated measurement waved through) are
reported separately from accuracy and gated at 0.02 and 0.00 respectively.

**Confidence, not just labels.** Every case's final ``confidence`` is kept in the report, and
``evals/report.py`` turns those rows into the calibration artefact — reliability buckets, ECE and
Brier. That is the only way to answer "does 0.8 mean 80%?" with something other than an opinion.
"""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any
from uuid import UUID, uuid4

from careerforge_ai.agents.validator import ValidatorAgent
from careerforge_ai.graph import build_evidence_graph
from careerforge_ai.orchestrator import ExecutorSettings, WorkflowExecutor
from careerforge_ai.prompting.registry import load_prompt_registry
from careerforge_ai.providers.base import LLMProvider
from careerforge_ai.rag import HybridRetriever, InMemoryVectorStore, RetrievalDocument
from careerforge_ai.schemas.claim import ClaimValidation
from careerforge_ai.schemas.common import EvidenceKind, SourceAuthority, utcnow
from careerforge_ai.schemas.evidence import EvidenceItem, EvidenceLocator
from careerforge_ai.schemas.profile import CandidateProfile
from evals.metrics import classification_report, rate
from evals.report import SuiteOutcome

__all__ = ["SUITE_NAME", "suite_evidence_validation"]

SUITE_NAME = "evidence_validation"

#: The three labels, in the order the confusion matrix prints them. `supported` first because the
#: matrix is read as "gold rows, predicted columns" and the dangerous cell is the far one.
LABELS = ("supported", "partially_supported", "unsupported")

_MAX_RECORDED_FAILURES = 15

#: Evidence kinds the corpus uses. Kept here so a dataset row naming an unknown kind fails loudly
#: at load time instead of being silently skipped.
_KINDS = {kind.value for kind in EvidenceKind}


@dataclass(frozen=True)
class _Case:
    case_id: str
    claim: str
    gold: str
    evidence: list[dict[str, Any]]
    group: str
    has_unsupported_number: bool
    description: str
    notes: str = ""


def _placeholder_profile() -> CandidateProfile:
    """The minimum profile the graph builder needs.

    The builder computes per-item confidence from the *evidence* (kind, authority, locator,
    recency, corroboration); the profile is only there to hang the graph's skill nodes on, and this
    suite measures the claim gate rather than skill attribution.
    """
    return CandidateProfile(slug="eval-claim-candidate", headline="Eval candidate")


def parse_cases(rows: list[dict[str, Any]]) -> list[_Case]:
    cases: list[_Case] = []
    for row in rows:
        gold = str(row["expected_label"])
        if gold not in LABELS:
            raise ValueError(f"{row.get('id')}: unknown expected_label {gold!r}")
        for item in row.get("evidence", []):
            if item["kind"] not in _KINDS:
                raise ValueError(f"{row.get('id')}: unknown evidence kind {item['kind']!r}")
        cases.append(
            _Case(
                case_id=str(row["id"]),
                claim=str(row["claim"]),
                gold=gold,
                evidence=list(row.get("evidence", [])),
                group=str(row.get("group", "uncategorised")),
                has_unsupported_number=bool(row.get("has_unsupported_number", False)),
                description=str(row.get("description", "")),
                notes=str(row.get("notes", "")),
            )
        )
    return cases


async def suite_evidence_validation(
    provider: LLMProvider, rows: list[dict[str, Any]]
) -> SuiteOutcome:
    started = time.perf_counter()
    cases = parse_cases(rows)
    result = SuiteOutcome(
        name=SUITE_NAME,
        dataset="evidence_validation",
        dataset_version=str(rows[0].get("fixture_version", "v1")) if rows else "v1",
        cases=len(cases),
    )

    executor = WorkflowExecutor(
        provider=provider,
        prompts=load_prompt_registry(),
        settings=ExecutorSettings(max_retries=0, backoff_base_s=0.0),
    )
    agent = ValidatorAgent()

    predictions: list[str] = []
    golds: list[str] = []
    numeric_unsafe = numeric_total = 0
    by_group: dict[str, dict[str, float]] = {}
    rewrite_offered = rewrite_expected = 0
    degraded_cases = 0

    for case in cases:
        user_id = uuid4()
        # Evidence confidence is not decoration: `decide_phase` averages the *retrieved hits'*
        # confidence, so a corpus whose documents carry the default 0.0 makes every claim
        # unsupported regardless of how well it is evidenced. Production stores the score the
        # confidence engine computed, so this suite builds the same graph to obtain it — an
        # earlier version skipped this step and reported support_recall 0.0000, a number about
        # an evidence base no deployment has.
        items = [
            EvidenceItem(
                kind=EvidenceKind(item["kind"]),
                title=item["title"],
                snippet=item["text"],
                locator=EvidenceLocator(path=item["title"]),
                source_authority=SourceAuthority.CODE_OR_COMMIT,
                # Required by the schema and overwritten by the graph builder below; the builder
                # is the only thing allowed to *decide* a confidence, and feeding it a hand-picked
                # number here would defeat the point of computing it.
                confidence=0.0,
                occurred_at=utcnow(),
            )
            for item in case.evidence
        ]
        graph = build_evidence_graph(profile=_placeholder_profile(), evidence=items)
        confidence_by_title = {item.title: item.confidence for item in graph.evidence}

        retriever = HybridRetriever(vector_store=InMemoryVectorStore(), embedder=provider, top_k=8)
        if case.evidence:
            await retriever.index(
                [
                    RetrievalDocument(
                        evidence_id=UUID(item["evidence_id"]),
                        title=item["title"],
                        text=item["text"],
                        kind=EvidenceKind(item["kind"]),
                        confidence=confidence_by_title.get(item["title"], 0.0),
                    )
                    for item in case.evidence
                ],
                user_id=user_id,
            )
        # Rendered exactly as `resume_service._evidence_text` renders the candidate's material, so
        # the rules phase reads what it reads in production.
        material = "\n\n".join(f"{item['title']}\n{item['text']}".strip() for item in case.evidence)

        outcome = await agent.run(
            executor,
            claim=case.claim,
            evidence_text=material,
            retriever=retriever,
            user_id=user_id,
        )
        validation: ClaimValidation | None = outcome.value
        if validation is None:
            # The gate always decides; a `None` here means the workflow itself failed, and
            # recording it as `unsupported` would flatter the metrics by counting a crash as a
            # correct rejection. It is counted separately instead.
            degraded_cases += 1
            continue
        predicted = validation.status.value
        if predicted not in LABELS:
            raise ValueError(f"{case.case_id}: gate produced an unknown status {predicted!r}")

        predictions.append(predicted)
        golds.append(case.gold)

        bucket = by_group.setdefault(
            case.group, {"cases": 0.0, "correct": 0.0, "unsafe": 0.0, "confidence": 0.0}
        )
        bucket["cases"] += 1
        bucket["correct"] += 1 if predicted == case.gold else 0
        unsafe_here = case.gold != "supported" and predicted == "supported"
        bucket["unsafe"] += 1 if unsafe_here else 0
        bucket["confidence"] += float(validation.confidence)

        if case.has_unsupported_number:
            numeric_total += 1
            if predicted == "supported":
                numeric_unsafe += 1
                if len(result.failures) < _MAX_RECORDED_FAILURES:
                    result.failures.append(
                        {
                            "kind": "unsafe_numeric_support",
                            "case_id": case.case_id,
                            "claim": case.claim,
                            "confidence": float(validation.confidence),
                            "reasons": [reason.rule.value for reason in validation.reasons],
                        }
                    )

        if case.gold != "supported":
            rewrite_expected += 1
            if validation.safe_rewrite is not None:
                rewrite_offered += 1

        if predicted != case.gold and len(result.failures) < _MAX_RECORDED_FAILURES:
            result.failures.append(
                {
                    "kind": "misclassification",
                    "case_id": case.case_id,
                    "claim": case.claim,
                    "gold": case.gold,
                    "predicted": predicted,
                    "confidence": float(validation.confidence),
                    "independent_sources": validation.independent_source_count,
                    "reasons": [reason.rule.value for reason in validation.reasons],
                    "description": case.description,
                }
            )

        result.confidence_rows.append(
            {
                "case_id": case.case_id,
                "claim": case.claim,
                "confidence": float(validation.confidence),
                "predicted": predicted,
                "gold": case.gold,
                "correct": predicted == case.gold,
                "unsafe": unsafe_here,
                "group": case.group,
                "independent_sources": validation.independent_source_count,
            }
        )

    report = classification_report(golds, predictions, LABELS)
    supported = report.per_class["supported"]
    unsafe_support = sum(
        1
        for row in result.confidence_rows
        if row["gold"] != "supported" and row["predicted"] == "supported"
    )
    unsupported_total = sum(1 for gold in golds if gold != "supported")

    result.metrics = {
        "evidence.accuracy": report.accuracy,
        "evidence.macro_f1": report.macro_f1,
        "evidence.micro_f1": report.micro_f1,
        "evidence.supported_precision": supported.precision,
        "evidence.supported_recall": supported.recall,
        "evidence.supported_f1": supported.f1,
        "evidence.support_recall": supported.recall,
        "evidence.unsafe_support_rate": rate(unsafe_support, unsupported_total),
        "evidence.unsafe_numeric_support_rate": rate(numeric_unsafe, numeric_total),
        "evidence.partial_recall": report.per_class["partially_supported"].recall,
        "evidence.unsupported_recall": report.per_class["unsupported"].recall,
        "evidence.safer_rewrite_rate": rate(rewrite_offered, rewrite_expected),
        "evidence.degraded_case_rate": rate(degraded_cases, len(cases)),
    }
    result.counters = {
        "cases": len(cases),
        "scored_cases": len(predictions),
        "degraded_cases": degraded_cases,
        "gold_supported": sum(1 for gold in golds if gold == "supported"),
        "gold_partially_supported": sum(1 for gold in golds if gold == "partially_supported"),
        "gold_unsupported": sum(1 for gold in golds if gold == "unsupported"),
        "unsafe_supports": unsafe_support,
        "numeric_claims": numeric_total,
        "numeric_unsafe": numeric_unsafe,
        "true_positives": supported.tp,
        "false_positives": supported.fp,
        "false_negatives": supported.fn,
    }
    result.breakdown = {
        "confusion": report.confusion,
        "by_group": {
            key: {
                "cases": value["cases"],
                "accuracy": round(rate(value["correct"], value["cases"]), 4),
                "unsafe_supports": value["unsafe"],
                "mean_confidence": round(rate(value["confidence"], value["cases"]), 4),
            }
            for key, value in sorted(by_group.items())
        },
    }
    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result
