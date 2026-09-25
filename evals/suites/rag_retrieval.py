"""Suite: RAG retrieval quality.

The question this suite answers is *"can the retriever find the evidence that belongs to a
query?"* — not "did the endpoint return something". The corpus is built so the relevant document
ids are known by construction, which is what makes precision-style metrics possible at all.

Three arms are measured, all through public API:

* **hybrid** — the production pipeline (`HybridRetriever.retrieve`), the number that describes
  what a user gets;
* **keyword** — the same call with ``semantic_weight_enabled=False``, i.e. BM25 alone;
* **dense** — the vector store queried directly. The pipeline has no dense-only switch, so the
  arm is measured against the same store the pipeline fills; the report says so rather than
  pretending it is the same code path.

Two metrics, because they disagree in a way that matters:

* **Hit@k** — is *a* relevant document in the top k? This is the user-facing question ("did I get
  something useful").
* **Recall@5** — what *share* of the relevant set made the top 5? A query with four relevant
  documents can score Hit@5 = 1.0 while returning only one of them, and an evaluation that
  reported only Hit@k would never notice.

MRR adds the ordering question: a retriever that finds everything but buries it at rank 5 is
worse for a UI that shows three results.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from careerforge_ai.providers.base import LLMProvider
from careerforge_ai.rag import HybridRetriever, InMemoryVectorStore, RetrievalDocument
from careerforge_ai.schemas.common import EvidenceKind
from evals.metrics import hit_at_k, rate, recall_at_k, reciprocal_rank
from evals.report import SuiteOutcome

__all__ = ["SUITE_NAME", "suite_rag_retrieval"]

SUITE_NAME = "rag_retrieval"

#: k values reported. 1 answers "is the best result right", 3 matches what the UI shows, 5 is the
#: depth the claim gate retrieves at.
_K_VALUES = (1, 3, 5)
_TOP_K = 5
_MAX_RECORDED_FAILURES = 12


def _empty_arm() -> dict[str, float]:
    return {"queries": 0.0, "hit1": 0.0, "hit3": 0.0, "hit5": 0.0, "recall5": 0.0, "rr": 0.0}


async def suite_rag_retrieval(provider: LLMProvider, rows: list[dict[str, Any]]) -> SuiteOutcome:
    started = time.perf_counter()
    result = SuiteOutcome(
        name=SUITE_NAME,
        dataset="rag_retrieval",
        dataset_version=str(rows[0].get("fixture_version", "v1")) if rows else "v1",
        cases=sum(len(row["queries"]) for row in rows),
    )

    arms = {"hybrid": _empty_arm(), "keyword": _empty_arm(), "dense": _empty_arm()}
    by_type: dict[str, dict[str, float]] = {}
    fusion_wins = fusion_losses = 0
    dense_available = True

    for row in rows:
        user_id = uuid4()
        store = InMemoryVectorStore()
        documents = [
            RetrievalDocument(
                evidence_id=UUID(document["evidence_id"]),
                title=document["title"],
                text=document["text"],
                kind=EvidenceKind(document["kind"]),
            )
            for document in row["documents"]
        ]
        retriever = HybridRetriever(vector_store=store, embedder=provider, top_k=_TOP_K)
        await retriever.index(documents, user_id=user_id)
        ids_by_uuid = {str(document.evidence_id): document.title for document in documents}

        for query_row in row["queries"]:
            gold = {str(gold_id) for gold_id in query_row["gold_ids"]}
            bucket = by_type.setdefault(query_row["type"], _empty_arm())

            hybrid = await retriever.retrieve(query_row["query"], user_id=user_id, top_k=_TOP_K)
            fused_ranked = [str(hit.evidence_id) for hit in hybrid.hits]
            keyword = await retriever.retrieve(
                query_row["query"], user_id=user_id, top_k=_TOP_K, semantic_weight_enabled=False
            )
            keyword_ranked = [str(hit.evidence_id) for hit in keyword.hits]
            dense_ranked: list[str] = []
            try:
                embedding = await provider.embed([query_row["query"]])
                vector = embedding.vectors[0] if embedding.vectors else []
                dense_hits = await store.search(vector, user_id=user_id, limit=_TOP_K)
                dense_ranked = [str(hit.owner_id) for hit in dense_hits]
            except Exception:
                dense_available = False

            for arm_name, ranked in (
                ("hybrid", fused_ranked),
                ("keyword", keyword_ranked),
                ("dense", dense_ranked),
            ):
                if arm_name == "dense" and not dense_available:
                    continue
                _record(arms[arm_name], ranked, gold)
                if arm_name == "hybrid":
                    _record(bucket, ranked, gold)

            hybrid_hit = hit_at_k(fused_ranked, gold, _TOP_K)
            keyword_hit = hit_at_k(keyword_ranked, gold, _TOP_K)
            if hybrid_hit and not keyword_hit:
                fusion_wins += 1
            elif keyword_hit and not hybrid_hit:
                fusion_losses += 1

            if not hybrid_hit and len(result.failures) < _MAX_RECORDED_FAILURES:
                result.failures.append(
                    {
                        "kind": "retrieval_miss",
                        "query": query_row["query"],
                        "query_type": query_row["type"],
                        "gold_topic": query_row["topic"],
                        "returned": [ids_by_uuid.get(doc_id, doc_id) for doc_id in fused_ranked],
                    }
                )

    queries = arms["hybrid"]["queries"]
    result.metrics = {
        "retrieval.hit_at_1": rate(arms["hybrid"]["hit1"], queries),
        "retrieval.hit_at_3": rate(arms["hybrid"]["hit3"], queries),
        "retrieval.hit_at_5": rate(arms["hybrid"]["hit5"], queries),
        "retrieval.recall_at_5": rate(arms["hybrid"]["recall5"], queries),
        "retrieval.mrr": rate(arms["hybrid"]["rr"], queries),
        "retrieval.keyword_hit_at_5": rate(arms["keyword"]["hit5"], arms["keyword"]["queries"]),
        "retrieval.dense_hit_at_5": rate(arms["dense"]["hit5"], arms["dense"]["queries"])
        if dense_available
        else 0.0,
    }
    result.counters = {
        "queries": int(queries),
        "documents": sum(len(row["documents"]) for row in rows),
        "hybrid_top5_hits": int(arms["hybrid"]["hit5"]),
        "keyword_top5_hits": int(arms["keyword"]["hit5"]),
        "dense_top5_hits": int(arms["dense"]["hit5"]),
        "fusion_wins": fusion_wins,
        "fusion_losses": fusion_losses,
        "dense_arm_available": int(dense_available),
    }
    result.breakdown = {
        "by_query_type": {
            key: {
                "queries": value["queries"],
                "hit_at_1": round(rate(value["hit1"], value["queries"]), 4),
                "hit_at_3": round(rate(value["hit3"], value["queries"]), 4),
                "hit_at_5": round(rate(value["hit5"], value["queries"]), 4),
                "mrr": round(rate(value["rr"], value["queries"]), 4),
            }
            for key, value in by_type.items()
        },
        "by_arm": {
            arm: {
                "queries": data["queries"],
                "hit_at_1": round(rate(data["hit1"], data["queries"]), 4),
                "hit_at_5": round(rate(data["hit5"], data["queries"]), 4),
                "mrr": round(rate(data["rr"], data["queries"]), 4),
            }
            for arm, data in arms.items()
        },
    }
    result.duration_ms = int((time.perf_counter() - started) * 1000)
    return result


def _record(bucket: dict[str, float], ranked: list[str], gold: set[str]) -> None:
    bucket["queries"] += 1
    for k in _K_VALUES:
        if hit_at_k(ranked, gold, k):
            bucket[f"hit{k}"] += 1
    bucket["recall5"] += recall_at_k(ranked, gold, _TOP_K)
    bucket["rr"] += reciprocal_rank(ranked, gold)
