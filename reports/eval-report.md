# Evaluation report

- schema `1.0` · generated `2026-09-26T04:33:50.074915+00:00`
- commit `da7ddb6` (working tree dirty)
- provider `heuristic` × chain heuristic
- suites 4/4 executed · cases **242** · gated pass **4** / fail **0** · reported misses 0

> Controlled benchmark with exact ground truth. The JD and retrieval corpora are generated (real postings carry no labels); the evidence and interview cases are hand-authored. Treat these numbers as indicators of behaviour on this corpus, not as market-representative accuracy.

| suite | cases | gated | reported misses | duration |
| --- | ---: | --- | --- | ---: |
| `jd_extraction` | 120 | PASS | — | 412 ms |
| `evidence_validation` | 60 | PASS | — | 277 ms |
| `rag_retrieval` | 59 | PASS | — | 41 ms |
| `interview_relevance` | 3 | PASS | — | 27 ms |

## jd_extraction

Dataset `jd_extraction` @ `jd1.0` · 120 cases · 412 ms

| metric | value | threshold | status |
| --- | ---: | --- | --- |
| `jd.bonus_skill_f1` | 0.7758 | ≥ 0.70 | **PASS** (report only) |
| `jd.company_accuracy` | 1.0000 | — | measured, no threshold |
| `jd.distractor_leakage_rate` | 0.0000 | ≤ 0.05 | **PASS** |
| `jd.education_accuracy` | 1.0000 | — | measured, no threshold |
| `jd.evidence_grounding_rate` | 1.0000 | ≥ 1.00 | **PASS** |
| `jd.location_accuracy` | 1.0000 | — | measured, no threshold |
| `jd.preferred_skill_f1` | 0.9880 | — | measured, no threshold |
| `jd.required_skill_f1` | 0.8832 | ≥ 0.85 | **PASS** |
| `jd.required_skill_precision` | 0.7908 | ≥ 0.75 | **PASS** (report only) |
| `jd.required_skill_recall` | 1.0000 | — | measured, no threshold |
| `jd.requirement_level_accuracy` | 0.9459 | — | measured, no threshold |
| `jd.role_accuracy` | 1.0000 | ≥ 0.90 | **PASS** (report only) |
| `jd.years_accuracy` | 0.9500 | — | measured, no threshold |

Counters: `company_hits`=120, `distractor_cases`=72, `distractor_leaks`=0, `education_hits`=120, `location_hits`=120, `required_false_negative`=0, `required_false_positive`=123, `required_true_positive`=465, `role_hits`=120, `skills_grounded_in_source`=900, `skills_with_evidence`=900, `unmapped_skill_names`=0, `years_hits`=114

### by_family

| key | metrics |
| --- | --- |
| `embedded` | cases=24.0, required_f1=0.7647 |
| `backend` | cases=24.0, required_f1=0.9143 |
| `ai_app` | cases=24.0, required_f1=0.9406 |
| `frontend` | cases=24.0, required_f1=0.9231 |
| `devops` | cases=24.0, required_f1=0.8942 |

### by_language

| key | metrics |
| --- | --- |
| `zh` | cases=53.0, required_f1=0.8875 |
| `mixed` | cases=25.0, required_f1=0.7764 |
| `en` | cases=42.0, required_f1=0.9524 |

## evidence_validation

Dataset `evidence_validation` @ `ev2.1` · 60 cases · 277 ms

| metric | value | threshold | status |
| --- | ---: | --- | --- |
| `evidence.accuracy` | 0.9000 | ≥ 0.80 | **PASS** (report only) |
| `evidence.brier` | 0.0904 | ≤ 0.15 | **PASS** (report only) |
| `evidence.degraded_case_rate` | 0.0000 | — | measured, no threshold |
| `evidence.ece` | 0.0316 | ≤ 0.05 | **PASS** (report only) |
| `evidence.macro_f1` | 0.8481 | ≥ 0.78 | **PASS** |
| `evidence.micro_f1` | 0.9000 | — | measured, no threshold |
| `evidence.partial_recall` | 0.6667 | — | measured, no threshold |
| `evidence.safer_rewrite_rate` | 0.3750 | — | measured, no threshold |
| `evidence.support_recall` | 0.9500 | ≥ 0.80 | **PASS** (report only) |
| `evidence.supported_f1` | 0.9268 | — | measured, no threshold |
| `evidence.supported_precision` | 0.9048 | — | measured, no threshold |
| `evidence.supported_recall` | 0.9500 | — | measured, no threshold |
| `evidence.unsafe_numeric_support_rate` | 0.0000 | ≤ 0.00 | **PASS** |
| `evidence.unsafe_support_rate` | 0.0500 | ≤ 0.07 | **PASS** |
| `evidence.unsupported_recall` | 0.9355 | — | measured, no threshold |

Counters: `cases`=60, `degraded_cases`=0, `false_negatives`=1, `false_positives`=2, `gold_partially_supported`=9, `gold_supported`=20, `gold_unsupported`=31, `numeric_claims`=4, `numeric_unsafe`=0, `scored_cases`=60, `true_positives`=19, `unsafe_supports`=2

### confusion

| key | metrics |
| --- | --- |
| `supported` | supported=19, partially_supported=1, unsupported=0 |
| `partially_supported` | supported=2, partially_supported=6, unsupported=1 |
| `unsupported` | supported=0, partially_supported=2, unsupported=29 |

### by_group

| key | metrics |
| --- | --- |
| `ai_app` | cases=6.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.91 |
| `backend_api` | cases=2.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.9 |
| `backend_data` | cases=2.0, accuracy=0.5, unsafe_supports=0.0, mean_confidence=0.92 |
| `devops` | cases=3.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.8967 |
| `embedded_comms` | cases=2.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.92 |
| `embedded_control` | cases=1.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.9433 |
| `experience_only` | cases=1.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.89 |
| `fabricated_achievement` | cases=1.0, accuracy=0.0, unsafe_supports=0.0, mean_confidence=0.89 |
| `fabricated_metric` | cases=7.0, accuracy=0.8571, unsafe_supports=0.0, mean_confidence=0.89 |
| `fabricated_role` | cases=3.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.89 |
| `fabricated_scope` | cases=2.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.89 |
| `fabricated_technology` | cases=7.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.8957 |
| `firmware` | cases=2.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.93 |
| `frontend` | cases=1.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.89 |
| `over_claim_role` | cases=2.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.89 |
| `over_claim_scope` | cases=4.0, accuracy=0.75, unsafe_supports=0.0, mean_confidence=0.89 |
| `partial_scope` | cases=1.0, accuracy=0.0, unsafe_supports=1.0, mean_confidence=0.89 |
| `quality` | cases=2.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.91 |
| `quantified_partial` | cases=1.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.89 |
| `quantified_unsupported` | cases=3.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.89 |
| `side_project` | cases=1.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.89 |
| `technology_inflation` | cases=3.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.9167 |
| `vague_magnitude` | cases=1.0, accuracy=0.0, unsafe_supports=1.0, mean_confidence=0.91 |
| `weak_evidence` | cases=2.0, accuracy=1.0, unsafe_supports=0.0, mean_confidence=0.89 |

### Recorded failures (6)

```json
{"kind": "misclassification", "case_id": "ev-0010", "claim": "使用 Redis 缓存会话数据以降低数据库压力", "gold": "supported", "predicted": "partially_supported", "confidence": 0.93, "independent_sources": 2, "reasons": ["no_evidence_match"], "description":…
{"kind": "misclassification", "case_id": "ev-0030", "claim": "设计了完整的权限模型并落地到所有接口", "gold": "partially_supported", "predicted": "unsupported", "confidence": 0.89, "independent_sources": 1, "reasons": ["no_evidence_match"], "description": "O…
{"kind": "misclassification", "case_id": "ev-0036", "claim": "用 C++ 重写了通信中间件，吞吐提升明显", "gold": "partially_supported", "predicted": "supported", "confidence": 0.91, "independent_sources": 2, "reasons": [], "description": "'明显' is vague enoug…
{"kind": "misclassification", "case_id": "ev-0039", "claim": "完成两轮自平衡机器人的整机调试", "gold": "partially_supported", "predicted": "supported", "confidence": 0.89, "independent_sources": 2, "reasons": [], "description": "Control tuning is evidenc…
{"kind": "misclassification", "case_id": "ev-0052", "claim": "获得国家级算法竞赛一等奖", "gold": "unsupported", "predicted": "partially_supported", "confidence": 0.89, "independent_sources": 1, "reasons": ["no_evidence_match", "single_source_only"], "…
{"kind": "misclassification", "case_id": "ev-0057", "claim": "在 3 个月内完成了 6 个模块的交付并提前两周上线", "gold": "unsupported", "predicted": "partially_supported", "confidence": 0.89, "independent_sources": 1, "reasons": ["single_source_only"], "descrip…
```

## rag_retrieval

Dataset `rag_retrieval` @ `rag1.0` · 59 cases · 41 ms

| metric | value | threshold | status |
| --- | ---: | --- | --- |
| `retrieval.dense_hit_at_5` | 0.8983 | — | measured, no threshold |
| `retrieval.hit_at_1` | 0.8475 | ≥ 0.80 | **PASS** (report only) |
| `retrieval.hit_at_3` | 0.9661 | — | measured, no threshold |
| `retrieval.hit_at_5` | 0.9661 | ≥ 0.93 | **PASS** |
| `retrieval.keyword_hit_at_5` | 0.9831 | — | measured, no threshold |
| `retrieval.mrr` | 0.9011 | ≥ 0.85 | **PASS** |
| `retrieval.recall_at_5` | 0.9661 | ≥ 0.90 | **PASS** (report only) |

Counters: `dense_arm_available`=1, `dense_top5_hits`=53, `documents`=20, `fusion_losses`=1, `fusion_wins`=0, `hybrid_top5_hits`=57, `keyword_top5_hits`=58, `queries`=59

### by_query_type

| key | metrics |
| --- | --- |
| `exact_term` | queries=21.0, hit_at_1=0.9048, hit_at_3=1.0, hit_at_5=1.0, mrr=0.9524 |
| `intent` | queries=38.0, hit_at_1=0.8158, hit_at_3=0.9474, hit_at_5=0.9474, mrr=0.8728 |

### by_arm

| key | metrics |
| --- | --- |
| `hybrid` | queries=59.0, hit_at_1=0.8475, hit_at_5=0.9661, mrr=0.9011 |
| `keyword` | queries=59.0, hit_at_1=0.9322, hit_at_5=0.9831, mrr=0.9534 |
| `dense` | queries=59.0, hit_at_1=0.7288, hit_at_5=0.8983, mrr=0.7898 |

### Recorded failures (2)

```json
{"kind": "retrieval_miss", "query": "多个节点同时发送会不会冲突", "query_type": "intent", "gold_topic": "can", "returned": ["can/evidence_1.md", "docker/evidence_1.md", "pytest/evidence_1.md", "rag_rrf/evidence_0.md", "pid/evidence_1.md"]}
{"kind": "retrieval_miss", "query": "怎么保证服务按顺序启动", "query_type": "intent", "gold_topic": "docker", "returned": ["stm32/evidence_1.md", "react_next/evidence_1.md", "pgvector/evidence_0.md", "docker/evidence_1.md", "freertos/evidence_1.md"]}
```

## interview_relevance

Dataset `interview_relevance` @ `iv1.0` · 3 cases · 27 ms

| metric | value | threshold | status |
| --- | ---: | --- | --- |
| `interview.difficulty_match_rate` | 1.0000 | ≥ 0.60 | **PASS** (report only) |
| `interview.duplicate_rate` | 0.0000 | ≤ 0.10 | **PASS** |
| `interview.evidence_awareness_rate` | 0.6000 | ≥ 0.50 | **PASS** (report only) |
| `interview.forbidden_leakage_rate` | 0.0000 | ≤ 0.05 | **PASS** |
| `interview.question_count_ok_rate` | 1.0000 | — | measured, no threshold |
| `interview.required_skill_coverage` | 0.8333 | ≥ 0.75 | **PASS** |

Counters: `covered_skills`=10, `difficulty_items`=15, `difficulty_matches`=15, `duplicate_pairs`=0, `evidence_backed_items`=9, `gap_probes`=3, `plan_items`=15, `question_pairs`=9, `questions_asked`=9, `required_skills`=12, `scenarios`=3

### by_scenario

| key | metrics |
| --- | --- |
| `iv-embedded` | required_skills=4.0, covered=4.0, plan_items=5.0, evidence_backed_items=3.0, gap_probes=1.0, questions=3.0 |
| `iv-backend` | required_skills=4.0, covered=3.0, plan_items=5.0, evidence_backed_items=3.0, gap_probes=1.0, questions=3.0 |
| `iv-ai-app` | required_skills=4.0, covered=3.0, plan_items=5.0, evidence_backed_items=3.0, gap_probes=1.0, questions=3.0 |
