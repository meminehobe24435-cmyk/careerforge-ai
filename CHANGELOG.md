# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-09-26

### Fixed — PHASE 14 · the defects a fresh database found before launch

Every item below was found by running the product against an empty database and reading what it
actually did, not by reviewing the code. `reports/release-readiness.md` §1 carries the measurements;
`docs/ROADMAP.md` carries the per-defect record.

- **The AI rate-limit budget counted reads as model spend.** `classify_request` matched AI paths by
  substring and ignored the method, so `GET /jobs/{id}/match` (reads a stored row) and
  `GET /ai/interview/{id}` (reads the session store) were charged to the same 20-per-minute bucket as
  the calls that reach a provider. A user could spend their twenty "AI requests" by reloading a page
  and then be refused the analysis they wanted. Measured: in the sixty seconds ending at the first
  `429` the browser suite made 33 requests to AI-marked paths against a bucket of 20, ten of them
  reads. The budget now covers `POST`/`PUT`/`PATCH` on AI paths — the requests that can spend — with
  the documented limit, window and default unchanged; `docs/API.md` §1.7 defined the group by
  endpoint and is corrected in the same commit.
- **`/system/info` announced an upload budget the limiter was not enforcing.** PHASE 14 made the
  upload budget a setting; the middleware was switched over and the reporting site was missed, so the
  status page kept printing the default 20 while the limiter used the configured value. The test
  asserting it reproduced the same literal, so it could not fail — it now asserts against settings,
  with a guard that the fixture's value differs from the default.
- **The browser suite declared no budgets and depended on spec order.** Two separate reds that both
  read like product bugs: the suite is one user driving 45 flows in ~90 s against a budget designed
  for a human (the stack now declares its own, as the unit suite already did, and
  `apps/web/e2e/README.md` writes the whole configuration down), and the shared `jobId` fixture
  analysed a posting without matching it, so `a11y.spec.ts` — which runs before `jd-analysis.spec.ts`
  on desktop — waited thirty seconds for a panel whose stored row did not exist yet.
- **Every evaluation artefact recorded `git_dirty: true`,** clean tree or not. `_git` returned the
  sentinel `"unknown"` for any empty output and the caller read it with `bool(...)`, so
  `git status --porcelain` answering "nothing is modified" produced a truthy string. The flag a reader
  uses to decide whether the published numbers belong to a commit was always the same value; it now
  distinguishes clean, dirty and "git could not answer", with tests for all three.
- **Calibration was published but not comparable.** ECE and Brier were computed into
  `reports/confidence-calibration.md` and never entered the report's metric set, while
  `evals/compare.py` carries explicit lower-is-better rules for both names. A calibration change could
  not appear in a diff or fail a gate. Both are now emitted as `evidence.ece` and `evidence.brier`,
  with report-only thresholds and the reason they do not gate.
- Removed three places where the dashboard said something untrue about the product: skeleton cards
  captioned 「尚未接入的面板」 claiming that `/analytics/timeline` and `/analytics/funnel` were needed
  (both exist and `/app/analytics` charts them), a permanently disabled 「载入示例数据 · PHASE 3」
  button, and a stat card rendering a missing 7-day delta as `7d trend · PHASE 10`. The dashboard
  guard test now fails on any `PHASE \d` or 「尚未接入」 a reader can see.

### Fixed — PHASE 15 · what the first CI runs found

The repository's first push started the first CI run this project has ever had. A clean machine found
ten defects that a green local suite could not, **three of them in the product**. The per-defect table
is in `docs/ROADMAP.md`; this is the summary of what it cost and what it taught.

- **The PostgreSQL migration path had never been executed.** `0009` used
  `batch_alter_table(recreate="always")`, which on PostgreSQL drops the table being rebuilt — and
  `llm_calls.run_id` has a foreign key into `agent_runs`. `DependentObjectsStillExistError: cannot drop
constraint pk_agent_runs`. The release proof's `NOT RUN` table had said in its own words that the
  PostgreSQL path was unproven; this is what the proof looked like. Now `recreate="auto"`: rebuild
  where the dialect requires it (SQLite), alter in place where it does not (PostgreSQL).
- **The prompt registry resolved only for an editable install.** `_repo_root()` walked up from the
  imported `config.py`, which is correct for development and wrong everywhere else: `pip install -e
apps/api` installs its sibling core as a _regular_ package, shadowing the editable one, so the walk
  landed in the Python installation's `lib/`, the registry came up **empty**, and 63 API tests failed
  with `400 VALIDATION_ERROR` on job analysis, profile import and résumé optimisation. Fixed by also
  walking up from the working directory — which is also how the container resolves `/app/prompts`.
- **The API image could not read a PDF.** It installed the core without the `parsing` extra, so a
  deployed container would accept a résumé upload and fail to parse it for every kind except plain
  text. The image installs `./packages/ai[parsing]` now, and every CI job installs `[dev,parsing]` so
  the suite runs with the dependencies the deployment has.
- **Two images that could never have built.** `Dockerfile.web` never copied `pnpm-lock.yaml`
  (`ERR_PNPM_NO_LOCKFILE`), and its builder stage had no _source_ for the workspace packages
  (`TS6053: File '@careerforge/config/tsconfig/nextjs.json' not found`). `output: 'standalone'` was
  documented in the Dockerfile as enabled and was not; `apps/web/public` did not exist at all. There is
  now a `.dockerignore`, which the source-copy fix made necessary rather than optional.
- **`docker compose up` had never worked.** `infra/db/init/` was mounted whole into
  `docker-entrypoint-initdb.d`, so the taxonomy seed ran during `initdb` — before Alembic creates the
  table it inserts into: `relation "skills" does not exist`, postgres unhealthy, whole stack down.
- **Containers could not name the commit they were running.** `/system/version` answered
  `"commit": null`, because nothing passed the `GIT_SHA` build argument `Dockerfile.api` declares — so
  the deployment could not satisfy the version proof a release gate depends on.
- **`engines.node >= 20.9.0` was a claim nothing had checked.** pnpm 11.7.0 imports `node:sqlite`,
  which needs Node ≥ 22.5; three jobs and the web image died on Node 20. Now `>=22.5.0`, with `.nvmrc`.

### Added — PHASE 15

- **A `compose-stack` CI job** that brings the whole topology up — postgres+pgvector, Redis, the
  one-shot migration service, the API, the worker, the built frontend — and then, in order: requires
  the migration container to have exited 0, waits for both services, confirms `vector` is a real
  PostgreSQL extension and counts the migrated tables, checks `/system/health`, `/system/ready` and
  `/system/version` (failing if the build does not name `$GITHUB_SHA`), applies the demo seed twice to
  prove it is idempotent, and runs the full browser suite — desktop and mobile, accessibility gate
  included — against the containerized URLs.
- `docs/INTERVIEW_QUESTIONS.md` (65 answers, each with the artefact its numbers came from, plus the
  three questions about how the project was built), `docs/CODE_TOUR.md` (the five files to open in an
  interview, with the ADR each one implements), `docs/ROLE_MAPPING.md` (four roles: what to lead with,
  what not to claim), and a rewritten `docs/PORTFOLIO.md` (six STAR stories, résumé bullets in Chinese
  and English for four roles, 150/300-character project descriptions, screenshots, slide outline).
- `.dockerignore`, `.nvmrc`, and a root `pytest.ini` that makes the eval suite importable however
  pytest was invoked.

### Added — PHASE 14

- `GET /dashboard` → `profileStrength.dimensions` and `algorithmVersion`: the five weighted
  dimensions with the engine's own labels, weights and weighted contributions, which sum to the
  score. `compute_profile_strength` had always returned them and the endpoint dropped them while the
  page said the breakdown would arrive later. Rendered under the ring, and asserted against the live
  response rather than against literals.
- `apps/web/e2e/README.md` — how to start the two-process stack, which budgets it declares and why,
  what the specs may assume, and the two gates that exist to fail a build.
- `reports/release-readiness.md` — the release record: blockers found and fixed, the production proof,
  the deployment block with its reasons, and an index from every published number to its artefact.
- `evals/tests/test_calibration_metrics.py` — the calibration wiring, including the direction
  invariant that motivated it.

### Known limitations — PHASE 14

- **`DEPLOYMENT BLOCKED`**: this machine has no container runtime, no PostgreSQL, no Redis and no
  cloud credentials, and the repository has no remote. The native path is proved end to end
  (`reports/release-proof.md`, 7/7) and `docker compose up` is not claimed anywhere. The image build
  is not yet a CI job; both are PHASE 15's first tasks.
- One unexplained E2E flake: the interview page stayed on skeletons once in two full runs. The wait is
  now named and three times longer, and "never hydrated" is distinguishable from "no posting to
  select"; one non-reproduction is not a fix, and it stays open in `docs/ROADMAP.md`.
- `evidence.ece` and `evidence.brier` report as `missing` against the PHASE 12 baseline, which
  predates them; they become comparable at the next baseline refresh.
- `evidence.unsafe_support_rate` remains 5.00% against a target of 0.02 (gate 0.075).

### Fixed — PHASE 13 · the observability layer told the truth about what it had measured

PHASE 12 found three defects in the AI observability layer, wrote them down and left them unfixed.
This unit fixes all three and makes each one **provable by a failing test**.

- **The cost page was structurally `$0.00`, including on a paid deployment.** `RunContext.structured`
  never charged usage and `MeteredProvider.structured_output` passed `tokens=None, cost=None`, because
  the provider returned only the parsed schema and dropped its usage object. Since every agent in the
  product uses that path, every run recorded zero tokens. Added a **usage envelope** (`LLMUsage`) that
  all three call shapes return — `chat`, `stream` and `structured_output` — carrying
  `input_tokens`/`output_tokens`/`total_tokens`/`cached_tokens`, USD and CNY cost, `provider`, `model`,
  `request_id` and **`usage_status`**. When a vendor reports nothing the status is `unavailable` and
  every count is SQL `NULL` — **not `0`**, and not a sentinel: `agent_runs`/`llm_calls`' counts became
  nullable (migration `0009`), `SUM` skips them, and `/ai-costs` says the totals are a floor. A cache
  hit reports `cached` with zero counts rather than the original call's tokens, which would bill them
  twice. The heuristic provider declares `unavailable` honestly (it computes locally and spends
  nothing) and keeps its local count in a separate field so it can never be summed into a cost.
- **A failed request left no trace at all.** `get_db` rolls the request's transaction back on any
  exception and the tracker wrote inside it, so a 400 or a 500 erased the run — contradicting
  `executor.py`'s comment that observability is never lost. A **failure journal**
  (`services/failure_journal.py`) now holds a failed run and the outermost middleware writes it through
  its own short-lived session _after_ the transaction has settled. Rows carry `status = failed`, a
  sanitized `error` plus a machine-readable `error_code`, the steps that completed, latency, usage and
  prompt version. A SAVEPOINT and a second session opened mid-transaction were both rejected; the
  reasoning is in the module.
- **A stored failure can no longer leak a secret or a document.** The error text is the one stored
  field copied out of an arbitrary exception, and those exceptions quote request bodies. A sanitiser
  (`services/error_report.py`) removes bearer tokens, API keys by vendor shape, auth headers, JWTs,
  emails, phone numbers and pasted documents before the row is written — and leaves the diagnostic
  intact, which the first version did not.
- **`skill_not_in_graph` is a blocker where the vocabulary can prove it.** A claim asserting a
  taxonomy-known technology that appears nowhere in the candidate's material — under any alias — is
  now refused outright, instead of producing a warning while the claim came back
  `partially_supported`. The prerequisite PHASE 12 named (a false-positive audit of the extractor) is
  `packages/ai/tests/test_skill_presence.py`: 30 labelled cases for spelling variants
  (`K8s` ⟷ `Kubernetes`), English/Chinese equivalents (`实时操作系统` ⟷ `FreeRTOS`), version suffixes,
  the material's own wording, and technologies **outside** the taxonomy, which stay warnings because
  "the extractor never recognised it" cannot be told apart from "the material never says it".
  Evaluation: `unsupported_recall 0.9032 → 0.9355`, `macro_f1 0.8306 → 0.8481`, no metric regressed.
- **A cache hit is now visible on the run that used it.** `RunRecorder` counts the envelope's `cached`
  status, so `agent_runs.cache_hit` agrees with `/cache/stats` instead of denying a hit the cache layer
  recorded.

### Added — PHASE 13

- `packages/ai/careerforge_ai/schemas/usage.py`, `providers/openai_responses.py`,
  `apps/api/src/careerforge_api/services/{failure_journal,error_report}.py` and
  `apps/api/src/careerforge_api/middleware/failures.py`, split out of files that outgrew the
  file-length gate.
- Migration `0009_usage_observability`: `usage_status`, `cached_tokens` and `error_code` on the
  observability tables, and the count columns made nullable — with a `downgrade()` that says which
  rows it cannot keep rather than writing zeros back.
- `usageStatus` (and nullable counts) in the `/ai-runs` and `/ai-costs` payloads, so a client can
  print "unavailable" instead of `0`. **The web pages do not read it yet** — see
  `docs/QUALITY.md` §7.9.

### Added — PHASE 12 · Measurement: evaluation, calibration, end-to-end and coverage

The phase was not "write more tests"; it was "find out what the system gets wrong". It did.

- **A real evaluation framework** (`evals/`): `run.py` (CLI, exit code 2 on a missed gate),
  `config.py` (every threshold typed, with its rationale and a `gate`/`report` severity),
  `metrics.py` (classification, retrieval, calibration — each with hand-checked unit tests),
  `report.py` (one `schema_version 1.0` document → `eval-report.{json,md}` +
  `confidence-calibration.{json,md}`), `compare.py` (baseline diff with per-metric direction).
- **Four suites, 242 cases**: `jd_extraction` (120), `evidence_validation` (60, hand-authored),
  `rag_retrieval` (59 queries over three arms), `interview_relevance` (3 roles).
- **Confidence calibration**: reliability buckets, **ECE 0.0166**, **Brier 0.1034** — the answer to
  "does 0.8 mean 80%", computed from the same run rather than asserted.
- **Failure injection**: a scripted provider that times out, hangs, returns 429, malformed JSON, a
  wrong shape, a crash or budget exhaustion, driven through real endpoints; 30 new tests.
- **End-to-end in a real browser** (Playwright, `channel: 'chrome'`, nothing downloaded): the five
  product flows plus the AI Runs drill-down and a CORS regression verified to fail on a bad origin.
- **Core-domain coverage 91.9%** of 1,649 statements, scope declared in
  `scripts/coverage_report.py`, with `reports/coverage.xml` and a markdown summary.
- **`docs/QUALITY.md`** (strategy, thresholds, findings, limitations) and **`docs/INTERVIEW.md`**
  (the story, with the numbers), plus `reports/README.md` as the quality hub.

### Fixed — PHASE 12 (defects the evaluation found)

- **Scope-inflated claims were granted `supported`.** "主导了后端服务的重构" over evidence that says
  _participated_ — token overlap is high and the arithmetic has no opinion about who did what. A new
  rule detects ownership language the evidence never uses and **caps** the verdict at
  `partially_supported`; a cap can only lower a status, never raise one.
- **A model-reported blocker was softened by retrieval hits.** `decide_phase` used "were there any
  hits" as a proxy for "is this partially supported", so a claim the model explicitly called
  unsupported came back partially supported whenever the evidence base was non-empty — which is
  every real candidate. Thirteen of twenty fabricated cases were softened; the model's own
  three-way answer now decides. `unsupported_recall 0.3500 → 0.9032`, `unsafe_support_rate 0.1000 → 0.0500`.
- **The interview planner only knew embedded skills.** A backend or AI-application posting fell
  through to one generic project topic (nothing about FastAPI, PostgreSQL or RAG) and repeated the
  same question. Topic map and question bank extended with per-topic answer terms:
  `required_skill_coverage 0.3333 → 0.8333`, `duplicate_rate 0.2222 → 0.0000`.
- **`/ai-runs` and `/ai-costs` leaked across accounts** — a second user could list and fetch
  another's runs, and the cost aggregates summed the whole deployment. Both reads are now scoped to
  the caller plus the deployment's own ownerless runs; a foreign id is a 404.
- **A raising retriever returned 500** (the optional step wrote `None` into the slot the decision
  phase then read). Retrieval now degrades and says so; three `None`-unsafe reads removed.
- **`sinceHours` compared local time against a UTC column**, so on a UTC+8 host a run created
  seconds earlier fell outside a one-hour window. Now `utcnow()`, and the `xfail` became an assertion.
- **The mobile drawer rendered below its own overlay** (`--z-drawer` 50 under `--z-modal` 60), so
  every tap below 768 px was intercepted by the backdrop. `DialogContent` gained
  `overlayClassName`/`overlayStyle`; the drawer moves both layers.
- **A metric implementation was wrong**: the confusion matrix incremented once per declared label,
  triple-counting every cell of a three-label matrix. Caught by the test that sums the matrix, before
  any number was published.

### Removed — PHASE 12

- **The generated claim corpus** (120 rows, 22 distinct claim/kind pairs, one evidence snippet each)
  and its generator. Its metrics were statements about a template, and its labels tracked the rule
  layer's own logic — `support_recall 1.0000` proved the gate agreed with itself. Replaced by 60
  hand-authored cases with a written rubric and a committed `fixture_version` (ev2.1).

### Known limitations — PHASE 12

- `unsafe_support_rate` is **0.0500**, not the 0.02 ambition: two scope-inflation cases
  (`吞吐提升明显`, `整机调试`) have no keyword a deterministic rule can act on.
- **The hybrid retriever is slightly worse than BM25 alone** on the 59-query corpus (Hit@5 0.9661 vs
  0.9831, one fusion loss, zero wins). Reported rather than tuned — fitting RRF weights to 59
  queries would be overfitting with extra steps.
- `structured_output` still records no tokens, and a failed request still leaves no run row (the
  tracker writes inside the request transaction). Both need changes outside this phase.
- The E2E suite asserts four of five flows at the API level, because those pages are not shipped yet.

### Added — PHASE 11b · The AI Runs table and the cost dashboard

PHASE 11a wrote the rows; this phase puts them on screen, and refuses to dress up what they say.

- **`/app/ai-runs`** — every traced operation, newest first: agent/workflow, model, tokens, latency,
  cost, status, cache hit, UTC time and step count, with status / time-window / workflow / agent
  filters that are sent to the API rather than applied to the page (a client-side filter would
  silently disagree with `total`). Opening a row fetches _that run's_ step chain and its metered
  calls — two granularities, kept apart, because a step can make two calls and a call can happen
  outside a step.
- **`/app/costs`** — window totals, the daily-budget guardrail against `AI_DAILY_BUDGET_USD`, a daily
  cost line with its data table underneath, cost per agent, cost per product feature (with the
  `workflow` values behind each), the cache hit rate split into table-life and process-life readings,
  and the prompt registry that makes a run's prompt version checkable.
- `packages/shared` gained `types-observability.ts` and seven runtime guards. The guards are the
  reason a shape change fails loudly instead of rendering an empty page, and `smoke:api` now feeds
  the **live** payloads through **the same guards the pages use** — so "the page renders" and "the
  contract has not drifted" are one check.
- `pnpm --filter @careerforge/web capture:pages` drives an installed Chrome/Edge over the DevTools
  Protocol (no Playwright, nothing downloaded) to screenshot both new pages at 1440 and 375, waiting
  for real data (`[data-run]`, `[data-total]`) before capturing and printing the rendered text.

### Changed — PHASE 11b

- The sidebar and command palette now list `/app/ai-runs` and `/app/costs` as live rather than as
  PHASE 10 placeholders.
- The narrow layout of the runs list is a **card list**, not a horizontally scrolling table: at 375 px
  the table pushed cost, status and time off-screen with nothing to indicate they existed.
- Timestamps are read on the clock they were written on. The API stores naive-UTC instants and
  `new Date('2026-09-24T10:00:00')` parses that as _local_ time — an eight-hour error for a reader in
  UTC+8, and one that looks entirely normal. `parseApiInstant` restores the missing zone and every
  column is labelled UTC.
- Cost charts stay honest about their inputs: with a zero total no line is drawn (a flat line at zero
  is a measurement claim), and the daily chart states that the API returns only days with activity
  instead of interpolating across the gaps.

### Fixed — PHASE 11b

- **A test that could never fail.** The cache-hit assertion read
  `assert any(...) or not any(...)` — true whether or not the flag worked. It now asserts the property
  that is actually checkable at the interface: every run carries a boolean `cacheHit`, including when
  it is `False`.
- **Two minutes rendered as `120.00 s`.** `formatDuration` reused the latency formatter's thresholds;
  a wall clock and a model call are not the same magnitude. It now scales to minutes and hours, and a
  clock that went backwards reports `—` rather than a negative duration.
- **"No ceiling" was drawn as 0%.** `dailyBudgetUsd = 0` means no guardrail is configured, not that
  zero dollars are allowed, so the ratio is `null` and the card says so — the same rule that makes
  `hitRate: null` read "not served yet" instead of `0%`.

### Known limitation — PHASE 11b

- `/ai-costs` does not zero-fill days with no runs, so the chart can only annotate the window
  ("2 of 7 days had activity") rather than draw a continuous axis. Zero-filling belongs in the
  backend query.
- The runs list shows the first page (50 rows) and says how many it returned; there is no pager or
  infinite scroll yet.
- The prompt registry shows the active version's digest, not prompt bodies; bodies live in
  `apps/api/src/careerforge_api/prompts/` and are versioned into the database on startup.

### Added — PHASE 11a · Metering every model call, and a cache that outlives the request

`llm_calls` and `ai_caches` have had models, migrations and indexes since PHASE 1 — and **no
writer**. The AI Runs page PHASE 1 promised would have shown runs with no calls beneath them, and
`/cache/stats` would have read an empty table. This phase closes the loop:

- `MeteredProvider` records one row per model call, from **what the provider reported**: tokens,
  cost, latency, and whether the answer came from the cache. It wraps the shared chain rather than
  rebuilding it, so the cache and the resilience state the app built once are the ones in use.
- `DatabaseCacheStore` gives the AI core's cache — synchronous, because a provider's hot path
  cannot await — a durable layer: it serves from memory and buffers events that `RunRecorder`
  flushes into `ai_caches` at the end of the request that owns the session.
- Seven endpoints: `/ai-runs`, `/ai-runs/{id}` (step chain plus every call), `/ai-costs`,
  `/ai-costs/by-agent`, `/ai-costs/by-feature`, `/cache/stats`, `/prompts`.
- The **budget guardrail is wired**: `Budget(daily_usd=…)` is built with the provider chain at
  startup, so exhaustion now degrades to the next provider instead of the ceiling being a
  configuration field nobody reads. `/ai-costs` reports the same number the guardrail enforces.
- Step traces carry **digests** of their inputs and outputs, not the payloads: an operator browsing
  runs should not be reading candidate material.

### Fixed — PHASE 11a

- **The metering decorator swallowed the degradation signal.** `MeteredProvider` forwarded only the
  protocol members, while the orchestrator reads `provider.last_chain_info` after every structured
  call to decide whether a run was degraded — so on the zero-key path a run flipped from `degraded`
  to `succeeded`. That exposed a **latent bug** too: `job_service` asked the executor for
  `executor.provider.name` on the _not-degraded_ branch only, which had therefore never run, and
  crashed with `AttributeError` the first time it did. The wrapper now delegates unknown attributes
  to the provider it wraps — a decorator that measures must not change what it measures — and the
  service reads the run record's own `model`/`provider`.
- **One flush inserted the same cache key twice.** A `set` followed by a `get` produced two events,
  and looking each up individually could not see the row the first had just added but not yet
  flushed: `UNIQUE constraint failed: ai_caches.cache_key`. Now fetched in one statement and updated
  in memory.
- **`_NOTES` was a string, not a tuple.** `list("…")` exploded the explanation into single
  characters, so `/ai-costs` served `notes: ["t","o","k",…]`. A parenthesised string is not a tuple.
- **A run said "no cache hit" while the cache page said otherwise.** `agent_runs.cache_hit` only
  reflected the executor's step cache; a provider-level hit now raises it too, and the difference
  between the two caches is documented rather than left to the reader.
- **`vector` health still claimed `not_implemented`**, which stopped being true in PHASE 3: the
  hybrid retriever answers retrieval today. It now reports `in_memory_index` and states both halves —
  what serves retrieval, and that the durable index is still missing. Under-reporting is as wrong as
  over-reporting.
- **An environment fault disguised as a regression**: the C: drive filled to zero bytes, so pytest
  could not create `tmp_path` (`OSError: could not create numbered dir … after 10 tries`) and 15
  tests failed with 16 errors. Regenerable caches were cleared and pytest's basetemp moved to D:.
  Recorded here because the failure looked exactly like a code regression.

### Known limitation — PHASE 11a

Most agent work goes through `structured_output`, whose provider returns the parsed schema and
discards its usage envelope, so **that path has no token count to record** — a limit of the core
interface rather than a gap in the metering. Those calls still record provider, latency and prompt
version; the token/cost plumbing is covered by tests through the `chat` path, and the notes on
`/ai-costs` explain why a zero-key deployment honestly reports zero. Fixing it properly means
changing the core's return shape, which belongs in its own change.

### Added — PHASE 10 · Recruiter View, and two layers of redaction

- `GET /public/candidate/{slug}` and `GET /public/candidate/{slug}/evidence/{skillId}` take **no
  token**. That is the feature: a recruiter opening a shared link should not have to create an
  account, and a page that needs a login is not a shareable page. Everything they can reach is
  already filtered and masked by the service — there is no owner-only field left to leak.
- `POST /public/publish`, `GET/PATCH /public/settings`, and `/app/settings` for the candidate:
  the publish switch, the share link, eight per-section switches, the per-skill hide list, and
  the list of what was masked at publish time.
- `/candidate/[slug]` renders on the **server**. This is the one page whose whole purpose is to be
  shared: it must produce its content for a stranger with no account, no token and no JavaScript
  round-trip, and a link preview or a crawler should see the same page a person does.
- The page's evidence is fetched on **click**, through the same anonymous endpoint, so the first
  paint stays small and the request that expands a citation is itself the proof that no account
  is needed.
- `public_profiles` gains `public_payload` and `pii_findings` (migration `0008`).

Four decisions that are all about consent:

- **Privacy switches apply on read, not only on publish.** The stored projection is re-filtered
  through the candidate's _current_ switches every time it is served, so unchecking a section is
  true immediately rather than at the next republish. The window between "I turned that off" and
  "it is off" is exactly where a leak would live.
- **PII is scanned twice** — once while the agent builds the page, and again on the payload that
  is about to be served. The asymmetry decides it: a false negative publishes somebody's phone
  number, a false positive costs a masked string.
- **The candidate is told what was removed.** Silence about a redaction is indistinguishable from
  having had nothing to redact.
- **A public view costs no model call.** The narrative is generated once at publish and stored; a
  page a recruiter can refresh should not bill the candidate per view. And a `storage_scope=local`
  account cannot publish at all (403): a public URL contradicts "my data does not leave this
  machine".

### Fixed — PHASE 10

- **The one endpoint strangers can reach returned 500.** `row.user` is a lazy relationship, and
  touching it inside an async session raises `MissingGreenlet`; nine of sixteen tests failed with
  that error at once. Now eagerly loaded, with the reason in the docstring.
- **The "no PII published" check was passing vacuously.** The first live run produced a public page
  with zero skills and zero highlights — the résumé had been uploaded and analysed but never
  _imported as a profile_, so there was no candidate material to leak and the redaction assertion
  had nothing to prove. The live script now imports the profile and asserts the **source material
  really carries the email** before asserting that the published page does not.
- **The published page reported zero views forever.** The counter lives on the row; the page's meta
  never read it, so the footer said "0 views" while the owner's panel said 3. `public_profile` now
  returns the count alongside the projection.
- **`ALTER TABLE` cannot put a column where the model declares it.** The migrated-vs-models guard
  compares columns as an ordered list, and appending two columns to `public_profiles` broke it.
  Columns are compared as a set now (name, type, nullability, primary key) while indexes, uniques,
  foreign keys and checks are still compared in full — a deliberate narrowing, with the reason in
  the test, because column _order_ is the one thing a migration cannot preserve and no query
  depends on it.
- `packages/shared/src/api/types.ts` reached 552 lines. Split by domain into
  `types-applications.ts`, `types-analytics.ts` and `types-public.ts`, with `types.ts` keeping the
  envelope and re-exporting the rest, so every existing import path still works.

### Added — PHASE 9 · Career analytics, and the discipline of a small sample

- `careerforge_ai/analytics/` — the funnel, the rates, the correlation, the categories and the
  trend, as **pure functions in the framework-free core** (ADR-022). No model produces a number
  here: every figure is arithmetic over rows the candidate's own activity created, so one
  implementation serves the API, the tests and the eval harness. 28 unit tests pin the
  boundaries — an empty cohort, one application, every card rejected, a skill that splits the
  cohort into one group, a month with no activity.
- `GET /analytics/funnel`, `/rates`, `/skill-correlation`, `/categories`, `/timeline`
  (FR-14.1–14.5), each carrying `meta` with its window, its sample policy and the **basis of
  every stage**. Five endpoints share one cohort read, so the panels of one page cannot describe
  two different sets of applications.
- `/app/analytics`: a hand-drawn SVG funnel, the rate cards, the correlation table, the category
  table and the monthly trend, behind a 7d/30d/90d/all switcher. 21 frontend tests, including the
  two the exit criteria name — an insufficient sample says 样本不足 next to the number, and the
  switcher refetches every panel.

Three decisions the numbers forced:

- **The funnel counts what was reached, not what is current.** A card applied → interviewed →
  rejected is `rejected` on the board and _was interviewed_ in the funnel. PHASE 8b documented the
  same distinction when it defined the dashboard's `interviews` as a snapshot; this is the other
  half of it, and the live check prints both numbers beside each other.
- **A rate never travels alone.** Each card carries its numerator, denominator, a Wilson 95%
  interval and a `sufficient` flag; the minimum sample is 5 and the response says so. A rate of
  100% from one interview ships with the interval that admits how little is known, and `0/0` is
  `null` rather than 0%.
- **A step rate can be undefined.** Zero offers out of zero final rounds is `null`, not 100% — the
  first version of this engine called it a perfect conversion. The test that catches it now states
  the distinction between "a real zero" (no replies from one application) and "no denominator".

### Fixed — PHASE 9

- **The trend chart's month-prefix loop never terminated.** Extending the axis backwards from the
  earliest activity walked _further_ back each iteration, because every earlier month is also less
  than the window's first key: 36 seconds of CPU with no output, and the test that reaches that
  branch hung instead of failing. It walks forwards now, and is bounded.
- **`?range=` was silently ignored.** The handler's parameter was named `range_key`, and FastAPI
  takes the query-parameter name from the parameter — so `?range=7d` fell back to the default 30d
  and `?range=1y` answered 200 with a 30-day result. Now aliased. A defect that raises no error and
  returns the same answer for every window is the kind that survives a demo.
- **Every application appeared twice on the timeline.** The board wrote a `career_events` milestone
  when a card was created _and_ when it was actually applied to, so the trend counted each
  application twice. `wishlist` is no longer a milestone: adding a bookmark is not an act. The
  audit trail still records the creation, which is where that belongs.
- **`Counter` cannot hold fractional weights.** The category weighting multiplies by skill weight,
  and `Counter[str]` is typed over `int` — mypy flagged the assignment that would otherwise have
  silently truncated every preferred-skill weight to zero.
- **A schema comment claimed the wrong denominator.** `cohortSize` was documented as "the
  denominator of the funnel and of every rate below it"; it is really the pool (cards created in
  the window, wishlist included) while the funnel's denominator is its first stage. Found by
  comparing the docstring against live output. A wrong note about what a number means is worse than
  no note, because it reads as verified.

### Added — PHASE 8c · The board, and the frontend's first tests

- `/app/applications`: seven columns in the documented order, cards carrying the FR-13.3 fields
  (company, role, location, salary, status, match score, date, notes), a create dialog for the
  referral that has no posting yet, and a grouped list view on narrow screens where seven
  columns and page-scrolling fight each other.
- **A keyboard path that can actually change columns.** dnd-kit's stock
  `sortableKeyboardCoordinates` only walks the sortable items of the column the drag started in,
  so with it a card picked up by keyboard can be reordered within its column and never moved to
  another one — the single thing the board is for. `lib/keyboard-coordinates.ts` is ours: the
  drag's current rectangle is the origin, the nearest droppable in the pressed direction is the
  target, and because columns are droppables too an _empty_ column is reachable. `→` moves one
  column, `→→` moves two (the position accumulates), `↓` reorders within the column.
- A card menu (move / archive / delete) that calls exactly the same mutation as a drag. It is the
  primary path on touch, the discoverable path for anyone who does not know a board is draggable,
  and the only place archive and delete live.
- **Vitest + Testing Library**, the frontend's first test runner: 32 tests covering the board's
  arithmetic, its rendering, its keyboard drag, and its rollback. The runner exists because the
  phase's exit criterion is an accessibility assertion, and an a11y claim that nothing executes is
  a claim, not a guarantee.
- `smoke:api` grew from 7 checks to 11: it now creates a card through the real client, runs the
  new `isApplicationBoard` guard against the real response, asserts the seven columns arrive in
  the documented order, reorders, and deletes — cleaning up after itself, because a smoke test
  that leaves cards behind changes the numbers the next run measures.

### Fixed — PHASE 8c

- **`pnpm-workspace.yaml` carried pnpm's own error text as a value.** `allowBuilds.esbuild` was
  literally `set this to true or false`, copied from the message it was meant to silence, so every
  install failed with that same message. It is `true` now, with both dependencies that need to
  compile named and explained.
- **Value imports inside a workspace package broke one of the three runtimes that load it.**
  `packages/shared` is consumed as source by Next's bundler, by Vitest, and by Node's
  `--experimental-strip-types` loader (the smoke script). Node resolves specifiers literally, so
  turning `guards.ts`'s `./types` import from a type-only import into a value import (for
  `APPLICATION_STATUSES`) made the smoke test fail with `ERR_MODULE_NOT_FOUND` while the app and
  the tests stayed green. Package-internal imports now carry explicit `.ts` extensions, permitted
  by `allowImportingTsExtensions` (ADR-023).
- **The README claimed the demo account was seeded with a complete candidate** — "3 projects, 9
  skills, ~180 evidence records, 12 analyzed jobs, 16 applications, 5 interviews. No page is ever
  empty." A fresh database has an empty demo account; the numbers described a seed script that
  does not exist yet. The section now says what the seed actually creates and why the rest is
  deliberately absent until the surfaces it fills exist.
- The dashboard's local fallback definitions for `applications` / `interviews` / `offers` had
  drifted from the API's own wording (the `interviews` fallback described the funnel meaning while
  the API ships the snapshot meaning).

### Notes — PHASE 8c

Pointer dragging is exercised by the component tests only in its _decision_ logic: jsdom has no
layout and no `PointerEvent`, so the gesture itself — and the visual result of 280px columns on a
real screen — is verified in a real browser in PHASE 13. What is verified now: the keyboard drag
end to end, the menu path, the optimistic render before the server answers, the rollback and its
toast, and the board arithmetic against the server's rule.

### Added — PHASE 8b · The application tracker, and a dashboard that stops guessing

- `applications`, `application_events` and `career_events` (§2.7, §2.11) with migration
  `0007`, verified column-for-column against the ORM models.
- Nine endpoints: the board, list, create, detail, update, reorder, events, delete, plus
  `POST /jobs/{id}/applications` — FR-13.5, one click from "I analysed this posting" to
  "I am tracking it".
- `GET /applications/board` returns all seven columns in the documented order, empty ones
  included, with `counts` and `total`. A missing key would force the client to guess, and
  a guessed board draws the wrong columns the day a stage is added.
- **Every status change writes an `application_events` row**, which is what PHASE 9's
  funnel will read. A move to the _same_ status writes nothing: a within-column drag is a
  reorder, and an event log full of `applied → applied` makes one application look like
  several.
- `career_events` finally has a writer: the milestones a candidate would put on a CV
  timeline (applied, interviewed, offered, rejected). Intermediate board moves stay in the
  event log. A `dedupe_key` plus unique constraint means dragging a card back and forth
  cannot inflate the timeline with the same milestone.
- The dashboard's `applications` / `interviews` / `offers` are real counts. PHASE 5 shipped
  them as named zeros in `meta.unavailable` because no data source existed; that list is now
  empty and the definitions say which arithmetic each number is — including that
  `interviews` is a board snapshot, not the ever-reached funnel.

### Changed — PHASE 8b

- **The board is a snapshot, not a view over live postings.** A card copies the company,
  role, location and the system's last computed match score at creation. Deleting a
  posting therefore leaves the card standing (its `jobId` goes null) instead of erasing
  the user's history as a side effect of housekeeping.
- **A client cannot post a score.** `matchScore` is refused on input; the number on a card
  is evidence, not a claim. With no stored match it is `null`, never `0` — "never scored"
  and "scored zero" are different facts.
- **Drop positions are re-derived server-side.** A drag-and-drop client is a hostile source
  of ordering data (duplicates, gaps, a whole column in one gesture), so a position is an
  input to rendering, not a source of truth.
- No transition is forbidden. The board is dragged, so candidates mis-drop, rewind after a
  rejection and reopen an old wishlist item; rather than fight the user, every move is
  recorded. `applied_at` is stamped when a card first leaves `wishlist` and is not erased by
  a rewind, and `offer`/`rejected` clear `next_action_at`.

### Fixed — PHASE 8b

- **The JD parser could not read a company name.** `_COMPANY_RE` demanded a `公司：` label,
  while the most common Chinese layout puts the company unlabelled on line one. Every card
  came out with a blank company and every parse lost the 15% `company_found` weight. The
  parser now reads a title block — unlabelled first line, `Company — Role` on one line, or
  the labelled form — requiring a name-shaped candidate, ≤ 24 characters, free of prose
  words, and neither a role line nor a section header; `我们是一家专注于工业智能化的公司`
  is therefore still not read as a company.
- **The eval corpus labelled a company for all 120 postings and nothing scored it.** The
  gold field was dead data. `jd.company_accuracy` now measures it in both directions —
  inventing a company for a posting that names none is exactly the error the rule exists to
  prevent. Measured 1.0000 on 120 samples, with `required_skill_f1` (0.8832) and
  `distractor_leakage_rate` (0.0000) unmoved.
- `/applications/board` and `/applications/reorder` are declared before
  `/applications/{id}`: registered the other way round, a literal path is unreachable and
  the endpoint answers "Application not found" for its own documented URL. There is a test
  that would catch it.
- Three test assertions counted rows across the whole session-shared test database instead
  of one account's. Each passed in isolation and failed in the full run — the argument for
  running the whole suite every phase, and for tenant-scoping every assertion.

### Added — PHASE 6b · The claim gate, made durable

- `resume_versions`, `resume_claims` and `claim_evidence` (§2.9) with migration `0006`,
  verified column-for-column against the ORM models.
- `POST /resume/optimize`, `GET /resume/versions`, `GET /resume/versions/{id}`,
  `DELETE /resume/versions/{id}`, plus the documented `POST /evidence/validate` and
  `/evidence/validate/batch` (≤ 20).
- Every bullet is gated and stored with its verdict: status, confidence, the rules that fired,
  the safer rewrite, and — for a supported claim — the citations that support it. The
  candidate's own wording is kept beside the rewrite so a reviewer can judge whether the
  optimised version invented something.
- A claim can exist without a résumé version, which is what makes the Validator page possible:
  a sentence someone is _considering_, checked before it reaches a document.

### Fixed — PHASE 6b

- **Without a retriever the gate did not degrade — it rejected everything.** The retrieval phase
  reported "no retriever configured" and returned zero hits, so "使用 STM32 与 FreeRTOS 开发电机
  控制固件" came back unsupported with `skill_not_in_graph`, while the graph held eight pieces of
  evidence for those skills. The API now builds the project's own hybrid retriever (BM25 +
  vectors, RRF-fused, ADR-0006) over the caller's stored evidence.
- **The rules phase runs before retrieval and reads caller-supplied material**, which the API was
  not passing — so every technical noun in a claim was reported as unmentioned, in the same
  response that cited a document naming it. The single-claim path now supplies the candidate's
  material, which is what the contract asks of a caller that holds it.
- The API's bullet field is `original` while the engine reads `text`; the mismatch made every
  bullet look empty and the optimiser politely reported having nothing to rewrite. Mapped
  explicitly — a silent failure rather than an error is the worst kind here.
- `integrity_score` and `claim_stats` were copied from an engine field that can arrive empty,
  leaving a version whose summary read `{}` beside a list of claims. Both are now computed from
  the claims actually stored.

### Fixed — PHASE 6c · The three recorded limitations, closed

- **A safer rewrite is no longer offered when it would still assert something unsupported.** If
  stripping the numbers leaves a technology name the evidence cannot carry, keeping the name and
  deleting the digits states the same unsupportable thing while hiding that something was removed.
  Rule blockers now decline to rewrite in that case; a blocker that is _only_ a number still gets a
  rewrite, because removing the number is exactly the correct repair.
- **The blocking rules no longer soften under retrieval.** A rule blocker with hits used to fall
  through to `partially_supported`, which relabelled a fabricated number with a gentler verdict.
- **`contradicted` now means contradicted.** It is reserved for `timeline_conflict` and a model
  reporting `contradicting_evidence`; rule blockers — no comparable measure, missing technology,
  superlative language — are `unsupported`. Nothing refuted the fabricated sentence, so calling it
  refuted was an overclaim of the gate's own.
- **A dangling measure verb is removed wherever it lands**, not only at the end of a sentence:
  `_DANGLING_MEASURE_RE` anchors on `(?=[，,；;、]|$)` and both rewrite branches share one tidy pass.
- **The single-source downgrade explains itself**: `single_source_only` is appended to `reasons`
  (`目前只有 1 条独立来源；达到 2 条独立来源才能判为 supported。`), so the status is no longer a
  verdict without a reason.

Verified against a running API on a fresh database: the fabricated sentence returns `unsupported`
with all three reasons; the supported one gains the `single_source_only` note; neither gets a
rewrite. Every eval metric is unchanged — `numeric_rejection_rate 1.0000`,
`over_support_rate 0.0000`, `safer_rewrite_rate 0.6222`, `support_recall 1.0000` — so the three
fixes changed what the gate _says_, not how strict it is.

### Known limitations — PHASE 6c

Recorded in `docs/ROADMAP.md` rather than left implicit: after a measure verb is removed the clause
can be left as a bare noun phrase (`响应时间缩短了 40%，并完成了压测` → `响应时间，并完成了压测`);
the rule cannot honestly rebuild the deleted predicate, so it keeps the clause and leaves it to the
candidate. Separately, the heuristic extractor still splits free-form Chinese résumés imperfectly —
marked `origin=heuristic` and correctable, but imperfect.

### Added — PHASE 2b · Career entities and the profile import path

- `educations`, `experiences`, `projects`, `achievements` and `profile_skills` (§2.2) with
  migration `0005`, verified column-for-column against the ORM models.
- `POST /profile/import` extracts entities from text or from a stored document and persists
  them; `GET /profile` returns what is stored. Both are the _assembled_ profile every other
  feature reads, so what a client shows and what the system scores cannot diverge.
- `origin` is returned on every entity and every declared skill: a row a model extracted and
  nobody has checked stays visibly different from one a candidate corrected.
- Three consumers were rewired to read real entities — the graph builder, the match engine and
  the dashboard — which is what the tables were for.

### Fixed — PHASE 2b

- **A declared skill with evidence was reported as a gap.** Declarations come from résumé
  extraction with an `evidence_count` of zero, and the match engine reads that as "claimed but
  unproven" — so STM32, FreeRTOS and CAN were all listed as gaps while the graph held eight
  pieces of evidence for each. The declared skills and the evidence graph are now merged: levels
  are kept, counts are corrected, and skills that have evidence but were never declared are
  added. Measured on a fresh database: `skill` 0.0 → **39.16**, `evidence` 0.0 → **87.0**, total
  score 16.4 → **40.76**, and the gap list went from three false gaps to `['autosar']`.
- **Re-importing a profile orphaned its graph edges.** The writers deleted and re-inserted rows,
  so every project and experience got a new UUID and the edges pointing at the old ones stopped
  resolving — the canvas showed `project:de6dd367`, a node nobody can open. `dedupe_key` exists to
  identify the same entity across imports; the writers now upsert on it, and an entity the source
  really dropped is deleted together with its edges. Verified live: a second import leaves the
  graph and the score identical, with zero placeholder nodes.
- **The documented `origin` CHECK could not express the extractor's own vocabulary.** §2.2 lists
  `llm` / `user_corrected` / `import`, while the AI core's `Origin` enum also carries
  `heuristic` — the zero-key path. Written as documented, every heuristic extraction would have
  violated the constraint; recording it as `llm` would have been a false claim about provenance.
  The value is added in all three places (model, migration, docs), with the reasoning recorded.

### Added — PHASE 5 · Dashboard endpoint and the first live frontend↔API run

- `GET /dashboard` implements the `DashboardResponse` contract the frontend has carried since
  PHASE 0: profile strength from the deterministic engine, the six documented metrics derived
  from stored rows, a skill radar built from the evidence graph, and concrete next actions.
- `meta.unavailable` names the metrics whose data source does not exist yet (the application
  tracker belongs to PHASE 8). A zero on a dashboard reads as "you have none", which for a
  system that has never seen an application would be a claim it cannot make; the UI renders
  "尚未接入" for those cards instead of the zero.
- `meta.definitions` ships each metric's actual 口径 with the number, and the UI prefers it
  over its local copy, so the label and the arithmetic cannot drift apart.
- `pnpm --filter @careerforge/web smoke:api` runs the **real** frontend client and runtime
  guards against a live API — the first time the two halves of this project were executed
  against each other. Seven checks: demo login, the dashboard guard, health normalisation,
  the evidence graph, the job list, a match, and the error envelope with its requestId.

### Notes — PHASE 5

- `/dashboard` is deliberately uncached, unlike the documented "含缓存": every number comes
  from rows a user may have changed seconds earlier, and a cached home page that disagrees
  with the page you just left is worse than a 30 ms query. The cache belongs on the expensive
  `/analytics/*` aggregations.
- Browser verification (hydration, interaction) still has not run: it needs Playwright, which
  is PHASE 12. What is verified here is the build, every route serving, the client/server
  contract, and the dashboard strings reaching the client bundle.

### Added — PHASE 4 · JD Analyzer and explainable matching

- `jobs`, `job_skills` and `job_matches` (§2.6) with migration `0004`, verified
  column-for-column against the ORM models. `job_skills` carries an application-generated
  `dedupe_key` because the documented uniqueness spans a **nullable** column, and `NULL`
  never compares equal in a unique index on either backend.
- `POST /jobs/analyze`, `GET /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/skill-tree`,
  `DELETE /jobs/{id}`, `POST /jobs/{id}/match` and `GET /jobs/{id}/match`.
- Every requirement carries the posting's own sentence (`jdEvidence`), so a reader can check
  that the parser did not invent it. Analysis and matching are synchronous, as documented.
- The match payload keeps the documented shape: five dimensions with their weights and
  weighted contributions, `why.formula` holding the actual formula, and the strengths, gaps
  and unknowns as explicit camelCase models. Each run is stored, so a changed score has a
  before and after.
- Pasting the same posting twice updates one job (`description_sha256`), keeping its match
  history on a single card.

### Fixed — PHASE 4

- **The evidence dimension measured the wrong list.** It was computed over the _highlighted_
  skills — those whose effective level clears 0.5 — so a candidate satisfying five
  requirements, each with evidence behind it, scored **0.00** on the dimension whose entire
  purpose is to measure that evidence. Measured live: evidence 0.0 → 87.0, total score
  11.56 → 20.26. A regression test now covers the most common shape (one piece of evidence,
  MODERATE level).
- A freshly inserted job triggered a synchronous lazy load of its skills relationship and
  returned a 500 (`MissingGreenlet`); the repository refreshes the relationship it just
  wrote.
- `strengths``/`gaps`/`unknowns` leaked the engine's snake_case keys into an otherwise
  camelCase payload — the same class of defect as the locator in PHASE 3.
- `test_models.py` outgrew the 500-line guard; split into `test_schema_inventory.py` (what
  the schema declares) and `test_models.py` (what the database enforces) rather than
  allowlisted.

### Added — PHASE 3 · Evidence Graph

- `evidence` and `evidence_links` (§2.5) with migration `0003`, verified column-for-column
  against the ORM models. The confidence formula is a database `CHECK`: the stored score
  must equal the formula applied to the stored five factors, so the number a UI shows can
  be recomputed in SQL. The cap is spelled with `CASE` rather than PostgreSQL's `least()`,
  because SQLite spells it `min()` and CI runs both dialects.
- `GET /evidence`, `GET /evidence/{id}`, `GET /evidence/{id}/trace`, `POST /evidence`
  (manual, with the confidence computed server-side and unknown fields refused),
  `DELETE /evidence/{id}`, `GET /evidence-graph`, and `POST /documents/{id}/analyze`.
- `analyze` builds evidence and skill edges from a stored document's chunks. It is
  synchronous — a documented exception to the 202 convention — because it is deterministic,
  CPU-only and bounded by the chunks already in the database. Re-running it is idempotent.
- Evidence is de-duplicated on `(user_id, kind, content_hash)` and edges on their
  five-tuple, so re-analysis cannot inflate the graph.

### Fixed — PHASE 3

- **Hand-typed evidence was scored as an uploaded document** (0.80), letting a candidate
  type a claim and receive near-document-grade confidence. It now carries the self-report
  tier (0.55), with a measured test pinning the gap to the authority weight.
- **Five relations existed as in-memory edges with no stored link**, including every
  candidate `HAS` edge. The in-memory graph looked complete; the persisted one lost its
  root and every education/experience/achievement node. An invariant test now asserts the
  edge set equals the link set.
- **`include_orphans` was silently ignored** whenever a `GraphQuery` was passed — which is
  every API call — so `includeOrphans=true` did nothing.
- The `stats` block described the whole graph while the payload carried a subgraph, so a UI
  could show "129 nodes" above a ten-node canvas. `stats` describes the response now and
  `totals` describes the graph.
- The locator leaked the store's snake_case keys (`char_start`) into an otherwise camelCase
  payload, and engine-derived evidence ids were not remapped onto the stored rows, leaving
  edges that no query could resolve.

### Added — PHASE 2 · Candidate Profile (documents)

- `documents` and `document_chunks` tables (`docs/DATABASE.md` §2.3) with the migration
  `0002_documents`, verified column-for-column against the ORM models by
  `tests/test_migrations.py`.
- Document ingestion in the AI core: PDF (pypdf), DOCX (python-docx), Markdown and plain
  text, with a GB18030/Big5 decoding ladder for résumés saved by Chinese Windows editors,
  YAML front-matter stripping, and honest reporting of what could not be read — a scanned
  PDF is reported as needing OCR rather than returned as an empty document.
- `POST /documents` (multipart, `202` + task id), `GET /documents`,
  `GET /documents/{id}`, `GET /documents/{id}/chunks`, `GET /documents/{id}/text`,
  `DELETE /documents/{id}`. Uploads are spooled and parsed by the queued
  `document.ingest` worker, which registers the same handler set in both the API process
  and the standalone worker.
- Re-uploading identical bytes is idempotent (`sha256` unique per user), so a résumé
  cannot fork the evidence graph.
- Local Mode (`storage_scope = 'local'`) and `retainRawText: false` store neither the text
  nor the chunks; the API says which of the two applies instead of showing an empty box.

### Fixed

- `DELETE` no longer returns a JSON envelope body on `204` (RFC 9110 §6.4.1 forbids a body
  on that status).
- A failed parse is now a stored fact (`parse_status` / `parse_error`), committed before
  the request transaction would roll it back.
- Unknown document kinds and unreadable file types are refused with `400` at upload time
  rather than accepted and failed later in the worker.
- The `status` filter on `GET /documents` is applied in SQL; filtering after a `LIMIT`
  returned short pages whose total disagreed with their items.

### Added — PHASE 1 · Platform, AI core and API

- `packages/ai`: deterministic orchestration (custom DAG executor), 4 provider
  implementations including a zero-key heuristic provider, hybrid retrieval (BM25 + RRF +
  exact vectors), the evidence graph with a five-factor confidence formula, and 9 agents.
- `apps/api`: application factory, response envelope, error taxonomy, request-id,
  rate limiting, JWT auth with a demo account, and an idempotent background queue.
- `apps/web`: Next.js 15 shell with the design tokens, AppShell and six routes.
- `evals/`: three labelled suites with committed results and documented weaknesses.

### Added — PHASE 0 · Product design

- `docs/PRD.md` — product definition: personas, evidence-graph concept, deterministic
  confidence formula, 18 requirement groups with acceptance criteria, non-goals, risks.
- `docs/ARCHITECTURE.md` — layered architecture, custom agent orchestrator design,
  9 agents, 10 workflows, hybrid RAG pipeline, scoring engine, security architecture.
- `docs/DATABASE.md` — 32-table schema, index strategy, pgvector configuration,
  SQLite/PostgreSQL compatibility layer, seed-data self-consistency requirements.
- `docs/API.md` — REST surface with response envelope, error-code table, SSE contracts,
  rate limits, and a full demo call chain.
- `docs/UI.md` — design system (tokens, typography, motion), 54-component inventory,
  sitemap, page-by-page specifications, accessibility and responsive matrices.
- `docs/ROADMAP.md` — 16 phases with exit criteria, dependency graph, risk register.
- `docs/DECISIONS.md` — 22 ADRs including rejected alternatives.
- Repository skeleton, `README.md`, `.env.example`, community health files.

### Notes

- Every metric quoted in the README and `evals/README.md` comes from a committed artifact
  (`reports/eval-report.json`), and unmet targets are reported as unmet.
