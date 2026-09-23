# Evaluation framework

Measured numbers for CareerForge AI, produced by running the real production code
(`packages/ai`) against labelled datasets.

```bash
python evals/generate_datasets.py     # regenerate the labelled datasets (seeded)
python evals/generate_datasets.py --check   # verify committed datasets are in sync
python evals/run.py                   # run every suite, write reports/eval-report.json
python evals/run.py --suite claim_validation
python evals/run.py --provider deepseek     # same suites against a real model
```

## Why this exists

A product whose entire claim is "every résumé line is backed by evidence" cannot
assert its own quality. The claim-validation suite is therefore not a nice-to-have:
it is the test of the product thesis.

It is also the only honest way to report performance. Every figure in the README's
benchmark table comes from `reports/eval-report.json`, which is committed
alongside the code so the numbers can be checked rather than trusted.

## Datasets

| Dataset | Samples | Contents |
|---|---|---|
| `jd_extraction.jsonl` | 120 | Job descriptions across 5 role families, 3 language styles, with exact ground-truth skill sets. 65% deliberately contain a company blurb naming technologies the role does **not** require. |
| `claim_validation.jsonl` | 120 | Claims paired with an evidence pool, labelled `supported` / `partially_supported` / `unsupported`, including 30 claims carrying a fabricated metric. |

Both are **generated, not scraped**, from a seeded generator
(`evals/generate_datasets.py`, seed `20260211`) with a content hash recorded in
`manifest.json`.

### The caveat, stated plainly

Real job postings have no ground truth — nobody publishes the correct skill set
for a scraped ad. A controlled corpus does, which is what makes precision and
recall measurable at all.

The consequence is that these numbers describe **performance on a controlled
corpus**, and should be read as an indicator rather than as market-representative
accuracy. Where a metric has a known weakness, it is listed below rather than
omitted.

## Suites

### `jd_extraction`

Runs `JobAgent`'s extraction path (`ExtractedJD` → taxonomy normalisation) and
compares against gold labels.

| Metric | Meaning |
|---|---|
| `required_skill_precision` / `recall` / `f1` | Canonical-id set comparison on required skills |
| `distractor_leakage_rate` | Share of postings whose *company blurb* technology was wrongly promoted to a requirement |
| `evidence_grounding_rate` | Share of extracted skills whose quoted evidence is a verbatim substring of the source — **a safety target, enforced in CI** |
| `requirement_level_accuracy` | Of skills found in both sets, the share assigned the right required/preferred/bonus level |
| `role_accuracy` / `location_accuracy` / `years_accuracy` / `education_accuracy` | Field-level extraction accuracy |

### `claim_validation`

Runs the deterministic adjudicator and measures the property the product exists
for.

| Metric | Meaning |
|---|---|
| `numeric_rejection_rate` | Share of claims carrying an unsupported metric that were rejected. **Safety target: must be 1.00.** |
| `over_support_rate` | Share of unsupported claims accepted as fully supported. The dangerous error. |
| `support_recall` | Share of genuinely supported claims recognised |
| `safer_rewrite_rate` | Share of rejected claims offered a compliant rewrite |

## Known weaknesses (measured, not hidden)

These are the current results on the heuristic provider — the zero-API-key path.
They are reported here because an evaluation framework that only shows favourable
numbers is decoration.

| Weakness | Value | Cause |
|---|---|---|
| `bonus_skill_f1` | 0.776 | Bonus skills are sparse and their phrasing ("了解 …") is the most varied of the three levels |
| `required_skill_precision` | 0.791 | Residual over-extraction when a technology is mentioned outside any recognisable section |
| `requirement_level_accuracy` | 0.946 | A skill mentioned in two sections is classified by its first non-ignored mention |
| `safer_rewrite_rate` | 0.489 | A rewrite is only offered when a clause can actually be dropped; many single-clause claims have no partial version |
| Threshold margin | 0.011 / 0.009 | Character-level overlap cannot see paraphrase, so the supported/unsupported separation for `claim_validation` is narrow (unsupported tops out at 0.404, supported bottoms out at 0.424). Widening it needs semantic matching — which is exactly what `--provider deepseek` measures. |

## Planned suites

| Suite | Blocked on |
|---|---|
| `retrieval_recall` (Recall@5 over a labelled evidence set) | PHASE 3 — the hybrid retriever does not exist yet |
| `interview_relevance` (question/evidence alignment) | PHASE 7 — the interview agent does not exist yet |
| `end_to_end` (full JD → match → résumé → gate pipeline) | PHASE 6 |

A suite is added when the component it measures exists. Shipping a metric for a
component that has not been built would be the exact failure mode this project is
about.
