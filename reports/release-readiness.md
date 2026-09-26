# Release readiness — v1.0.0

- generated: 2026-09-26 (PHASE 14 record below, PHASE 15 launch status in §0)
- tree: `main`, pushed to `github.com/meminehobe24435-cmyk/careerforge-ai`
- verdict: **the code is released and CI-verified end to end, including a containerized deployment; a
  public demo URL does not exist** (§0, §4)

This is the release record: what was fixed before launch, what was *proved* rather than claimed, and
what could not be proved here. Nothing in it is an estimate. Where a number is missing, the reason is
written next to it rather than a plausible value.

## 0. PHASE 15 status — launch

| requirement | state | evidence |
| --- | --- | --- |
| GitHub remote | ✅ configured and pushed | `github.com/meminehobe24435-cmyk/careerforge-ai`, `main` tracking `origin/main` |
| Repository About | ✅ description + 16 topics | `gh repo view`; homepage deliberately empty (there is no demo URL) |
| CI | ✅ **all six jobs green** | `api-sqlite`, `api-postgres`, `web`, `e2e`, `images`, `compose-stack` |
| Docker images built | ✅ witnessed | the `images` job builds both and boots the API container against its own health check |
| PostgreSQL path | ✅ witnessed | `api-postgres` runs the full API suite on `pgvector/pgvector:16`; `compose-stack` migrates a real database from empty — `migrate exited with 0`, 28 tables |
| Containerized stack | ✅ started and verified | postgres+pgvector, Redis, migrate, api, worker and web; `ready: {"ready": true, "gate": "database", "degraded": ["llm_provider","queue","vector"]}` |
| Seed idempotency on that stack | ✅ | second run reported `skills: {inserted: 0, unchanged: 126}` and `prompts: {inserted: 0, unchanged: 10}` |
| Browser suite against that stack | ✅ **45 passed (48.8s)** | desktop + mobile, axe `0 critical · 0 serious`, against `localhost:3000` |
| Version proof | ✅ | the job fails unless `/system/version` names `$GITHUB_SHA`; it did (`00f6698`) |
| Public URL | ❌ **not available** | no hosting account or credential on this machine; see §4 |
| Live E2E on a public URL | ❌ not run | follows from the line above |
| `v1.0.0` tag | ✅ created | after every condition in §8 and §21 above was met **in CI's containerized deployment**, which §8 accepts as the alternative to a live deployment; the absent public URL is stated here and in the release notes rather than implied |

The distinction that matters: the image path, the migration path, the whole compose topology and the
browser suite against it are now *witnessed* rather than described — on a machine with a container
runtime and a PostgreSQL service, which this one does not have. The one thing still missing cannot be
supplied by any amount of local or CI work: a hosting account.

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

## 1b. What the first CI runs found (PHASE 15)

The repository's first push started the first CI run this project has ever had — and a clean machine
found ten defects that a green local suite could not, **three of them in the product**:

| # | defect | how CI found it | fixed in |
| --- | --- | --- | --- |
| 1 | `0009` used `batch_alter_table(recreate="always")`, which on PostgreSQL tries to drop a table `llm_calls.run_id` has a foreign key into → `DependentObjectsStillExistError`. **The PostgreSQL migration path had never been executed**; the release proof's `NOT RUN` table said so in its own words | `api-postgres`: `alembic upgrade head` | `41dc6c6` |
| 2 | `_repo_root()` resolved the repository only for an editable install; `pip install -e apps/api` shadows the editable core with a regular site-packages copy, so the walk landed in the Python installation's `lib/`, the **prompt registry came up empty**, and 63 API tests failed with `400 VALIDATION_ERROR` on job analysis, profile import and résumé optimisation | `api-postgres`, then `api-sqlite` | `0b3f467`, `b0d4d64` |
| 3 | The API image installed the core **without the `parsing` extra**, so a container could accept a PDF or DOCX upload and fail to read it — every document kind except plain text | `api-sqlite` parsing tests | `a999c08` |
| 4 | `Dockerfile.web` never copied `pnpm-lock.yaml` → `ERR_PNPM_NO_LOCKFILE`: the image could never have built | `images` | `a999c08` |
| 5 | The web image's builder stage had no **source** for the workspace packages → `TS6053: File '@careerforge/config/tsconfig/nextjs.json' not found` | `images` | `04fddc2` |
| 6 | `output: 'standalone'` was documented in the Dockerfile as enabled and was **not** → `failed to calculate checksum … .next/standalone: not found` | `images` | `b0d4d64` |
| 7 | `apps/web/public` **did not exist** in the repository, so the final `COPY` of it failed | `images` | `b0d4d64` |
| 8 | `engines.node >= 20.9.0` was a claim nothing had ever checked: pnpm 11.7.0 imports `node:sqlite`, which needs Node ≥ 22.5, so three jobs and the web image died on Node 20 | `web`, `e2e`, `images` | `a04e584` |
| 9 | `docker compose up` **had never worked**: `infra/db/init/` was mounted whole, so `002_skills.sql` ran during `initdb`, before Alembic created `skills` → `relation "skills" does not exist` → postgres unhealthy → the whole stack failed to start | `compose-stack` | `53c6578` |
| 10 | `/system/version` answered `commit: null` in every container, because nothing passed the `GIT_SHA` build argument the Dockerfile declares — the stack could not name the commit it was running | `compose-stack` version proof | `59e4404` |

Four more were configuration rather than product (`pnpm` version declared twice, a missing throwaway
`JWT_SECRET` for `compose config`, `ARG005` in a new test file, and three unformatted documents), and
one was caused by a fix (`check_file_length.py` crashing on the newly emitted `standalone` output).

**The lesson this phase is built around:** "1,385 tests pass" was true, and it was evidence about *this
machine, with this install method, running these commands*. Six of the ten defects above were in code
paths that had never been executed anywhere else.

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

## 4. Deployment

**Verdict: the stack is proved in containers; a public URL does not exist.** No hosting account or
credential is available to this machine, so no live URL is published and none is fabricated.

| required | state |
| --- | --- |
| Multi-stage `Dockerfile` for api and web | ✅ `infra/docker/Dockerfile.api`, `Dockerfile.web` — both **built** by CI's `images` job, which also boots the API container and checks its health endpoint |
| `docker-compose.yml` (postgres+pgvector, redis, migrate, api, worker, web) | ✅ **started** by CI's `compose-stack` job: migrations from an empty database, the demo seed applied twice, pgvector confirmed as a real extension, the schema's tables counted, health/ready/version checked, then the whole browser suite run against `localhost:3000` |
| CI covering the container build | ✅ `images` and `compose-stack` |
| `docker compose up` executed | ✅ in CI (Linux runner with a container runtime). ⚠️ still **not** on this machine, which has no `docker`, `podman` or `docker-compose` — the release proof's `NOT RUN` table remains accurate about *this* machine |
| A git remote | ✅ `origin` → `github.com/meminehobe24435-cmyk/careerforge-ai` |
| A public URL | ❌ **blocked** — no cloud account, credentials or payment method available here |

What a person with credentials must do — one step, because everything else now exists:

```bash
# web on Vercel · api on Render/Railway · Postgres on Neon (pgvector) · Redis on Upstash
#   set DATABASE_URL, REDIS_URL, JWT_SECRET (>=32 chars), CORS_ORIGINS, LLM_PROVIDER=deepseek + key
#   run `alembic upgrade head` as the pre-deploy step (the app does not migrate at boot on PostgreSQL)
# then re-prove it rather than assuming:
E2E_BASE_URL=https://<web-host> E2E_API_URL=https://<api-host>/api/v1 pnpm --filter @careerforge/web test:e2e
curl -sf https://<api-host>/api/v1/system/version   # must name the deployed commit
```

Two limitations the containerized run made visible, both reported by the system itself rather than
discovered later: `/system/health` says `vector: degraded (in_memory_index)` — there is no durable
embeddings table, so a restart re-embeds — and `queue: degraded (redis_unavailable)`, because the
configured Redis queue falls back to the in-process one. `docs/DEPLOYMENT.md` documents both, and
`/system/ready` returns `ready: true` *with* a `degraded` list rather than claiming a clean bill.

## 5. GitHub and portfolio launch

In place: the public repository with its description and 16 topics; `README.md` (hero with the evidence
graph, architecture, quick start for both paths, API, testing, security, the measured weaknesses);
`LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and PR templates, `.env.example`,
`.nvmrc`, `.dockerignore`; `docs/` (PRD, ARCHITECTURE, DATABASE, API, UI, DECISIONS with 23 ADRs,
QUALITY, ROADMAP, DEMO, DEPLOYMENT, **INTERVIEW**, **INTERVIEW_QUESTIONS** (65 prepared answers),
**CODE_TOUR** (the five files), **ROLE_MAPPING** (four roles), **PORTFOLIO** (résumé bullets, STAR
stories, slide outline)); 18 screenshots and one 0.46 MB evidence-graph GIF; a CI workflow with six jobs.

Outstanding, and it is UI work rather than repository work: the social preview image, the GitHub
Release entry with notes (the `v1.0.0-rc.1` tag is pushed; a Release is a web-UI object), and the
`v1.0.0` tag itself, which waits on a public deployment. A `docs/PORTFOLIO.md` résumé/STAR set that used
to be listed here as missing now exists.

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
