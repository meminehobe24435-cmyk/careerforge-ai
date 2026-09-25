# Quality & evaluation

> The premise: an AI feature that "seems to work" has not been measured, and a number nobody can
> reproduce is a marketing claim. This document explains how quality is measured here, what the
> thresholds mean, and which gaps are still open — including the ones found by the very tests
> described below.

Related: [`reports/README.md`](../reports/README.md) (the current numbers) ·
[`ROADMAP.md`](./ROADMAP.md) (per-phase findings) · [`ARCHITECTURE.md`](./ARCHITECTURE.md) §9
(observability) · [`AI_DESIGN.md`](./AI_DESIGN.md) (why the model never produces numbers).

## 1. Testing strategy: four layers, each earning its cost

| layer                                       | runs | what only it can catch                                                                             |
| ------------------------------------------- | ---- | -------------------------------------------------------------------------------------------------- |
| **unit** (`packages/ai/tests`)              | 504  | arithmetic: confidence factors, match weights, RRF fusion, rule severities, PII patterns           |
| **integration** (`apps/api/tests`)          | 348  | the contract as shipped: envelope, auth, ownership, migrations, failure injection, cost arithmetic |
| **component** (`apps/web`, Vitest)          | 143  | rendering rules (null ≠ 0), keyboard coordinates, runtime guards against a drifted payload         |
| **end-to-end** (`apps/web/e2e`, Playwright) | 11   | the browser: stacking order, focus, real CORS, a real session, a real page with real data          |

The layering is not decoration — each layer has caught something the others structurally cannot:

- jsdom has no layout engine, so the 375 px table that pushed cost and status off-screen was
  invisible to 143 passing component tests and obvious in the first screenshot.
- Node's `fetch` does not enforce CORS, so a browser origin the API refuses was invisible to a
  25-check API smoke suite and to every unit test.
- A DOM-level test cannot see stacking order, so a drawer rendered _below_ its own overlay looked
  perfect until the mobile end-to-end run tried to click it.

Those three are the answer to "what has your test strategy actually caught?" — see
[`INTERVIEW.md`](./INTERVIEW.md) §PHASE 12.

**What is deliberately not done.** No snapshot tests of AI text (a model rephrasing a sentence must
not turn CI red); no pixel-diffing; no coverage target for the repository as a whole, because the
number would be dominated by generated migrations and schema files and would push people to write
tests for getters. Coverage is reported for the **core domain** only, and the scope is a list of
files somebody chose (`scripts/coverage_report.py`).

## 2. Evaluation strategy: measure the product, not the component

Four suites, one runner, one report schema (`evals/run.py`, `evals/report.py`):

| suite                 | dataset                     |      cases | origin                                                  |
| --------------------- | --------------------------- | ---------: | ------------------------------------------------------- |
| `jd_extraction`       | `jd_extraction.jsonl`       |        120 | generated, seeded, five role families × three languages |
| `evidence_validation` | `evidence_validation.jsonl` |         60 | **hand-authored**, three labels, 100 evidence fragments |
| `rag_retrieval`       | `rag_retrieval.jsonl`       | 59 queries | generated corpus with construction-known relevance      |
| `interview_relevance` | `interview_relevance.jsonl` |    3 roles | **hand-authored** scenarios                             |

Two rules make the numbers mean something:

1. **A suite never reimplements what it measures.** `evidence_validation` runs the real gate —
   rules → retrieval → model verdict → arithmetic — through `ValidatorAgent`, on the same
   `WorkflowExecutor` the API builds. It also reproduces the caller contract of
   `resume_service.validate` (material supplied _and_ a retriever), because the rules phase reads
   the material before retrieval runs; the first version of the suite omitted it and reported
   `support_recall 0.0000` — a number about a configuration no deployment uses.
2. **Labels do not come from the implementation.** The claim labels were written against a rubric
   before the gate was run, which is what makes them falsifiable — and they falsified two real
   defects (§5).

### Why the old claim benchmark was thrown away

PHASE 6–11 reported `claim.support_recall 1.0000` and `claim.over_support_rate 0.0000`. Both were
true and both were worthless: the generated corpus held **22 distinct claim/kind pairs across 120
rows** (one claim repeated twelve times), each with a single evidence snippet, and its labels
tracked the rule layer's own logic. The gate agreed with itself.

The replacement is 60 distinct hand-authored cases with 100 evidence fragments across nine evidence
kinds. The honest number on that corpus was `support_recall 0.0000` on the first run — and the
investigation that followed found the two defects below.

## 3. Confidence calibration: does 0.8 mean 80%?

Every case's final `GateConfidence` is recorded in the report, and
`reports/confidence-calibration.json` turns those rows into a reliability diagram, ECE and Brier
score. The current measurement (60 cases):

| bucket  | cases | mean confidence | actual accuracy |     gap |
| ------- | ----: | --------------: | --------------: | ------: |
| 0.8–0.9 |    45 |          0.8900 |          0.8889 | +0.0011 |
| 0.9–1.0 |    15 |          0.9296 |          0.8667 | +0.0629 |

**ECE 0.0166 · Brier 0.1034.** Read together they say: the confidence is well calibrated on
average, and specifically over-confident in its top bucket — which is exactly the region a résumé
gate operates in, and the reason the metric is reported rather than assumed. Two implementation
notes: ECE is sample-weighted (so ten empty buckets cannot flatter it), and `confidence == 1.0`
falls in the last bucket rather than outside every bucket.

## 4. Thresholds, gates and the two severities

`evals/config.py` holds every threshold with its rationale and severity:

- **gate** — missing it exits non-zero, so CI fails. Reserved for properties the product cannot
  ship without: evidence grounding 1.00, fabricated numbers rejected (0.00), fabricated claims
  accepted (≤0.075), retrieval Hit@5 ≥0.93, MRR ≥0.85, cross-role question leakage ≤0.05.
- **report** — printed as `MISS`, run still succeeds. Used where the honest number is below the
  ambition (partial-skill F1, safer-rewrite rate, evidence awareness).

Each threshold is anchored to a **measured** baseline with a stated margin, never to a round number
somebody liked. Example, verbatim from the config:

```python
Threshold(
    "evidence.unsafe_support_rate",
    maximum=0.075,
    severity="gate",
    rationale=(
        "最严格的一条 … 实测 0.0500（40 个非 supported 用例里漏过 2 个 …）。"
        "门禁设在 0.075（即 3/40）：比实测留一个用例的抖动余量 … "
        "本项目的目标是 0.02，**尚未达到**，缺口与对策记录在 docs/QUALITY.md。"
    ),
)
```

## 5. Findings the evaluation produced (and what was done)

| #   | finding                                                                                                                                                                                                                                                                                                                        | how it surfaced                                                                            | disposition                                                                                                                                                                                                                    |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | **Scope-inflated claims were accepted as fully supported.** "主导了后端服务的重构" over evidence saying _参与_, and three more like it. Token overlap is high and the confidence arithmetic has no opinion about who did what.                                                                                                 | First honest run of the hand-authored corpus: `unsafe_support_rate 0.1000`                 | **Fixed.** `detect_ownership_gap` + a **status cap**: an ownership phrase the evidence never uses caps the verdict at `partially_supported`. The cap can only lower a status, never raise one.                                 |
| 2   | **A model-reported blocker was softened by retrieval hits.** `decide_phase` treated "were there any hits" as "is this partially supported", so a claim the model explicitly called unsupported came back partially supported whenever the evidence base was non-empty — i.e. always. 13 of 20 fabricated claims were softened. | Same run: `unsupported_recall 0.3500`                                                      | **Fixed.** The model's own three-way answer decides: named `unsupported_parts` ⇒ unsupported; an explicit `partially_supported` ⇒ partial; a bare negative falls back to the arithmetic. `unsupported_recall 0.3500 → 0.9032`. |
| 3   | **The interview planner was embedded-only.** `_TOPIC_BY_SKILL` mapped embedded skills, so a backend or AI-application posting fell through to one generic project topic and asked nothing about FastAPI, PostgreSQL or RAG.                                                                                                    | New `interview_relevance` suite: `required_skill_coverage 0.3333`, `duplicate_rate 0.2222` | **Fixed.** Topic map and question bank extended for backend/data/AI/frontend/platform roles with per-topic answer terms. Coverage **0.3333 → 0.8333**, duplicates **0.2222 → 0.0000**.                                         |
| 4   | **The eval itself was misconfigured**: evidence documents were created with the schema default `confidence=0.0`, so the gate's confidence was 0 for every case.                                                                                                                                                                | `support_recall 0.0000` with confidence 0.0 in every trace                                 | **Fixed** by building the evidence graph, exactly as production stores it. Worth noting for phase 13: _missing_ confidence degrades the gate to "everything unsupported" — safe, but silent.                                   |
| 5   | **Cross-tenant leak on `/ai-runs` and `/ai-costs`.** A second account could list and fetch another account's runs; the cost aggregates summed the whole deployment.                                                                                                                                                            | Failure-injection suite (written to probe ownership)                                       | **Fixed**: both reads are scoped to the caller plus the deployment's own ownerless runs; a foreign run id is a 404.                                                                                                            |
| 6   | **A raising retriever returned 500.** The optional step recorded `None`, and the decision phase raised `AttributeError` on the missing mapping.                                                                                                                                                                                | Failure-injection suite                                                                    | **Fixed**: `retrieve_phase` catches and reports the degradation; the three `None`-unsafe reads are gone. The test now asserts the fixed behaviour (200, unsupported, with the reason stated).                                  |
| 7   | **`sinceHours` compared local time to a UTC column**, so on this UTC+8 host a run created seconds earlier fell outside a one-hour window.                                                                                                                                                                                      | Failure-injection suite, pinned as `xfail`                                                 | **Fixed** (`utcnow()`); the xfail became an ordinary assertion.                                                                                                                                                                |
| 8   | **A metric implementation was wrong**: the confusion matrix incremented once per declared label, so a three-label suite reported a cell of 3 for one case.                                                                                                                                                                     | `evals/tests/test_metrics.py` — the test that sums the matrix                              | **Fixed** before any number was published. A metric nobody tests is a metric that can be wrong.                                                                                                                                |
| 9   | **The RAG fusion is slightly worse than BM25 alone** on this corpus (Hit@5 0.9661 vs 0.9831; 1 fusion loss, 0 wins).                                                                                                                                                                                                           | `rag_retrieval` per-arm breakdown                                                          | **Reported, not tuned.** Equal RRF weights are the likely cause; fitting weights to 59 queries would be overfitting dressed as engineering.                                                                                    |

## 6. Failure injection: what the system does when a dependency lies

`apps/api/tests/failure_support.py` provides a `ScriptedProvider` that can time out, hang, return
429, emit malformed JSON, return the wrong shape, crash, or exhaust a budget; `test_failure_injection.py`
drives real endpoints with it. The properties asserted are about the _user_, not the exception:

- a transient upstream failure **degrades** (200 with a degraded run) rather than 500-ing;
- a malformed structured output never becomes a fabricated answer;
- a retrieval outage still produces a verdict, with the reason stated;
- every one of those writes an `agent_runs` row whose status says what happened.

The team's own rule: a test that cannot fail is worthless, so each of these was verified by
breaking the production code it protects and watching it go red —
`resilience.py`'s degrade path was replaced with a re-raise and the suite went from `16 passed` to
`7 failed, 21 passed`, then back to green on restore.

## 7. Known limitations (measured, not hidden)

1. **`structured_output` records no tokens or cost.** The core returns the parsed schema and drops
   the provider's usage envelope, so `agent_runs.total_tokens` is structurally 0 for every
   agent that uses the structured path (all of them). The cost page is honest about it (it prints
   the provider's own note), but a paid deployment would not see real spend. Fixing it means
   changing `RunContext.structured`'s return shape — a core interface change, deliberately left
   for its own unit of work.
2. **A failed request leaves no run row.** The tracker writes inside the request transaction, which
   `get_db` rolls back on failure. `executor.py`'s comment claims observability is never lost; the
   measurement says otherwise. Recorded here as a contradiction, not a design decision.
3. **Two scope-inflation cases still pass** (`ev-0036` "吞吐提升明显", `ev-0039` "整机调试") — the
   residual 0.05. Both need entailment on the _action_, which no keyword rule can do.
4. **`skill_not_in_graph` is only a warning.** A technology the evidence never mentions should, by
   the product's own rule, make a claim unsupported; raising it to a blocker needs a
   false-positive audit of the token extractor first (an honest claim wrongly hard-rejected is a
   worse failure than a soft verdict).
5. **Interview coverage 0.8333**: two required skills in the fixtures have no topic mapping yet.
6. **Calibration covers the zero-key path only.** With a real provider the model's verdict changes
   the confidence distribution; the calibration artefact is regenerated by
   `python evals/run.py --provider deepseek`, which needs a key and is therefore not in CI.
7. **The E2E suite runs the desktop project by default**; the mobile project is opt-in
   (`pnpm --filter @careerforge/web test:e2e --project=mobile`) because it triples the runtime for
   a project whose mobile surface is still thin.

## 8. CI gates

| job          | command                                                                      | gating                                          |
| ------------ | ---------------------------------------------------------------------------- | ----------------------------------------------- |
| python-tests | `pytest packages/ai/tests apps/api/tests evals/tests -q`                     | yes                                             |
| web-tests    | `pnpm --filter @careerforge/web test`                                        | yes                                             |
| web-build    | `pnpm --filter @careerforge/web build`                                       | yes                                             |
| evals        | `python evals/run.py` + `python evals/generate_datasets.py --check`          | yes — a missed **gate** threshold fails the job |
| guards       | `ruff`, `mypy`, `check_layering`, `check_file_length`, `check_design_tokens` | yes                                             |
| e2e          | `pnpm --filter @careerforge/web test:e2e` against a started stack            | yes, on the desktop project                     |

Real-model evaluation (`python evals/run.py --provider deepseek`) and the real-provider E2E smoke
are **manual**, because they cost money and depend on a key. The default CI path needs no API key
at all: every suite, test and end-to-end flow runs on the zero-key heuristic provider, which is a
first-class deployment rather than a mock (ADR-009).
