# Release readiness — v1.0.0-rc.1

- generated: 2026-09-26
- tree: `main`, all work committed before this report was written; every number below was produced by
  a run recorded in `reports/` on this machine
- verdict: **the code is release-ready; the deployment is `DEPLOYMENT BLOCKED`** (see §4)

This is the PHASE 14 record: what was fixed before launch, what was *proved* rather than claimed, and
what could not be proved here. Nothing in it is an estimate. Where a number is missing, the reason is
written next to it rather than a plausible value.

## 1. Release blockers: found, fixed, and how each one was found

Five defects were found by running the product against a fresh database rather than by reading it,
and a sixth was found while generating the artefacts below. Each is recorded in `docs/ROADMAP.md`
under PHASE 14 with the measurement that exposed it.

| # | Defect | How it surfaced | Fixed in |
| --- | --- | --- | --- |
| 1 | The AI rate-limit budget charged **reads** of stored AI state (`GET /jobs/{id}/match`, `GET /ai/interview/{id}`) as model spend, so a user could exhaust twenty "AI requests" by reloading a page and then be refused the analysis they wanted | E2E on a fresh database: `429` rendered as a failed job analysis; the API log showed 33 AI-path requests in 60 s against a 20-token bucket, 10 of them reads | `eed606b` |
| 2 | `/system/info` announced a **hard-coded** upload budget of 20/hour while the limiter enforced the configured value, and the test asserting it reproduced the same literal — so the assertion could not fail | started the stack with `RATE_LIMIT_UPLOAD_PER_HOUR=500`: four of five reported numbers followed the environment, this one did not | `206c440` |
| 3 | The browser suite declared **no budgets**, which makes CI's `e2e` job red by construction (45 flows in ~90 s is not a human load) | same run as (1); still 23 spending calls per minute after (1) | `6301715` |
| 4 | The shared `jobId` fixture analysed a posting but never matched it, so two gates depended on **spec execution order** | `a11y.spec.ts` runs before `jd-analysis.spec.ts` on desktop; `GET /jobs/{id}/match` returned `404 not been matched yet` and the panel could not exist | `6301715` |
| 5 | ECE and Brier were measured and published in `reports/confidence-calibration.md` but never entered the compared metric set, while `evals/compare.py` carried explicit lower-is-better rules for both names — a calibration change could not appear in a diff or fail a gate | reading the eval report's metric list against the tool's own rules | `de84fad` |
| 6 | **Every evaluation artefact this project has committed recorded `git_dirty: true`**, clean tree or not: `_git` returned the sentinel `"unknown"` for any empty output and the caller read it with `bool(...)`, so `git status` answering "nothing is modified" produced a truthy string. The provenance flag that decides whether published numbers belong to a commit was therefore always the same value | the tree was verified clean and the freshly generated report still said dirty; calling the helper directly printed `'unknown'` | `58fd9c4` |

One further defect was fixed in the same spirit rather than as a blocker: `GET /dashboard` computed
the five-dimension Profile Strength breakdown on every request and dropped it, while the page told
the reader the breakdown would arrive in a later phase. The breakdown is now forwarded and rendered
(`497d6ad`). A second, smaller one: the browser-suite helper conflated "the page never hydrated" with
"the account has no posting" — both leave `#target-job` absent — and now names which happened.

## 2. Production proof (native path)

`reports/release-proof.md` — **7 passed, 0 failed, 0 not run**, 48.7 s, `containerized: false`.

| # | step | result |
| --- | --- | --- |
| 1 | Container runtime probe | no `docker`, `podman` or `docker-compose` on this machine (probed, not assumed) |
| 2 | Fresh database: delete the SQLite file, `alembic upgrade head` | revision `0009`, 28 tables |
| 3 | Seed twice | 161 rows across 9 tables; second run changed 0 tables |
| 4 | Production-mode API on the zero-key provider | health/ready/version answered; `degraded=['llm_provider','vector']` reported rather than hidden |
| 5 | Built frontend served by `next start` | landing/login/system/authenticated-dashboard all 200 |
| 6 | `smoke:api` against that API | 25 checks passed |
| 7 | Restart on the same database | no migration, no re-seed |

### Verification sweep on the release-candidate tree

| measurement | result | artefact |
| --- | --- | --- |
| API integration tests | **400 passed** | coverage run log |
| AI core + eval-metric tests | **passed** | `reports/coverage-summary.md` |
| Web unit tests | **365 passed / 27 files** | `pnpm --filter @careerforge/web test` |
| Browser E2E (desktop + mobile, fresh database) | **45 passed, 0 failed** | Playwright run |
| Accessibility gate (axe, 5 pages × 2 viewports) | **0 critical, 0 serious** | `a11y` annotations |
| Horizontal overflow at 375 / 768 / 1440 | no overflow on 7 pages | `e2e/overflow.spec.ts` |
| Core-domain coverage | **92.5%** (1556/1683), gate ≥75% | `reports/coverage-summary.md` |
| Evaluation gates | **4/4 suites pass, 0 fail, 242 cases** | `reports/eval-report.json` |
| Evaluation comparison vs PHASE 12 baseline | **improved 4, same 35, missing 2, regressed 0** | `evals/compare.py` output |
| Release proof | **7/7** | `reports/release-proof.json` |

Coverage by core area: claim gate and confidence 95.2%, job matching and scoring 96.2%, retrieval
91.2%, profile and JD parsing 95.7%, interview orchestration 94.6%, AI accounting and observability
83.6%. "Everything measured" is 91.0% and is reported beside it, never used as the target.

### Published quality numbers

| metric | value | threshold | status |
| --- | --- | --- | --- |
| `evidence.unsafe_support_rate` | 0.0500 | ≤ 0.075 (gate) | pass — **target is 0.02 and is not met** |
| `evidence.unsafe_numeric_support_rate` | 0.0000 | = 0 (gate) | pass |
| `evidence.macro_f1` | 0.8481 | ≥ 0.78 (gate) | pass |
| `evidence.accuracy` | 0.9000 | ≥ 0.80 (report) | pass |
| `evidence.support_recall` | 0.9500 | ≥ 0.80 (report) | pass |
| `retrieval.hit_at_5` | 0.9661 | ≥ 0.93 (gate) | pass |
| `retrieval.mrr` | 0.9011 | ≥ 0.85 (gate) | pass |
| `retrieval.hit_at_1` | 0.8475 | ≥ 0.80 (report) | pass |
| `jd.required_skill_f1` | 0.8832 | ≥ 0.85 (gate) | pass |
| `jd.evidence_grounding_rate` | 1.0000 | = 1.00 (gate) | pass |
| `interview.required_skill_coverage` | 0.8333 | ≥ 0.75 (gate) | pass |
| `evidence.ece` | 0.0316 | ≤ 0.05 (report) | pass |
| `evidence.brier` | 0.0904 | ≤ 0.15 (report) | pass |

### What this proof is not

The proof's `NOT RUN` table is part of the artefact and stays part of it:

| not run | precise reason |
| --- | --- |
| `docker compose up` | no container runtime installed (probed in step 1). The native path above is the equivalent this machine can produce, and no artefact claims a compose run happened. |
| PostgreSQL migration path | no PostgreSQL server or client installed, so `alembic upgrade head` is proved on SQLite only. The migrations are dialect-aware; that is not evidence. |
| Redis queue backend | no Redis installed; the deployment runs the in-process queue and `/system/health` reports `queue=inprocess`. |
| Durable vector index (pgvector) | not implemented in this build; `/system/health` reports `vector: degraded (in_memory_index)`. Readiness names it and stays ready — the documented behaviour, not a pass. |
| Live cloud run (real LLM provider + public URL) | no cloud account, API key or credentials available to this machine. `LLM_PROVIDER=heuristic` is the honest zero-key setting. |
| Browser-driven walkthrough | asserted over HTTP by the proof; interactively covered by the E2E suite above (45 passed). |

## 3. Known weaknesses, published rather than hidden

1. **`unsafe_support_rate` is 5.00% against a target of 0.02.** Two non-supported claims were judged
   supported: `ev-0036` (「吞吐提升明显」) and `ev-0039` (「整机调试」) — both are range or vague
   statements with no keyword to anchor them. The gate is 0.075 so a real regression fails; the gap to
   the target is recorded in `docs/QUALITY.md` rather than tuned away.
2. **Keyword-only retrieval beats the hybrid at Hit@5** (0.9831 vs 0.9661 on this corpus). Reported,
   not tuned: a fusion weight chosen to win on 59 queries would be fitting the corpus.
3. **`jd.required_skill_precision` is 0.7908** — the extractor over-reports skills (recall 1.0). Report
   only, deliberately: recall matters more here than precision, and the number stays visible.
4. **No durable vector index** — retrieval runs on an in-process hybrid index, and health says so.
5. **In-process queue and rate limiter** — correct for one process, and the limitation is stated on
   `/system/health` instead of being implied away.
6. **One unexplained E2E flake** — the interview page stayed on skeletons once in two full runs. The
   wait is now named and three times longer, and the two failure modes are distinguishable; one
   non-reproduction is not a fix, so it is recorded as open in `docs/ROADMAP.md`.
7. **Calibration is compared but not gated** (`evidence.ece`, `evidence.brier`, both `report`). At 60
   cases a calibration figure moves on one reclassified example; a gate that fires on that gets
   switched off. The gate that matters for this suite is `unsafe_support_rate`.
8. **The PHASE 12 baseline predates two compared metrics.** `evals/compare.py` reports `evidence.ece`
   and `evidence.brier` as `missing` against the baseline rather than as regressions, which is its
   documented rule. They become comparable at the next baseline refresh.

## 4. Deployment — `DEPLOYMENT BLOCKED`

**Verdict: blocked by this machine's environment, not by the code.** Per the PHASE 14 instruction, no
live URL is published and none is fabricated. What exists is everything except the run:

| required | state |
| --- | --- |
| Multi-stage `Dockerfile` for api and web | written: `infra/docker/Dockerfile.api`, `Dockerfile.web`, both built in this repo |
| `docker-compose.yml` (postgres+pgvector, redis, migrate, api, worker, web) | written: 163 lines, `migrate` gated with `service_completed_successfully`, api healthcheck |
| CI covering the container build | **not yet a job**: `.github/workflows/ci.yml` runs `api-sqlite`, `api-postgres` (pgvector service container), `web` and `e2e`, but not `docker build` |
| `docker compose up` executed | **blocked** — no `docker`, `podman` or `docker-compose` on this machine (probed in proof step 1) |
| A public URL | **blocked** — no cloud account, credentials or payment method available to this machine |
| A git remote | **none configured**. The repository is local: 107+ commits on `main`, no `origin`. |

What a person with credentials must do, in order, and nothing else is required:

```bash
# 1. publish the source
git remote add origin git@github.com:<user>/careerforge-ai.git
git push -u origin main --tags

# 2. prove the image path (the one step this machine could not run)
docker compose build && docker compose up -d
curl -sf localhost:8000/api/v1/system/ready   # expect {"ready": true, ...}

# 3. deploy: web on Vercel, api on Render/Railway, Postgres on Neon (pgvector), Redis on Upstash
#    set LLM_PROVIDER=deepseek + DEEPSEEK_API_KEY to leave the zero-key path
# 4. re-run `python scripts/release_proof.py` against the deployed URL and replace §2 with it
```

Step 2 is also the missing CI job: `docker build` for both images belongs in `ci.yml`, and it is
listed as the first task of PHASE 15 in `docs/ROADMAP.md`.

## 5. GitHub and portfolio launch

In place: `README.md` (23.7 KB: hero, architecture, quick start, API, testing, security, limitations),
`LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and PR templates, `.env.example`,
`docs/` (PRD, ARCHITECTURE, DATABASE, API, UI, DECISIONS with 22 ADRs, QUALITY, ROADMAP, DEMO,
INTERVIEW), 18 screenshots and one 0.46 MB evidence-graph GIF under `docs/assets/`, and a CI workflow
with four jobs.

Outstanding, and all of it needs the GitHub UI or a remote that does not exist yet: repository
About/description, topics, social preview image, the `v1.0.0` release with notes, and
`docs/PORTFOLIO.md` (the resume/STAR material). The release tag `v1.0.0-rc.1` is created locally by
this phase; `v1.0.0` should be tagged only after step 2 above passes on a machine with a container
runtime, because until then the image path is unwitnessed.

## 6. Evidence index

Every number in this report comes from one of these files, all committed:

| artefact | what it holds |
| --- | --- |
| `reports/release-proof.json` / `.md` | the 7 proof steps, their commands, exit codes, observations, and the `NOT RUN` table |
| `reports/eval-report.json` / `.md` | 4 suites, 242 cases, every metric with its threshold, severity and rationale |
| `reports/confidence-calibration.json` / `.md` | reliability buckets, ECE and Brier for the evidence suite |
| `reports/coverage-summary.md` | core-domain coverage with the per-area and per-file breakdown |
| `reports/baseline-eval-report.json` | the PHASE 12 baseline the comparison runs against |
| `reports/api-performance.json` | P50/P95 latencies measured by `scripts/perf_smoke.py` |
| `docs/ROADMAP.md` | per-phase findings: what was found, how, and what was done |
| `docs/QUALITY.md` | the quality model, the known gaps, and their owners |
