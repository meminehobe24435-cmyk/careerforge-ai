# Quality report

> **Know what the system gets wrong.** Every number below came from a command in this repository,
> on commit `c147180`. Nothing here is estimated, and where a metric is below its ambition it is
> printed as below.

Regenerate everything with:

```bash
python evals/generate_datasets.py          # datasets (deterministic; --check verifies no drift)
python evals/run.py                        # all four suites → eval-report.{json,md} + calibration
python scripts/coverage_report.py          # → coverage.{xml,json} + coverage-summary.md
pytest packages/ai/tests apps/api/tests evals/tests -q
pnpm --filter @careerforge/web test        # component + guard tests
pnpm --filter @careerforge/web test:e2e    # Playwright, installed Chrome
```

## Test suites

| suite | cases | what it protects |
| --- | ---: | --- |
| `packages/ai/tests` | **504** | the AI core: scoring arithmetic, claim rules, retrieval, agents, prompts |
| `apps/api/tests` | **348** | HTTP contract, auth, persistence, migrations, failure injection, cost accounting |
| `apps/web` (Vitest) | **143** | rendering, formatting, board state, keyboard, runtime guards (positive + negative) |
| `apps/web/e2e` (Playwright) | **11** | five product flows in a real browser, plus a CORS regression |
| `evals/tests` | **19** | the metric implementations themselves, against hand-computed values |
| **total** | **1025** | |

## AI evaluation (`reports/eval-report.json`)

242 cases across four suites, 39 metrics, 4/4 suites passing their gates, in 763 ms.
Provider: the zero-key heuristic chain — the same code path a deployment without API keys runs.

| suite | cases | headline metrics |
| --- | ---: | --- |
| `jd_extraction` | 120 | required-skill **F1 0.8832**, precision 0.7908, recall 1.0000, evidence grounding **1.0000**, distractor leakage 0.0000 |
| `evidence_validation` | 60 | accuracy **0.8833**, macro F1 **0.8306**, support recall 0.9500, unsupported recall 0.9032, **unsafe support rate 0.0500** |
| `rag_retrieval` | 59 | **Hit@1 0.8475, Hit@3 0.9661, Hit@5 0.9661**, Recall@5 0.9661, **MRR 0.9011** |
| `interview_relevance` | 3 roles | required-skill coverage **0.8333**, duplicate rate 0.0000, forbidden-topic leakage 0.0000, evidence awareness 0.6000 |

### The metric that matters most

```
evidence.unsafe_support_rate = 0.0500   (2 of 40 non-supported claims accepted as supported)
evidence.unsafe_numeric_support_rate = 0.0000   (0 of 4 fabricated measurements accepted)
```

`unsafe_support_rate` is the share of claims that should **not** have been called supported but
were. For a résumé system this is the only error direction that is unacceptable: a false negative
costs the candidate a review, while a false positive writes an invented achievement onto their CV
in their own voice. Confusion matrix over the 60 hand-authored cases:

| gold ↓ / predicted → | supported | partially | unsupported |
| --- | ---: | ---: | ---: |
| supported (20) | **19** | 1 | 0 |
| partially supported (9) | 2 | **6** | 1 |
| unsupported (31) | **0** | 3 | **28** |

The bottom-left cell is the one to watch: **zero** fabricated claims were promoted to *supported*.
The remaining 0.05 lives in the middle row — scope-inflated sentences whose work is real.

### Calibration (`reports/confidence-calibration.json`)

Does "confidence 0.8" mean 80%? On this corpus, yes:

| bucket | cases | mean confidence | actual accuracy | gap |
| --- | ---: | ---: | ---: | ---: |
| 0.8–0.9 | 45 | 0.8900 | 0.8889 | **+0.0011** |
| 0.9–1.0 | 15 | 0.9296 | 0.8667 | +0.0629 |

**ECE 0.0166** · **Brier 0.1034** · accuracy 0.8833 · mean confidence 0.8999.
The top bucket is the honest caveat: when the gate is most certain it is over-confident by six
points, and 7 cases were wrong at a confidence of 0.75 or above.

## Coverage (`reports/coverage-summary.md`)

| area | statements | covered | % |
| --- | ---: | ---: | ---: |
| claim gate & confidence | 362 | 344 | **95.0%** |
| job matching & scoring | 291 | 280 | **96.2%** |
| retrieval (RAG) | 365 | 333 | **91.2%** |
| profile & JD parsing | 140 | 134 | **95.7%** |
| interview orchestration | 211 | 199 | **94.3%** |
| AI accounting & observability | 280 | 226 | **80.7%** |
| **core domain** | **1649** | **1516** | **91.9%** |
| everything measured | 17452 | 15793 | 90.5% (reported, not a target) |

## Local API latency (`reports/api-performance.json`)

`python scripts/perf_smoke.py --base-url http://127.0.0.1:8319/api/v1` — a tripwire, not a
benchmark. Twenty samples each, development server, SQLite, laptop hardware; model-calling
endpoints are excluded because an LLM's latency is not a property of this code.

| endpoint | P50 | P95 |
| --- | ---: | ---: |
| `GET /system/health` | 4.77 ms | 5.51 ms |
| `GET /dashboard` | 14.18 ms | 15.01 ms |
| `GET /ai-runs?limit=50` | 7.73 ms | 8.14 ms |
| `GET /ai-costs?range=7d` | 8.72 ms | 9.79 ms |
| `GET /applications/board` | 7.14 ms | 7.81 ms |

## Regression policy

- **Gates vs reports.** Every threshold in `evals/config.py` declares its severity. A missed *gate*
  exits non-zero (CI fails); a missed *report* is printed as `MISS` and the run still succeeds.
  Quality metrics the project has not earned stay reports — lowering a threshold until it always
  passes converts an honest gap into a green check.
- **Baselines are committed.** `reports/baseline-eval-report.json` is the comparable report for
  this commit; `python evals/compare.py baseline current` classifies every metric as improved,
  same or regressed, with the direction declared per metric (for ECE, lower is better).
- **Fixture versions are committed.** A dataset change bumps `fixture_version`; `--check` fails if
  the content moves without the version moving, so a benchmark number can always be traced to the
  cases that produced it.

## Honest gaps

Everything here is measured, so the gaps are specific:

1. **Two scope-inflation cases still pass as supported** (`ev-0036`, `ev-0039`): vagueness and
   scope claims with no keyword to hang a deterministic rule on. The countermeasure — an
   entailment check on the *action* rather than the nouns — is not implemented.
2. **RAG: the fusion loses a query the lexical arm alone finds.** Keyword Hit@5 0.9831 vs hybrid
   0.9661 (1 fusion loss, 0 wins on this corpus). Equal RRF weights are the likely cause; a
   weighted fusion tuned on this corpus would risk overfitting 59 queries, so it is reported
   instead of tuned.
3. **`structured_output` records no tokens.** The core interface returns the parsed schema and
   drops the provider's usage envelope, so a paid deployment's cost page would read 0 until that
   interface changes. Documented in `docs/QUALITY.md` §Known limitations.
4. **A failed AI request leaves no observable trace** (the tracker writes inside the request
   transaction, which rolls back). Found by the failure-injection suite and recorded, not fixed.
5. **Interview coverage is 0.8333, not 1.0**: two required skills still have no topic mapping in
   the zero-key question bank.
6. **E2E covers four of five flows at the API level**, because the Jobs, Evidence Graph, Validator
   and Interview *pages* are not shipped yet (`live: false` in `nav-config.ts`). The specs assert
   the real endpoints from page context and prove the result where a surface exists.
