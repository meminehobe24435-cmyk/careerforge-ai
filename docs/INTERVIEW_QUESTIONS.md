# Interview questions — preparation notes

This is **preparation, not a script**. Each entry gives you the shape of an answer: a short version you
can say in one breath, the specifics that make it concrete, and the repository artefact the number came
from. Say it in your own words; if you find yourself reciting, you have memorised the wrong thing.

Three rules this file follows:

1. **Every number is traceable.** If a figure is here, it is in `reports/eval-report.json`,
   `reports/confidence-calibration.json`, `reports/coverage-summary.md`, `reports/release-proof.json`,
   `reports/release-readiness.md`, `docs/ROADMAP.md` or `docs/QUALITY.md`. Nothing is estimated, and
   nothing is a round number chosen because it sounds good.
2. **`docs/INTERVIEW.md` Q1–Q18 already covers the spoken versions** of evaluation, calibration,
   unsupported claims, the graph, the hybrid-retrieval loss and the CORS story. Those questions appear
   here too, with a short answer and a pointer, plus only what is _new_ (exact numbers, file paths,
   the arguments that are not in that file). Do not read both end to end before an interview.
3. **Weaknesses are part of the answers.** The last two sections are deliberately about what was not
   measured and what is still wrong. An interviewer who finds a gap you did not mention stops
   believing the rest.

Where a term is naturally Chinese in this codebase — a rule name, a case id, a UI string — it is
quoted in Chinese, because that is what is in the repository.

## Index

| Category                                                                                                             | Questions | What it covers                                                      |
| -------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------------------------------------------------- |
| [Product](#product)                                                                                                  | Q1–Q5     | the evidence-first premise, RAG, and what the product refuses to do |
| [Frontend](#frontend)                                                                                                | Q6–Q9     | Next.js, React Flow, honest empty states, the responsive gates      |
| [Backend](#backend)                                                                                                  | Q10–Q13   | FastAPI, the envelope, `null` vs `0`, rate limiting                 |
| [Database](#database)                                                                                                | Q14–Q18   | PostgreSQL, pgvector, Redis, migrations, CHECK constraints          |
| [RAG](#rag)                                                                                                          | Q19–Q22   | chunking, Hit@K, MRR, why the hybrid loses to BM25                  |
| [LLM](#llm)                                                                                                          | Q23–Q26   | hallucination, timeouts, malformed JSON, the provider chain         |
| [Agent](#agent)                                                                                                      | Q27–Q29   | the orchestrator, failed runs, how the interview is planned         |
| [Evaluation](#evaluation)                                                                                            | Q30–Q38   | accuracy, P/R/F1, macro F1, the gate, calibration, ECE              |
| [Observability](#observability)                                                                                      | Q39–Q42   | cost, run traces, usage statuses, showing degradation               |
| [Testing](#testing)                                                                                                  | Q43–Q49   | the four layers, CORS, coverage, test independence, mutation        |
| [Deployment](#deployment)                                                                                            | Q50–Q53   | Docker, CI, how you deploy, what is blocked                         |
| [Security](#security)                                                                                                | Q54–Q57   | prompt injection, tenancy, secrets, PII                             |
| [Trade-offs](#trade-offs)                                                                                            | Q58–Q61   | debt, SQLite, non-goals, the next month                             |
| [Answers to rehearse out loud](#answers-to-rehearse-out-loud)                                                        | —         | eight one-sentence stories with a pointer each                      |
| [Questions whose honest answer is: I did not measure that](#questions-whose-honest-answer-is-i-did-not-measure-that) | —         | where the evidence stops                                            |
| [If you had another month](#if-you-had-another-month)                                                                | —         | the five things that are actually next                              |

---

## Product

### Q1 — Why an Evidence Graph?

**Short answer.** Because the hard part of an AI résumé is not writing, it is proving. The graph is the
candidate's own material decomposed into addressable claims and sources, so every generated sentence
can be pointed back at something real. Without it, "the model wrote it" is the only provenance the
system has.

**Deep dive.**

- Nodes are evidence rows with a computed confidence (five weighted factors), linked to the skills,
  projects, experiences and requirements they support — the link table is `evidence_links`.
- It is the single source the claim gate retrieves over, the matcher scores against (the `evidence`
  dimension), and the graph page draws, so one artefact serves three consumers instead of three
  caches.
- The confidence is arithmetic, not an opinion: five weighted factors (authority, recency,
  specificity, corroboration, extraction quality) in one importable module that both the engine and
  the database CHECK constraint read, version `confidence@1.0.0`, with a test asserting the weights
  sum to 1.0.
- Spoken version of the "why" is `docs/INTERVIEW.md` Q11; the ADR that rejected a graph database is
  ADR-005.

**Evidence in repo.** `packages/ai/careerforge_ai/graph/builder.py` · `graph/query.py` ·
`packages/ai/careerforge_ai/scoring/weights.py` (`CONFIDENCE_WEIGHTS`, `CONFIDENCE_FORMULA`) ·
`docs/DECISIONS.md` ADR-005 · `docs/INTERVIEW.md` Q11.

### Q2 — Graph vs vector DB?

**Short answer.** They answer different questions, and this product needs both: a vector index answers
"what text is similar to this query", while the graph answers "which of _my_ skills does this evidence
actually support, and how strongly". Similarity is not support, and the gate's whole job is the
difference.

**Deep dive.**

- Retrieval over evidence uses both arms — BM25 and vectors, fused with RRF, `k = 60` — and returns
  fragments; the graph is what turns fragments into a claim about a skill.
- A graph database was rejected (ADR-005) because the access patterns are shallow and set-shaped: the
  adjacency table plus one indexed join answers every query the product makes, and adding Neo4j would
  add an operational dependency and a second consistency domain for no query it currently needs.
- The honest limitation lives in the same place: the durable vector arm is **not implemented** —
  `/system/health` reports `vector: degraded (in_memory_index)`.

**Evidence in repo.** `packages/ai/careerforge_ai/rag/fusion.py` (`RRF_K = 60`) · `rag/store.py` ·
`apps/api/src/careerforge_api/services/system_service.py` (`probe_vector`, reason `in_memory_index`) ·
`reports/release-proof.json` `notRun` entry "Durable vector index (pgvector / embeddings table)".

### Q3 — Why RAG at all?

**Short answer.** Because the alternative — putting a candidate's whole history in the prompt — is
unbounded, unverifiable and expensive, and because the gate needs _citable_ fragments rather than a
summary. Retrieval gives every verdict a list of sources with locators, which is what makes
"unsupported" a checkable statement instead of a refusal.

**Deep dive.**

- Retrieval output feeds the decision phase as `evidence_text` plus per-source confidence; the verdict
  carries the reasons and the sources, so the API response can show why.
- It also bounds cost: the prompt carries the retrieved fragments, not the corpus.
- Degradation is explicit: when retrieval raises, the verdict is still produced and the reason says
  retrieval was unavailable — a 500 there would be the worst possible behaviour for a verification
  product (that 500 was a real defect, `docs/ROADMAP.md` PHASE 12 finding 7).

**Evidence in repo.** `packages/ai/careerforge_ai/rag/retriever.py` · `agents/validator.py` ·
`docs/INTERVIEW.md` Q2 · retrieval numbers in `reports/eval-report.json`
(`retrieval.hit_at_5` 0.9661, `retrieval.mrr` 0.9011).

### Q4 — Why not a pure LLM?

**Short answer.** Because the model is the component that cannot be audited, reproduced or held to a
number. It judges support for one sentence at a time; it never produces a score, a confidence or a
status, and the rule layer runs before it. That split is what makes every figure in the UI
reproducible.

**Deep dive.**

- Order matters: deterministic rule blockers fire first (a quantified claim with no quantitative
  evidence is rejected before the model is consulted), then retrieval, then the model's verdict, then
  arithmetic decides the status and confidence.
- The product is useful with **no API key at all**: the provider chain ends at a deterministic
  heuristic provider (ADR-009), which is a first-class deployment, not a mock.
- Cost and latency follow from the same design: most requests never reach a vendor.

**Evidence in repo.** `packages/ai/careerforge_ai/agents/validator_decide.py` ·
`agents/validator.py` · `docs/DECISIONS.md` ADR-006 and ADR-014 · `docs/INTERVIEW.md` Q7 and Q10 ·
`docs/QUALITY.md` §1.

### Q5 — What does the product refuse to do?

**Short answer.** It refuses to state more than the evidence supports, and it refuses to look like it
did. Three concrete refusals: it will not put a claim on a résumé without corroboration from more
than one independent source and a confidence above the gate's threshold; it will not print `0` where
the truth is "not reported"; and it will not draw a chart of data it does not have.

**Deep dive.**

- The refusals are enforced in the decision layer, not in copy: `skill_not_in_graph` is a blocker when
  the taxonomy recognises the technology and the material does not contain it.
- The `null`-vs-`0` rule reaches the database: nullable count columns, `usage_status`, and sums that
  skip unknowns, so a total is a documented floor rather than a fabricated exact figure.
- The UI follows: a stored match that cannot report evidence coverage prints `—` and names the
  endpoint that does, rather than `0%`.

**Evidence in repo.** `.env.example` (the claim thresholds and the minimum-source count, by name) ·
`packages/ai/careerforge_ai/parsing/skill_mentions.py` ·
`apps/api/src/careerforge_api/services/dashboard_service.py` and the `null` handling in
`apps/web/src/lib/jobs-api.ts` · `docs/ROADMAP.md` PHASE 13.

---

## Frontend

### Q6 — Why Next.js?

**Short answer.** The product is a data-dense authenticated application plus one server-rendered public
page, and Next.js App Router covers both without a second framework. Server components render the
recruiter page without a login, and the authenticated shell is client-side, which is where the session
lives.

**Deep dive.**

- The public candidate page is server-rendered on purpose: a recruiter opens a link and has to read it
  with no account, no client bundle dependency for first paint (ADR-002).
- The public API base URL is a **build arg**, not a runtime variable — that is a real constraint of
  inlining public env vars, and it is documented as such in `docs/DEPLOYMENT.md` §2 rather than
  discovered at deploy time.
- Theme, tokens and components are shared through `packages/ui` and `packages/shared`, so the API's
  contract and the UI's types are one artefact (`docs/ADRs` 019 for tokens).

**Evidence in repo.** `apps/web/src/app/` · `apps/web/playwright.config.ts` · `docs/DECISIONS.md`
ADR-002 · `docs/DEPLOYMENT.md` §2.

### Q7 — Why React Flow?

**Short answer.** The evidence graph is an interactive canvas where clicking a node is the primary
action, and React Flow provides the viewport, zoom and pan without me writing an interaction layer.
The alternative — a static SVG — would have meant re-implementing pan and hit-testing, which is exactly
where the interesting bug turned out to live.

**Deep dive.**

- Two defects came out of using it, both recorded: cards needed xyflow's `nopan` class or a press
  started the pane's d3-zoom gesture, and nodes had to declare `measured` because the memo hands
  xyflow fresh objects on every render, during which it renders them hidden and hit-testing fails.
  Both fixes are documented in the component, and the coordinate-based click workaround was deleted.
- Accessibility is not an afterthought: the same data is available as a keyboard-operable node index
  (`node-index-row`), and the a11y gate asserts the two views are equivalent.
- dnd-kit was chosen for the application board for the same reason — keyboard coordinates need an
  explicit implementation, which is now a tested pure function.

**Evidence in repo.** `apps/web/src/components/graph/graph-canvas.tsx` (the `nopan` and `measured`
notes) · `apps/web/e2e/a11y.spec.ts` · `apps/web/e2e/helpers/axe.ts` · `docs/DECISIONS.md` ADR-018 ·
`docs/ROADMAP.md` PHASE 14 finding on the graph click.

### Q8 — How do you keep the UI honest about data it does not have?

**Short answer.** Three distinct renderings, not two: a number when the API reported one, `—` when the
API explicitly did not carry the field, and an explanation naming the endpoint that would. `0` is
reserved for a measured zero, so the page can never turn "not reported" into "none".

**Deep dive.**

- The client guards accept `null` (they used to require a number, which made a whole panel fail to
  mount), and consumers distinguish "not carried" from "zero" — see `isNullableNumber` in
  `apps/web/src/lib/jobs-api.ts`.
- An empty account gets a real empty state that says where material comes from, not a disabled button
  pretending a feature exists.
- The dashboard guard test fails on any `PHASE \d` or 「尚未接入」 string a reader can see, because
  internal phase vocabulary and "not wired yet" captions had leaked onto a shipped page.

**Evidence in repo.** `apps/web/src/components/dashboard/dashboard-view.test.tsx` (the vocabulary
guard) · `apps/web/src/components/dashboard/profile-strength-ring.tsx` · `apps/web/src/lib/jobs-api.ts`
· `docs/ROADMAP.md` PHASE 14.

### Q9 — What did the responsive and accessibility gates actually catch?

**Short answer.** Two classes of defect that no unit test can see: at 375px the AI Runs table pushed
the columns the page exists for off-screen, and the mobile drawer sat **below** its own backdrop so
every tap was swallowed. Both were found by looking at a real browser, and both are now gates rather
than reports.

**Deep dive.**

- The drawer defect was a z-index inversion (`--z-drawer` 50 under `--z-modal` 60); jsdom has no
  stacking context, so a DOM test could not see it.
- The mobile project used to be inert unless `E2E_MOBILE=1` was set — a guard that has to be
  remembered is not a guard, so both projects now run by default (desktop 27 flows + mobile 18).
- The accessibility gate is axe on five pages × two viewports: `critical` and `serious` fail the
  build, `moderate` and `minor` are annotations, because a gate that fires on a heading-order nit gets
  switched off.

**Evidence in repo.** `apps/web/e2e/overflow.spec.ts` · `apps/web/e2e/navigation-drawer.spec.ts` ·
`apps/web/e2e/a11y.spec.ts` · `apps/web/playwright.config.ts` · `reports/release-readiness.md`
(0 critical, 0 serious).

---

## Backend

### Q10 — Why FastAPI?

**Short answer.** One schema definition constrains both the HTTP contract and the model's structured
output, which is the property this product needs most: the same Pydantic model that documents a
response validates what the LLM is allowed to return. Async fits the workload, and the dependency
system keeps ownership checks in one place.

**Deep dive.**

- Structured calls are bounded by a schema (`StructuredJD`, etc.), so a malformed model reply is a
  validation failure rather than a fabricated answer.
- Ownership is a dependency (`_load_own`-style helpers) rather than something each handler remembers.
- The AI core does not import FastAPI or SQLAlchemy at all — enforced by a script, not by convention
  — so the logic is testable without a server and a database (ADR-022).

**Evidence in repo.** `apps/api/src/careerforge_api/routers/` · `scripts/check_layering.py` ·
`docs/DECISIONS.md` ADR-003 and ADR-022 · `docs/ARCHITECTURE.md`.

### Q11 — What does the response envelope guarantee?

**Short answer.** Every JSON body is the same four keys — `{success, data, error, requestId}` — so a
client never has to guess which shape it received. Success carries `error: null`, failure carries
`data: null`, and the `requestId` in the body matches the header and the log line.

**Deep dive.**

- The envelope is written by middleware outside the error handlers, so a `401`, a `429` and a `500`
  are all documented envelopes rather than framework defaults.
- `requestId` is validated before it reaches a response header or a log line, because it is an
  attacker-controlled string otherwise (header injection and unbounded length).
- The rate limiter sits outside the envelope writer and builds its own envelope with the same helpers,
  which is why a throttled response still carries `Retry-After` and the documented body.

**Evidence in repo.** `apps/api/src/careerforge_api/middleware/envelope.py` ·
`middleware/request_id.py` · `middleware/ratelimit.py` · `apps/api/tests/test_docs_contract.py`.

### Q12 — Why must `null` never become `0`?

**Short answer.** Because they are two different statements: "the vendor did not report token usage"
and "this run used no tokens" lead to opposite decisions about a bill. The API types them differently,
the database stores `NULL`, and the UI prints `—` or "unavailable" — never a zero it did not measure.

**Deep dive.**

- `usage_status` (`reported` / `estimated` / `cached` / `unavailable` / `legacy`) travels with the
  counts, so a consumer can tell which kind of number it holds; the heuristic provider declares
  `unavailable` because it computes locally and spends nothing.
- `SUM` skips nulls, so a cost total over mixed runs is labelled a floor rather than presented as
  exact.
- The same rule fixed a user-visible lie: `GET /jobs/{id}/match` used to return the model's `0.0`
  defaults for fields it cannot report, so a stored match printed a measured-looking zero for a
  coverage the live endpoint reported as complete — and the client had no way to tell which was real.

**Evidence in repo.** `packages/shared/src/api/types-observability.ts` (`UsageStatus`) ·
`apps/api/alembic/versions/0009_usage_observability.py` · `apps/api/src/careerforge_api/routers/jobs.py`
(`get_match` docstring) · `docs/ROADMAP.md` PHASE 13.

### Q13 — How do you design rate limiting?

**Short answer.** Token buckets per identity, with a documented budget per endpoint group (auth,
reads, writes, AI, uploads) rather than one global limit. The AI budget is the strictest, and the
limiter sits outside auth, so it decodes the JWT signature itself and never touches the database.

**Deep dive.**

- The AI group counts only requests that can **spend** model tokens (`POST`/`PUT`/`PATCH` on an AI
  path). It used to match by path alone, which charged `GET /jobs/{id}/match` and
  `GET /ai/interview/{id}` to that budget — measured during a release run: 33 requests to AI-marked
  paths in sixty seconds against a bucket of 20, ten of them reads, and the user's real analysis got a
  `429`.
- Budgets are settings, not literals, because a test suite or a self-hosting operator has to be able
  to raise them — and the reporting site had to be fixed too: starting the stack with
  `RATE_LIMIT_UPLOAD_PER_HOUR` set left `/system/info` still printing the hard-coded default while the
  limiter enforced the configured value.
- The limiter is in-process in this build; `/system/health` says `queue=inprocess`, and with several
  replicas each enforces its own budget. That limitation is stated rather than implied away.

**Evidence in repo.** `apps/api/src/careerforge_api/middleware/ratelimit.py` ·
`packages/ai/careerforge_ai/config.py` (the five budgets) · `apps/api/tests/test_rate_limit.py` ·
`docs/API.md` §1.7 · `docs/ROADMAP.md` PHASE 14 findings 1–3.

---

## Database

### Q14 — Why PostgreSQL?

**Short answer.** Relational rows, full-text search and vectors in one transaction, which is what makes
the ownership checks and the retrieval consistent with each other. SQLite stays a first-class degraded
path so the product runs with no services, and the migrations are dialect-aware so both produce the
same schema.

**Deep dive.**

- The zero-dependency path is not a stub: `create_all` builds the schema on SQLite, and the release
  proof exercises a fresh database, migrations, seeding and a restart.
- The PostgreSQL path is exercised in CI against a pgvector-enabled PostgreSQL service container; it
  has never run on this
  development machine, which has no PostgreSQL — stated in `docs/DEPLOYMENT.md` §0.
- Dialect differences are handled behind a named layer rather than `if backend ==` scattered through
  services (`db/compat.py`).

**Evidence in repo.** `docs/DECISIONS.md` ADR-004 · `apps/api/alembic/` · `.github/workflows/ci.yml`
(`api-postgres`) · `reports/release-proof.json` steps 2–3 and its `notRun` entry for PostgreSQL.

### Q15 — Why pgvector?

**Short answer.** Because the vector arm has to live in the same database as the evidence rows it
points at, or every retrieval becomes a two-store consistency problem. The compose file runs a
pgvector-enabled PostgreSQL server — but the durable index is **not implemented** in this build, so
retrieval currently runs on an in-process hybrid index and health says so.

**Deep dive.**

- What exists: the vector port, the in-memory exact-search store, and the RRF fusion over two arms.
  What does not: an `embeddings` table and an ANN index — no migration declares a vector column.
- The consequence is honest and visible: `/system/health` reports `vector: degraded`, the release
  proof lists "Durable vector index" under `NOT RUN`, and readiness stays `ready` because that is the
  documented behaviour, not a pass.
- Measurements from the retrieval suite describe the in-process index: Hit@5 0.9661, MRR 0.9011 over
  59 queries.

**Evidence in repo.** `packages/ai/careerforge_ai/rag/store.py` ·
`apps/api/src/careerforge_api/services/system_service.py` (`reason="in_memory_index"`) ·
`docker-compose.yml` · `reports/release-proof.json` `notRun`.

### Q16 — Why Redis?

**Short answer.** For two jobs that must not live in one process: the queue that carries uploads to the
worker, and a rate limiter that several API replicas can share. Neither is implemented in this build —
the queue is in-process and reports that — so Redis is a chosen dependency with a stated gap, not a
claim.

**Deep dive.**

- The queue port exists with an in-process implementation; `QUEUE_BACKEND=redis` with no implementation
  in the process falls back and reports the downgrade on `/system/health` rather than failing or
  hiding it (the unsupported **storage** backend is the one refused outright).
- Uploads are spooled to a file between the request and the worker precisely because a job payload
  cannot carry bytes and the API and worker may be separate processes.
- The compose topology declares a Redis service with a `redis-cli ping` healthcheck, and the worker
  waits on it.

**Evidence in repo.** `docs/DECISIONS.md` ADR-010 · `docker-compose.yml` · `docs/DEPLOYMENT.md` §1 and
§5 · `reports/release-proof.json` `notRun` entry for the Redis backend.

### Q17 — How are migrations managed, and what do they enforce?

**Short answer.** Alembic, nine migrations (`0001`–`0009`), applied as a separate step — the compose
`migrate` service or a platform pre-deploy hook, never at application boot on PostgreSQL. No migration
in the range drops a table or a column in its `upgrade()`, so a rollback can run the previous image
against the newer schema.

**Deep dive.**

- The zero-dependency SQLite path uses `create_all` instead, because it has no migration step by
  design; both are meant to produce the same schema, and `db/compat.py` is where that promise lives.
- Additive-only is a deliberate operational property: it is what makes §4 of `docs/DEPLOYMENT.md`
  honest about rollback.
- The release proof deletes the SQLite file and migrates from empty: revision `0009`, 28 tables, and a
  restart that neither migrates nor re-seeds.

**Evidence in repo.** `apps/api/alembic/versions/` · `apps/api/src/careerforge_api/db/session.py` ·
`docker-compose.yml` (`migrate`, gated with `service_completed_successfully`) ·
`reports/release-proof.json` steps 2 and 7.

### Q18 — What does the database enforce that application code could forget?

**Short answer.** The rules that must not depend on a code path: the confidence formula is mirrored as
a CHECK constraint, ranges are bounded, and status columns are constrained by a vocabulary. A future
code path that computes a score the formula does not produce cannot write it.

**Deep dive.**

- `ck_evidence_confidence_formula` recomputes the five-factor sum inside the database and rejects a row
  that disagrees (ADR-013) — the weights live in one importable module that both the engine and the
  constraint documentation point at.
- Nullable count columns plus `usage_status` are a schema-level statement of the `null`-vs-`0` rule:
  the database stores "not reported" as `NULL`.
- Enumerated vocabularies are `text + CHECK` rather than native enums (ADR-011), because adding a value
  to a native enum is a migration hazard on PostgreSQL and impossible on SQLite.

**Evidence in repo.** `apps/api/src/careerforge_api/models/` · `packages/ai/careerforge_ai/scoring/weights.py`
(`CONFIDENCE_WEIGHTS`) · `docs/DECISIONS.md` ADR-011 and ADR-013 · `docs/DATABASE.md`.

---

## RAG

### Q19 — How do you chunk documents?

**Short answer.** Heading-aware recursive chunking: the heading path is preserved on every fragment
instead of discarded, and there is an overlap so a claim split across a boundary does not lose its
context. Sizes are per source kind, because a code snippet has different useful granularity from
prose.

**Deep dive.**

- Sizes are per source kind with a configured overlap for prose and none for code-like kinds, plus a
  minimum below which a fragment is dropped — a code snippet and a paragraph do not have the same
  useful granularity.
- Keeping the heading path is what lets a retrieved fragment say where it came from, which is the
  difference between a citation and a string.
- Chinese documents are handled explicitly: headings are also detected by the `：`/`:` line form, not
  only by Markdown `#`.

**Evidence in repo.** `packages/ai/careerforge_ai/rag/chunking.py` (`_HEADING_RE`,
`_CHINESE_HEADING_RE`, `ChunkingConfig`) · `docs/ROADMAP.md` PHASE 3a.

### Q20 — What is Hit@K?

**Short answer.** The share of queries where at least one relevant document appears in the top K
results. It is a recall measure at a fixed cut-off: Hit@1 says "the first result is relevant", Hit@5
says "a relevant result is somewhere in the first five".

**Deep dive.**

- Measured on 59 queries, three arms: Hit@1 0.8475, Hit@3 0.9661, Hit@5 0.9661 — the gate is Hit@5
  ≥ 0.93 and it passes.
- The step from Hit@1 to Hit@3 is the interesting one: it says the right document is usually retrieved
  but not always ranked first, which is why re-ranking beats expanding the candidate set here.
- The dense arm alone is Hit@5 0.8983 and the lexical arm alone is 0.9831 — see Q22 for what that
  means.

**Evidence in repo.** `evals/suites/rag_retrieval.py` · `evals/metrics.py` (`hit_at_k`) · measured in
`reports/eval-report.json` (`rag_retrieval`, 59 cases, `rag1.0`).

### Q21 — What is MRR?

**Short answer.** Mean Reciprocal Rank: for each query, one over the rank of the first relevant result,
averaged over queries. It rewards putting the right document _first_, where Hit@K only cares that it
appeared at all.

**Deep dive.**

- Measured 0.9011, gate ≥ 0.85. Read against Hit@1 0.8475, the gap is the partial credit for relevant
  documents found at rank 2 or 3.
- MRR and Hit@K are reported together on purpose: optimising Hit@5 alone is satisfied by a system that
  buries the best source at position five, which for a citation-driven product is nearly useless.
- Both are computed by hand-checked functions in `evals/metrics.py`, with unit tests using textbook
  values rather than snapshots of the implementation's own output.

**Evidence in repo.** `evals/metrics.py` (`mean_reciprocal_rank`) · `evals/tests/test_metrics.py` ·
measured in `reports/eval-report.json` (`retrieval.mrr` 0.901130).

### Q22 — Why does hybrid retrieval lose to BM25?

**Short answer.** On this corpus the keyword arm alone reaches Hit@5 0.9831 while the hybrid reaches
0.9661 — equal RRF weights lose one query that lexical search finds. I did not tune the weights,
because choosing them to win on 59 queries is fitting the corpus, and the honest report is worth more
than the extra point.

**Deep dive.**

- The cause is specific and worth saying: technical identifiers (`STM32F407`, `vTaskDelayUntil`) are
  exactly what lexical search is good at, and the dense arm's embedding of a short identifier is close
  to noise, so it can outrank a correct lexical hit in the fused list.
- The suites are versioned (`rag1.0`) and the baseline is committed, so this comparison can be
  re-run and argued with rather than re-litigated from memory.
- The spoken version is `docs/INTERVIEW.md` Q12; the numbers above are the ones in the current report.

**Evidence in repo.** `packages/ai/careerforge_ai/rag/fusion.py` · `rag/lexical.py` ·
`reports/eval-report.json` (`retrieval.keyword_hit_at_5` 0.983051 vs `retrieval.hit_at_5` 0.966102) ·
`reports/release-readiness.md` §3.

---

## LLM

### Q23 — How do you prevent hallucination?

**Short answer.** You cannot prevent it in the model, so the product is built so the model cannot do
much damage: it never produces a number, it never sets a status, and its verdict is one input to a
decision that rules and arithmetic make. Unsupported claims are refused rather than reworded.

**Deep dive.**

- Layer order: deterministic blockers → retrieval → model verdict → arithmetic. A quantified claim
  with no quantitative evidence never reaches the model at all.
- The residual is measured, not hoped for: `unsafe_support_rate` 0.0500 means 2 of the 40
  non-supported cases were accepted, both named (`ev-0036` 「用 C++ 重写了通信中间件，吞吐提升明显」 at
  confidence 0.91, and `ev-0039` 「完成两轮自平衡机器人的整机调试」 at 0.89).
- Fabricated-number acceptance is gated at exactly zero and measured at 0.0000 — no claim carrying an
  unverifiable quantity has ever been marked supported.

**Evidence in repo.** `packages/ai/careerforge_ai/agents/validator_decide.py` ·
`parsing/claim_rules.py` · `reports/eval-report.json` (`evidence.unsafe_support_rate`,
`evidence.unsafe_numeric_support_rate`, and the `failures` list) · `docs/INTERVIEW.md` Q7.

### Q24 — How do you handle provider timeouts?

**Short answer.** Retry with backoff, then degrade rather than fail: a transient upstream failure
produces a 200 with a run marked degraded and the reason stated, because a 500 for a user whose
résumé still has a verifiable answer is the wrong outcome. Self-declared outages are passed through
rather than flattened into a generic error.

**Deep dive.**

- The provider chain is decorated: cached, routed, resilient; the chain always ends at the heuristic
  provider, so an outage means a worse answer, not no answer.
- Failure injection drives real endpoints with a scripted provider that can time out, hang, `429`,
  return the wrong shape, crash or exhaust a budget — and every one of those writes an `agent_runs`
  row whose status says what happened.
- The tests were proved to have teeth by breaking the code they protect: replacing `resilience.py`'s
  degrade path with a re-raise took the suite from `16 passed` to `7 failed, 21 passed`, then back to
  green.

**Evidence in repo.** `packages/ai/careerforge_ai/providers/resilience.py` ·
`apps/api/tests/test_failure_injection.py` · `apps/api/tests/failure_support.py` (`ScriptedProvider`) ·
`docs/QUALITY.md` §6.

### Q25 — How do you handle malformed JSON?

**Short answer.** A malformed structured output is a validation failure, never an answer: the call is
bounded by a schema, and a reply that does not satisfy it is rejected and surfaces as a degraded or
failed step. The one thing that must never happen is a partly-parsed object becoming a verdict.

**Deep dive.**

- The prompt registry declares the variables a template may use and fails on a missing one instead of
  rendering an empty prompt — the same "silent empty string" failure mode one layer up.
- Providers that emit JSON in prose are handled by the provider adapter, not by the agent, so the
  repair logic is in one place and the agent only sees a validated model.
- Injection covers it: "emit malformed JSON" is one of the scripted failures, and the asserted property
  is about the user (no fabricated answer, a run row that says what happened), not about the exception
  type.

**Evidence in repo.** `packages/ai/careerforge_ai/prompting/registry.py` ·
`providers/` adapters · `apps/api/tests/test_failure_injection.py` · `docs/QUALITY.md` §6.

### Q26 — Why does the provider chain always end at the heuristic provider?

**Short answer.** So the product has no configuration in which it stops working. Key present or not,
provider up or down, the chain terminates at a deterministic rule engine that computes locally — which
is why every test, evaluation and end-to-end flow in this repository runs with no API key and no cost.

**Deep dive.**

- It is a first-class deployment, not a mock: it is what the release proof runs
  (`LLM_PROVIDER=heuristic`), and it declares `usage_status: unavailable` because it spends nothing —
  rather than reporting `0` tokens it did not measure.
- Degradation is visible rather than silent: the response carries `degraded`, the run records which
  provider answered, and `/system/health` reports `llm_provider` as degraded.
- Cost follows: the default deployment path cannot produce a bill, so CI can run the whole evaluation
  suite on every commit.

**Evidence in repo.** `docs/DECISIONS.md` ADR-009 · `packages/ai/careerforge_ai/providers/` ·
`reports/release-proof.json` step 4 (`degraded=['llm_provider', 'vector']`) · `docs/QUALITY.md` §8.

---

## Agent

### Q27 — Why a custom orchestrator rather than LangGraph?

**Short answer.** Because the execution graph is small, fixed and the thing I most need to reason
about: nine agents, explicit steps, and a run record I can read afterwards. A framework would add
indirection exactly where observability matters, and the orchestration code is a few hundred lines of
straight-line async.

**Deep dive.**

- Every run records steps in order with provider, latency, prompt version and usage, so "what happened
  in this request" is a database query rather than a framework's internal state.
- The budget guard, the cache and the degradation flags are decorators around the provider port, not
  framework hooks — which is why they work identically for `chat`, `stream` and `structured_output`.
- The same choice applies to prompts: they live as versioned Markdown files outside the code (ADR-012),
  so prose review and code review are separate activities.

**Evidence in repo.** `packages/ai/careerforge_ai/orchestrator/` · `observability/tracker.py` ·
`prompts/` · `docs/DECISIONS.md` ADR-007 and ADR-012 · `docs/ARCHITECTURE.md`.

### Q28 — How do you handle a failed run?

**Short answer.** A failed request leaves a trace, written outside the request's transaction. The
tracker used to write inside it, so any 400 or 500 rolled the row back and the failure vanished —
which contradicted the executor's own comment that observability is never lost. A failure journal held
by middleware fixed it.

**Deep dive.**

- The journal is flushed by the **outermost** middleware with its own short-lived session after the
  request transaction has settled; SAVEPOINT and a second session inside the transaction were both
  rejected and the reasons are written down in the module.
- Rows carry `status = failed` and pass through a sanitiser first: keys, tokens and whole documents
  never appear in a row.
- This is the kind of defect that only shows up when you go looking: the same run was recorded
  perfectly on success and not at all on failure.

**Evidence in repo.** `apps/api/src/careerforge_api/services/failure_journal.py` ·
`apps/api/tests/test_failed_run_trace.py` · `docs/QUALITY.md` §7 · `docs/ROADMAP.md` PHASE 13.

### Q29 — How is the interview planned and scored?

**Short answer.** The plan comes from the target posting's requirements and the candidate's evidence,
not from a generic question bank: topics are selected to cover the required skills and to probe the
gaps. Scoring aggregates per-turn evaluations into a seven-dimension scorecard.

**Deep dive.**

- The seven dimensions are 技术准确性, 表达沟通, 技术深度, 问题解决, 工程思维, 自信度 and
  证据一致性; the difficulty ladder is a pure function, so its boundaries are unit-tested.
- Difficulty adapts per answer, which is why the _agreement_ between requested and declared difficulty
  is measured as 1.0000 rather than assumed.
- The suite is small and honest about it: 3 cases (`iv1.0`), with required-skill coverage 0.8333
  (gate ≥ 0.75), duplicate questions 0.0000, cross-role leakage 0.0000, and evidence awareness 0.6000.
  Three cases prove the shape works, not that the planner is good.

**Evidence in repo.** `packages/ai/careerforge_ai/agents/interview/plan.py` ·
`agents/interview/scorecard.py` (`_SCORE_DIMENSIONS`) · `evals/suites/interview_relevance.py` ·
`reports/eval-report.json` (`interview_relevance`).

---

## Evaluation

### Q30 — Why is accuracy not enough?

**Short answer.** Because the two error directions are not equally bad here, and accuracy averages
them away. Measured on the 60-case claim set, accuracy is 0.9000 — and the matrix behind it matters
more than the scalar: 19 of 20 supported claims confirmed, 29 of 31 unsupported rejected, 2 over-calls.

**Deep dive.**

- The over-calls are what `unsafe_support_rate` exists to name, and they get a stricter gate than any
  other metric in the project.
- The under-call direction is documented as deliberate: refusing to confirm an honest bullet costs a
  review, while accepting an invented one puts fiction on a CV in the candidate's voice.
- Class imbalance is why `macro_f1` (0.8481, gate ≥ 0.78) is the gated metric and accuracy is
  report-only. Spoken version: `docs/INTERVIEW.md` Q5.

**Evidence in repo.** `reports/eval-report.json` (`evidence.accuracy` 0.900000 report-only;
`evidence.macro_f1` 0.848105 gate; `breakdown.confusion` for the cells above) ·
`evals/config.py` (the rationales) · `docs/INTERVIEW.md` Q5.

### Q31 — What are precision / recall / F1?

**Short answer.** Precision is the share of what the system flagged that was right; recall is the share
of what should have been flagged that it found; F1 is their harmonic mean, so a system cannot trade one
away for the other without the score noticing. In this product they are computed per class and then
averaged, because "unsupported" and "supported" are both things the gate must get right.

**Deep dive.**

- Worked example from the claim suite: supported precision 0.904762, supported recall 0.9500,
  supported F1 0.926829 — one honest claim under-called, and none of the 19 correct ones lost.
- JD extraction is the opposite trade and it is visible: required-skill recall 1.0000 with precision
  0.790816, i.e. the extractor over-reports rather than misses, which is the safe direction when the
  requirement list drives everything downstream.
- The functions are implemented once (`prf`) and unit-tested against hand-computed values, so a metric
  definition cannot drift between suites.

**Evidence in repo.** `evals/metrics.py` (`prf`, `classification_report`) ·
`evals/tests/test_metrics.py` · `reports/eval-report.json` (`evidence.supported_precision`,
`evidence.supported_recall`, `jd.required_skill_recall`, `jd.required_skill_precision`).

### Q32 — Why macro F1?

**Short answer.** Because the classes are imbalanced — many more unsupported claims than partially
supported ones — so a micro-averaged or accuracy-based number would be dominated by the easy class.
Macro F1 averages the per-class F1 equally, which makes the rare class as expensive to get wrong as the
common one.

**Deep dive.**

- Measured: macro F1 0.848105 against 0.78 as a gate, with the rationale recorded next to the threshold
  rather than in someone's head.
- Reading it with accuracy is informative: 0.9000 accuracy against 0.8481 macro F1 is the gap between
  "mostly right" and "right on the hard class too".
- The confusion matrix is in the artefact, so the number can be taken apart: 2 unsupported cases became
  `partially_supported` and 2 partially-supported ones became `supported` (the unsafe pair).

**Evidence in repo.** `reports/eval-report.json` (`evidence.macro_f1`, `breakdown.confusion`) ·
`evals/config.py` (`evidence.macro_f1` rationale) · `evals/metrics.py`.

### Q33 — What is the unsafe support rate?

**Short answer.** The share of claims that are not fully supported by evidence but are marked
`supported` anyway — the one error this product exists to prevent. It is measured at 0.0500: 2 of the
40 non-supported cases, and both are named rather than absorbed into a percentage.

**Deep dive.**

- The two cases are `ev-0036` 「用 C++ 重写了通信中间件，吞吐提升明显」 (confidence 0.91) and `ev-0039`
  「完成两轮自平衡机器人的整机调试」 (0.89). Both are _scope_ problems: the rewrite and the control
  tuning are evidenced, while 「明显」 and 「整机」 are not — and no keyword rule can settle that.
- The gate is 0.075 while the project's target is 0.02, and the target is **not met**. Widening the
  gate to hide that would convert a real gap into a green check, which is why it stays published on
  the system page.
- The paired metric is fabricated-number acceptance, gated at exactly 0 and measured at 0.0000 — the
  stricter gate is on the error with no interpretive excuse.

**Evidence in repo.** `evals/config.py` (`evidence.unsafe_support_rate` rationale) ·
`reports/eval-report.json` (`evidence.unsafe_support_rate` 0.050000, `failures` for the two case ids) ·
`docs/QUALITY.md` §7 · `docs/INTERVIEW.md` Q13.

### Q34 — What is calibration?

**Short answer.** Whether the confidence number means what it says: of the claims the gate marked at
0.8, roughly 80% should actually be supported. It is a property of the whole distribution, measured by
bucketing predictions and comparing mean confidence with observed accuracy.

**Deep dive.**

- Measured over 10 buckets: ECE 0.031555, Brier 0.090405, mean confidence 0.899888 against accuracy
  0.9000.
- The buckets disagree in an informative way: 0.8–0.9 holds 45 cases and runs 0.021 _under_-confident,
  while 0.9–1.0 holds 15 cases and runs 0.063 _over_-confident — the region the gate actually operates
  in.
- Buckets with no cases are excluded rather than counted as perfectly calibrated; ECE is
  sample-weighted so an empty bucket cannot flatter it.

**Evidence in repo.** `reports/confidence-calibration.json` · `reports/confidence-calibration.md` ·
`evals/metrics.py` (`reliability_buckets`, `expected_calibration_error`) · `docs/QUALITY.md` §3 ·
`docs/INTERVIEW.md` Q4.

### Q35 — What is ECE?

**Short answer.** Expected Calibration Error: the case-weighted mean absolute gap between confidence
and accuracy across buckets. 0.03 means the gate's confidence is, on average, three points away from
the truth — small, and small in a direction worth knowing.

**Deep dive.**

- Measured 0.031555 over 60 cases in 10 bins, with `confidence == 1.0` falling in the last bucket
  rather than outside every bucket (a real edge case, unit-tested).
- It was **published but not comparable** until late in the project: ECE and Brier were written to a
  side artefact and never entered the report's metric set, while `evals/compare.py` carried explicit
  lower-is-better rules for both names. A calibration change could not appear in a diff or fail a
  gate.
- Now emitted as `evidence.ece` and `evidence.brier` with report-only thresholds, because at 60 cases
  a calibration figure moves on one reclassified example.

**Evidence in repo.** `evals/report.py` (`calibration_metrics`) · `evals/config.py` (`evidence.ece`,
`evidence.brier`) · `evals/tests/test_calibration_metrics.py` ·
`reports/eval-report.json` (`evidence.ece` 0.031555, `evidence.brier` 0.090405).

### Q36 — Why is confidence not the probability of truth?

**Short answer.** Because it is a weighted function of five observable factors — authority, recency,
specificity, corroboration and extraction quality — not a posterior over a hypothesis. It is a
_measurement of the evidence_, and calibration is the check that it behaves like a probability in
practice.

**Deep dive.**

- The formula is public, versioned (`confidence@1.0.0`) and mirrored as a database CHECK constraint, so
  it cannot silently change under stored rows.
- That is also why the numbers stay stable and explainable: the same evidence always yields the same
  confidence, which is what allows a claim's status to be argued about with a rule rather than a
  feeling.
- The honest caveat: calibration currently describes the zero-key path. A different provider changes
  the model's verdicts and therefore the distribution, and re-running it needs a key.

**Evidence in repo.** `packages/ai/careerforge_ai/scoring/confidence.py` ·
`scoring/weights.py` (`CONFIDENCE_WEIGHTS`, `CONFIDENCE_FORMULA`) · `docs/DECISIONS.md` ADR-013 ·
`docs/QUALITY.md` §7 item 6 · `docs/INTERVIEW.md` Q3.

### Q37 — What is a gate versus a report threshold?

**Short answer.** A gate that is missed fails the process; a report threshold that is missed is printed
and the run still succeeds. Every threshold carries its severity and its rationale in one file, so a
quality metric the project has not earned stays a report instead of being quietly lowered until it
passes.

**Deep dive.**

- Current state: 4 suites, 242 cases, 41 metrics, gates 4 passed / 0 failed / 0 reported misses, in
  839 ms — all on the deterministic provider, so it runs in CI for free.
- The split is deliberate and load-bearing: `evidence.unsafe_support_rate` is a gate because it is the
  product's core promise, while `jd.required_skill_precision` (0.790816) is report-only because
  tightening it would hide the known over-extraction weakness rather than fix it.
- Exit codes are meaningful: `2` means a gate was missed, `1` means infrastructure failure, `0` means
  every executed suite passed — CI can fail on the right thing.

**Evidence in repo.** `evals/config.py` (`Severity`, `SUITE_THRESHOLDS`) · `evals/run.py` (exit codes) ·
`reports/eval-report.json` (`summary`) · `docs/QUALITY.md` §4.

### Q38 — Why was an entire benchmark thrown away?

**Short answer.** Because it was measuring itself. The old claim corpus reported `support_recall
1.0000` and `over_support_rate 0.0000` — both true and both worthless: it held 22 distinct
claim/kind pairs across 120 rows, one claim repeated twelve times, and its labels tracked the rule
layer's own logic.

**Deep dive.**

- The replacement is 60 distinct hand-authored cases with 100 evidence fragments across nine evidence
  kinds — and the first honest run reported `support_recall 0.0000`, a number about a configuration
  no deployment uses.
- Investigating that zero found two real defects: evidence documents were created with the schema
  default `confidence=0.0`, so the gate's confidence was zero for every case; and a model-reported
  blocker was softened by the mere presence of retrieval hits — 13 of 20 fabricated claims were
  affected.
- Lesson worth stating out loud: a green benchmark is evidence about the benchmark until you have
  tried to make it fail.

**Evidence in repo.** `docs/QUALITY.md` §2 (the old corpus, the replacement, the `0.0000` first run) ·
`evals/suites/evidence_validation.py` · `evals/datasets/` · `docs/ROADMAP.md` PHASE 12 findings 4 and 7.

---

## Observability

### Q39 — How do you compute cost?

**Short answer.** Per call, from the usage the provider reports and a versioned price table — never
from a guess. Each `llm_calls` row keeps tokens, USD and CNY, provider, model and a `usage_status`, and
a run aggregates its calls; where a vendor reports nothing the counts are `NULL` and the total is
labelled a floor.

**Deep dive.**

- The table is `pricing@1.0.0` with a configurable currency conversion rather than a rate baked into
  code, because a fixed conversion silently rots.
- Three call shapes report the same envelope — `chat`, `stream` and `structured_output` — which was the
  fix for a real defect: the structured path used to record zero tokens for every agent that used it,
  so the cost page reported no spend at all, including on a paid deployment.
- Cache hits report `cached` with zero counts rather than re-billing the original call's tokens.

**Evidence in repo.** `packages/ai/careerforge_ai/observability/pricing.py` (`PRICE_TABLE_VERSION`,
`USD_TO_CNY`) · `apps/api/src/careerforge_api/services/metering.py` · `docs/INTERVIEW.md` Q15 ·
`docs/QUALITY.md` §7 item 1.

### Q40 — What is in a run trace?

**Short answer.** A run row with its status, latency, degraded flag and provider, plus ordered steps and
the model calls each step made — prompt version, tokens, cost, latency and outcome. It is written by the
executor, not by each agent, so a new agent gets observability without remembering to add it.

**Deep dive.**

- Failed runs are included by design: the failure journal writes them after the request transaction has
  rolled back, which is the only ordering that makes a 500 leave a trace.
- The page (`/app/ai-runs`) reads the same rows the API returns, with the step chain inline; there is no
  separate logging path to drift from the database.
- The reason this exists at all: a user asking "why did it answer that" is a product question here, not
  an ops question.

**Evidence in repo.** `packages/ai/careerforge_ai/observability/tracker.py` ·
`apps/api/src/careerforge_api/services/observability_service.py` ·
`apps/api/src/careerforge_api/routers/observability.py` · `docs/INTERVIEW.md` Q16.

### Q41 — What do the usage statuses mean?

**Short answer.** `reported` — the vendor told us; `estimated` — computed locally as an approximation;
`cached` — served from cache without a new call; `unavailable` — nobody reported, so the counts are
`NULL`; `legacy` — a row written before the envelope existed. The status travels with the numbers
because the numbers alone are ambiguous.

**Deep dive.**

- The heuristic provider declares `unavailable` and keeps its local count in a separate
  `estimated_input_tokens` field, so it can never be summed into a cost.
- `legacy` exists because rows written before the migration are neither reported nor unavailable —
  pretending otherwise would invent a provenance.
- The page prints "unavailable" and a note that totals are a floor, rather than a `0` that reads as a
  measurement.

**Evidence in repo.** `packages/shared/src/api/types-observability.ts` (`UsageStatus`) ·
`apps/api/alembic/versions/0009_usage_observability.py` · `docs/QUALITY.md` §7 item 1 ·
`apps/api/tests/test_cost_accounting.py`.

### Q42 — How does the UI show degradation instead of hiding it?

**Short answer.** Every AI surface carries the degradation state it was produced under: the run has a
`degraded` flag, the response has warnings, and the pages print them next to the number instead of
substituting a friendlier value. `/system` publishes the same facts for the whole deployment, including
the ones that are not passing.

**Deep dive.**

- The system page carries a quality snapshot generated from the evaluation artefacts, so the measured
  weaknesses are visible in the product rather than only in the repository.
- Health and readiness are separated: `/system/health` is liveness, `/system/ready` reports `degraded`
  components (`llm_provider`, `vector` on the zero-key path) without failing — a documented behaviour,
  not a pass.
- The dashboard states where its numbers come from and shows nothing when the endpoint is unavailable,
  rather than falling back to placeholders.

**Evidence in repo.** `apps/web/src/app/system/page.tsx` · `scripts/export_quality_snapshot.py` ·
`apps/api/src/careerforge_api/services/system_service.py` · `reports/release-proof.json` step 4.

---

## Testing

### Q43 — Unit vs integration vs E2E?

**Short answer.** Split by what each layer can _observe_, not by size: pure arithmetic in the AI core
(553 tests, 4 skipped), the contract as shipped in the API (400), rendering rules in components (365),
the measurement itself in `evals/tests` (22), and the browser (45 flows). The total is 1,385, and the
boundaries are what stop a defect from being tested nowhere.

**Deep dive.**

- The layering is not decoration: jsdom has no layout engine, Node's `fetch` does not enforce CORS, and a
  DOM test cannot see stacking order — each of those produced a defect that only one layer could catch.
- Component tests still carry real value: the "rendering rules" layer is where `null ≠ 0` is pinned, and
  where runtime guards catch a drifted payload.
- Spoken version: `docs/INTERVIEW.md` Q8.

**Evidence in repo.** `docs/QUALITY.md` §1 (the layer table with counts) ·
`packages/ai/tests/` · `apps/api/tests/` · `apps/web/src/**/*.test.tsx` · `evals/tests/` ·
`apps/web/e2e/`.

### Q44 — Why is E2E needed?

**Short answer.** Because the defects that matter most in this product are invisible to every layer
below it: whether the browser can actually read the API, whether a tap reaches a link, whether the table
the page exists for is on screen. Those are not logic bugs, so no logic test finds them.

**Deep dive.**

- The suite drives a real stack: real API, real database, real Chrome, real session installed the way
  the app stores it, and no route interception. Setup calls go through HTTP with the same bearer token.
- It is also where the release-blocking defects were found: the AI quota charged to page reads (33
  requests in 60 seconds against a bucket of 20, ten of them reads) and a shared fixture that made two
  gates depend on spec execution order.
- Spoken version: `docs/INTERVIEW.md` Q9 and Q18.

**Evidence in repo.** `apps/web/e2e/` · `apps/web/playwright.config.ts` ·
`apps/web/e2e/helpers/fixtures.ts` · `docs/ROADMAP.md` PHASE 14 findings 1 and 4.

### Q45 — How do you test CORS?

**Short answer.** From a page, in both directions: the allowed origin must be able to `fetch` the API
(including a preflighted authenticated request), and a non-allowed origin must **not** be granted —
with a wildcard explicitly refused, because "allow `*`" would pass the first assertion while breaking
the guarantee.

**Deep dive.**

- The spec derives the base URL from Playwright's `baseURL` rather than hard-coding a port; the earlier
  hard-coded `:3318` was a real defect that made the check silently vacuous on another port.
- Node's `fetch` does not enforce CORS, so an API-only smoke suite can be 25/25 green while every
  browser request is blocked — which is exactly what happened, and is why this test runs in a browser.
- The stack's own configuration is part of the fixture: the API has to name the origin the browser will
  use, which is why the E2E guide documents the start-up order.

**Evidence in repo.** `apps/web/e2e/cors.spec.ts` · `apps/web/e2e/README.md` ·
`docs/INTERVIEW.md` Q17 · `docs/ROADMAP.md` PHASE 13 finding 16.

### Q46 — Why does 92.5% coverage not prove there are no bugs?

**Short answer.** Because coverage says which lines ran, not which behaviours were checked — a line can
be executed by a test that asserts nothing. The number is scoped to the core domain on purpose (the
claim gate, scoring, retrieval, parsing, interview, accounting), and the areas with the lowest coverage
are the ones I would distrust first.

**Deep dive.**

- Measured: core domain 92.5% (1556/1683 statements); "everything measured" is 91.0% (17086/18778) and
  is reported beside it, never used as the target.
- The per-area spread is the useful part: claim gate & confidence 95.2%, matching 96.2%, retrieval
  91.2%, parsing 95.7%, interview 94.6%, AI accounting & observability 83.6% — and the lowest file is
  `observability_service.py` at 72.7%, which is a known soft spot rather than a surprise.
- The complement is the mutation check: breaking `resilience.py`'s degrade path took the failure suite
  from 16 passed to 7 failed, 21 passed — evidence the tests can fail, which coverage cannot give you.

**Evidence in repo.** `reports/coverage-summary.md` · `scripts/coverage_report.py` ·
`docs/QUALITY.md` §6 · `reports/release-readiness.md` §2.

### Q47 — Why is test count not quality?

**Short answer.** Because a count is a count. This repository had 1,025 tests while three UI defects
that a single screenshot exposed were invisible to all of them — the number went up when the missing
layer was added, but the number was never the reason the product got better.

**Deep dive.**

- What changed the outcome was choosing the layer by what it can observe: the browser suite (45 flows)
  and the accessibility/overflow gates found defects no unit test could model.
- The count did move as a side effect: 1,025 → 1,385 across the phases that added those layers, and the
  per-layer split is published so the shape of the suite is visible, not just its size.
- The honest framing for an interviewer: "the count is a lagging indicator; the useful question is
  which defect each layer exists to catch."

**Evidence in repo.** `docs/QUALITY.md` §1 · `reports/release-readiness.md` §2 ·
`docs/ROADMAP.md` PHASE 14 (the documentation audit that corrected these counts).

### Q48 — How do you keep a 45-flow browser suite independent?

**Short answer.** Setup is idempotent, expensive fixtures are per worker rather than per test, and the
suite is deliberately given its own rate-limit budgets — because a suite is not a user. Two failures
that looked like product bugs turned out to be test-environment defects, and both are now documented
where the stack is started.

**Deep dive.**

- Setup idempotency is a product property being reused: re-uploading the same résumé returns the same
  document, re-analysing the same posting updates the same job, publishing keeps the slug.
- The measured problems: one user driving 45 flows in ~90 s against a 20-per-minute AI budget, and a
  shared fixture that analysed a posting without matching it, so a gate waited for a panel whose stored
  row did not exist yet (`404 This job has not been matched yet`).
- The fix for the second was to make the fixture's contract honest — a matched posting depends on the
  evidence base, and it refuses to proceed on an empty account rather than scoring against nothing.

**Evidence in repo.** `apps/web/e2e/README.md` · `apps/web/e2e/helpers/fixtures.ts` ·
`.github/workflows/ci.yml` (the `e2e` job's declared budgets) · `docs/ROADMAP.md` PHASE 14 findings 3
and 4.

### Q49 — How do you verify that a test can actually fail?

**Short answer.** By breaking the code it protects and watching it go red before trusting it. That is
how the degradation suite was validated: replacing `resilience.py`'s degrade path with a re-raise took
it from 16 passed to 7 failed, 21 passed, and restoring the path turned it green again.

**Deep dive.**

- The same discipline caught a test that could never fail: an assertion in `test_system.py` compared the
  reported upload budget against the literal `20` while the service hard-coded that same `20`, so the
  line was decorative — and the drift it should have caught survived the change that made the budget
  configurable.
- Every fix in the release phase came with a test, and for two of them the test was verified by
  reverting the fix and watching the assertion fail (the AI-spend classification and the calibration
  wiring).
- The rule stated in the codebase: a test that cannot fail is worse than no test, because it looks like
  coverage.

**Evidence in repo.** `docs/QUALITY.md` §6 · `apps/api/tests/test_rate_limit.py` ·
`evals/tests/test_calibration_metrics.py` · `apps/api/tests/test_system.py` ·
`docs/ROADMAP.md` PHASE 14 finding 2.

---

## Deployment

### Q50 — How is Docker organised?

**Short answer.** Two multi-stage images — one API image that also runs the worker and the migration
step, one web image — and a compose file that brings up PostgreSQL with pgvector, Redis, a one-shot
migrate service, the API, the worker and the web app, with healthchecks between them.

**Deep dive.**

- The API image keeps `apps/api` as its working directory so a bare `alembic` resolves
  `alembic.ini`/`alembic/`; that is why the same image can be the API, the worker and the migration
  job.
- Ordering is enforced by compose: `migrate` must exit 0 before the API, worker or web start, so
  nothing serves against an unmigrated database.
- No secrets are baked in: `JWT_SECRET`, `DATABASE_URL` and API keys arrive at run time.
- **Honest status:** none of this has been executed. There is no container runtime on the development
  machine (probed and recorded), so the image path is unwitnessed; a CI job now builds both images and
  boots the API container against its own health check, and its first green run is what will witness it.

**Evidence in repo.** `infra/docker/Dockerfile.api` · `infra/docker/Dockerfile.web` ·
`docker-compose.yml` · `.github/workflows/ci.yml` (`images` job) · `reports/release-proof.json`
(`containerized: false`, `notRun`) · `docs/DEPLOYMENT.md` §0–§1.

### Q51 — How is CI designed?

**Short answer.** Separate jobs, each answering a different question: does the product work with no external
services, does it work against real PostgreSQL with pgvector, does the frontend typecheck/lint/build
and pass its tests, does the browser suite pass against a started stack, and do the images build and
boot.

**Deep dive.**

- The zero-dependency job is the one that proves the configuration most reviewers will run: SQLite,
  in-process queue, heuristic provider, no API key (ADR-004, ADR-009).
- The evaluation job runs `evals/run.py`, so a missed **gate** threshold fails the build while a
  report-only miss prints and passes — the severity split is what makes the gate credible.
- The browser job runs both Playwright projects and the accessibility gate as a named step, so
  "accessibility failed" is its own red line rather than a line in a log.
- Datasets are checked against their generator in CI, so a corpus cannot drift from the code that
  claims to produce it.

**Evidence in repo.** `.github/workflows/ci.yml` · `evals/run.py` (exit codes) ·
`docs/QUALITY.md` §8 · `reports/release-readiness.md` §2.

### Q52 — How do you deploy?

**Short answer.** Two paths and one refusal. Compose on a single host, or managed services: web on
Vercel, API and worker on Render or Railway, PostgreSQL with pgvector on Neon or Supabase, Redis on
Upstash. The refusal is that I will not claim a deployment I did not run — it is blocked here, and the
guide says so.

**Deep dive.**

- The environment matrix in `docs/DEPLOYMENT.md` §2 lists what happens when each variable is wrong:
  a placeholder `JWT_SECRET` refuses to start in production, a wrong `CORS_ORIGINS` blocks every browser
  call before the response is read, a missing provider key falls back to the heuristic chain and is
  reported as degraded.
- Migrations are a deploy step, not a boot step: the platform's pre-deploy hook runs `alembic upgrade
head`.
- Post-deploy proof is specified rather than implied: health, readiness, version, and the browser suite
  pointed at the deployed URL (`E2E_BASE_URL` / `E2E_API_URL`).

**Evidence in repo.** `docs/DEPLOYMENT.md` §2–§3 · `reports/release-readiness.md` §4 ·
`apps/web/e2e/helpers/api.ts` (`E2E_API_URL`).

### Q53 — What is blocked, and what would you run first on a machine with Docker?

**Short answer.** Deployment is blocked by the environment, not the code: no container runtime, no
PostgreSQL, no Redis, no cloud credentials, and no git remote. On a machine with Docker, the first
command is `docker compose build && docker compose up -d` followed by `curl /system/ready` — that single
step closes the only unwitnessed claim in the release.

**Deep dive.**

- The native path is proved instead, and it is not trivial: fresh database → `alembic upgrade head`
  (revision `0009`, 28 tables) → seed twice (161 rows across 9 tables; second run changed 0 tables) →
  production-mode API → built frontend (`next start`, not `next dev`) → 25 contract smoke checks →
  restart with no migration and no re-seed. Seven steps, 7/7, 48.7 s.
- The release proof keeps a `NOT RUN` table naming each step the machine cannot execute **and why**, so
  the artefact never implies more than it did.
- That is why `v1.0.0-rc.1` is tagged and `v1.0.0` is not: the image path has never been witnessed, and
  a release tag is a claim.

**Evidence in repo.** `reports/release-proof.json` (7/7, `notRun` table, environment) ·
`reports/release-readiness.md` §4 (the four commands) · `docs/DEPLOYMENT.md` §0.

---

## Security

### Q54 — How do you defend against prompt injection?

**Short answer.** Structurally, rather than by asking the model nicely. Untrusted text is rendered into
the user message, never into the system instructions; prompt templates are declared files with declared
variables, so a missing value fails instead of rendering empty; every model output is bounded by a
schema; and the model cannot set a status or a number, so the highest-value target — making a claim
"supported" — still has to pass the rule layer and the arithmetic.

**Deep dive.**

- Input is truncated before it reaches a prompt (`truncate_for_prompt`), so a document cannot consume the
  context with an instruction payload either.
- What injection cannot do here is the important part: it cannot invent a citation, because the sources
  are retrieved rows with locators, and it cannot move a confidence, because confidence is arithmetic
  over evidence facts.
- **Honest gap:** there is no dedicated adversarial prompt-injection corpus and no measured
  injection-resistance rate. I would build that before claiming this area is tested.

**Evidence in repo.** `packages/ai/careerforge_ai/prompting/registry.py` (`RenderedPrompt.system` /
`.user`, declared variables) · `agents/job.py` (`truncate_for_prompt`) ·
`docs/DECISIONS.md` ADR-014 · `docs/PORTFOLIO.md` §5.

### Q55 — How is multi-tenant isolation enforced?

**Short answer.** Every query is scoped by the authenticated user in the repository layer, and a
cross-tenant read returns `404`, not `403` — because telling a caller "this exists but is not yours"
leaks the existence of other people's rows. The limiter runs before auth and buckets by IP in that case
rather than trusting an unverified identity.

**Deep dive.**

- Ownership is a dependency the handler cannot forget to call, and the "not found" path is the same one
  used for a genuinely missing row, so the two cases are indistinguishable from outside.
- The failure-injection pass found two places where one account could read a row belonging to another —
  recorded in the service comments where they were fixed.
- Public sharing is a separate, explicit product: publishing creates a public profile row, and the
  public endpoints are the only ones serving another person's data.

**Evidence in repo.** `apps/api/src/careerforge_api/core/errors.py` (`ForbiddenError` docstring: cross-
tenant reads are not forbidden) · `apps/api/tests/test_dashboard.py` (scoped-to-caller test) ·
`apps/api/src/careerforge_api/services/observability_service.py` · `docs/API.md` §1.2.

### Q56 — How are secrets and tokens handled?

**Short answer.** Nothing secret is baked into an image or a repository: `.env.example` carries a
placeholder that is recognised by name, and the API **refuses to start** in production while the JWT
secret is still that placeholder. A short secret is a logged warning rather than a refusal, and the
length is stated in the deployment guide so the distinction is not hidden.

**Deep dive.**

- The secrets that must never leak into observability are also handled at the write path: rows written
  by the failure journal pass through a sanitiser, so keys, tokens and whole documents do not appear in
  a trace.
- `requestId` is validated before it is reflected into a header or a log line, because an
  attacker-controlled string there is a header-injection vector.
- The storage backend that is not implemented is refused outright in production rather than silently
  writing uploads to a container filesystem that disappears.

**Evidence in repo.** `apps/api/src/careerforge_api/core/config.py` (`DEV_JWT_SECRET`,
`MIN_PRODUCTION_SECRET_LENGTH`, `assert_runtime_configuration`) · `.env.example` ·
`services/failure_journal.py` · `middleware/request_id.py` · `docs/DEPLOYMENT.md` §2.

### Q57 — How do you keep PII off the public recruiter page?

**Short answer.** Two passes, not one: the payload is scanned and redacted when it is built, and scanned
again on the way out, because the cost of the second check is microseconds and the cost of publishing
somebody's phone number is not. The switch is applied at read time, so turning sharing off takes effect
immediately rather than at the next publish.

**Deep dive.**

- The findings are stored with the profile (`pii_findings`), so what was redacted and why is auditable
  rather than implied.
- Serving is server-rendered and unauthenticated by design, which is exactly why the second pass exists:
  the public endpoint is the one route where a mistake is visible to strangers.
- The measured check during development: source material that did contain an email produced public HTML
  and API responses containing neither email nor phone number; unknown and unpublished slugs both 404.

**Evidence in repo.** `apps/api/src/careerforge_api/services/public_service.py` (`scan_pii`,
`redact_pii`, second pass) · `packages/ai/careerforge_ai/parsing/pii.py` ·
`docs/ROADMAP.md` PHASE 10.

---

## Trade-offs

### Q58 — What is the project's biggest technical debt?

**Short answer.** The durable vector index: pgvector is chosen and the compose file runs it, but no
migration declares a vector column, so retrieval runs on an in-process index whose contents do not
survive a restart. It is the gap with the widest blast radius — retrieval feeds the claim gate, which
is the product's core promise.

**Deep dive.**

- It is visible rather than latent: `/system/health` reports `vector: degraded (in_memory_index)`, the
  release proof lists it under `NOT RUN`, and readiness deliberately stays `ready` because that is the
  documented behaviour.
- Runner-up: the in-process queue and rate limiter. Correct for one process, and with several replicas
  each enforces its own budget — stated on health rather than implied away.
- Third: `observability_service.py` is the least-covered core file at 72.7%, which is where I would
  expect the next defect to hide.

**Evidence in repo.** `reports/release-proof.json` `notRun` ·
`apps/api/src/careerforge_api/services/system_service.py` (`probe_vector`) ·
`reports/coverage-summary.md` · `reports/release-readiness.md` §3.

### Q59 — Why is SQLite a first-class path rather than a test fixture?

**Short answer.** Because a reviewer should be able to clone the repository and run the whole product —
API, evaluation, browser suite — with no Docker, no PostgreSQL and no API key. That decision is what
makes every number in this file reproducible on a laptop, including the ones in CI.

**Deep dive.**

- The two backends are meant to produce the same schema: migrations are dialect-aware, and the SQLite
  path calls `create_all` because it has no migration step by design.
- The cost is real and it is paid explicitly: dialect differences live in a named compatibility layer,
  and the PostgreSQL path is only exercised in CI — stated as unproven locally rather than assumed.
- It also shapes test design: the unit suite pins a throwaway SQLite file and an in-process queue, so a
  developer's local `.env` cannot make the suite depend on services it did not ask for.

**Evidence in repo.** `docs/DECISIONS.md` ADR-004 and ADR-009 · `apps/api/src/careerforge_api/db/compat.py` ·
`apps/api/tests/conftest.py` · `reports/release-proof.json` step 2.

### Q60 — What did you deliberately not build?

**Short answer.** Three things, each for a stated reason: no graph database (the queries are shallow and
set-shaped), no agent framework (the graph is small and observability matters more than abstraction), and
no "generate my whole résumé from a prompt" mode (it is the failure this product exists to prevent).
Non-goals are documented next to the goals.

**Deep dive.**

- The résumé Copilot rewrites sentences the candidate already wrote and gates each rewrite; the measured
  effect is that a rewrite is only offered when a clause can be dropped without leaving an unsupported
  noun behind — safer-rewrite rate 0.375, reported rather than tuned.
- Rejected alternatives are written down as ADRs with the reason, so the answer to "why didn't you use
  X" is a decision rather than an omission.
- The public roadmap carries the phases that were designed and not yet built, so "not built" and "not
  planned" are different words here.

**Evidence in repo.** `docs/DECISIONS.md` ADR-005, ADR-007, ADR-014 · `docs/PRD.md` (non-goals) ·
`reports/eval-report.json` (`evidence.safer_rewrite_rate` 0.375) · `docs/ROADMAP.md`.

### Q61 — What would you change with another month?

**Short answer.** Not features: five measurements. The section below is the actual list, in order, with
why each one is next rather than merely interesting.

**Deep dive.**

- The short version: a real-provider evaluation corpus, action-entailment for the scope-inflation cases,
  retrieval fusion tuning against a held-out set, real-user feedback, and longer production observation.
- Everything on that list is a measurement gap that currently makes a claim weaker than it could be —
  which is a different kind of work from adding a surface.

**Evidence in repo.** The section [If you had another month](#if-you-had-another-month) below ·
`reports/release-readiness.md` §3 · `docs/QUALITY.md` §7.

---

## Answers to rehearse out loud

One sentence each, with where the full story lives. Say these without notes.

1. **The self-referential benchmark.** The old claim corpus reported a perfect support recall across 120
   rows that held only 22 distinct claim/kind pairs with labels that tracked the rule layer — the gate
   was agreeing with itself, and the replacement's first honest run reported `support_recall 0.0000`.
   Full story: `docs/QUALITY.md` §2; `docs/INTERVIEW.md` Q1.
2. **Browser CORS versus a green Node smoke.** The API smoke suite passed 25/25 while every request from
   a real browser was blocked, because Node's `fetch` does not enforce CORS — the defect only exists in a
   browser. Full story: `docs/INTERVIEW.md` Q17; `docs/ROADMAP.md` PHASE 13 finding 16;
   `apps/web/e2e/cors.spec.ts`.
3. **The 375px table jsdom could not see.** The AI Runs table pushed cost, status and time off-screen at
   375px with no hint they were there, and jsdom has no layout engine, so 365 component tests were
   structurally unable to notice. Full story: `docs/ROADMAP.md` PHASE 11 finding 14;
   `apps/web/e2e/overflow.spec.ts`.
4. **The AI quota charged to page reads.** `GET /jobs/{id}/match` and `GET /ai/interview/{id}` cost
   tokens from the model-spend budget even though they only read stored rows — measured as 33 requests to
   AI-marked paths in sixty seconds against a bucket of 20, ten of them reads, ending in the user's real
   analysis being refused. Full story: `docs/ROADMAP.md` PHASE 14 finding 1;
   `apps/api/src/careerforge_api/middleware/ratelimit.py`.
5. **The always-true `git_dirty`.** Every evaluation artefact the project ever committed claimed a dirty
   tree, because a helper returned the sentinel `"unknown"` for empty output and the caller read it as a
   boolean — so the field that says whether numbers belong to a commit never changed value. Full story:
   `docs/ROADMAP.md` PHASE 14 finding 6; `evals/run.py` (`_tree_is_dirty`).
6. **Hybrid losing to BM25.** The keyword arm alone reaches Hit@5 0.9831 against the hybrid's 0.9661, and
   I did not tune the fusion weights because choosing them to win on 59 queries is fitting the corpus.
   Full story: `docs/INTERVIEW.md` Q12; `reports/eval-report.json`.
7. **The rollback that erased failed runs.** The run tracker wrote inside the request transaction, so any
   400 or 500 rolled the row back and the failure left no trace at all — while the executor's own comment
   claimed observability is never lost; a middleware-owned failure journal writes it after the
   transaction settles. Full story: `docs/QUALITY.md` §7; `services/failure_journal.py`;
   `docs/INTERVIEW.md` Q16.
8. **`null` versus `0`.** A stored match used to print a measured-looking zero coverage beside a live
   endpoint reporting that coverage as complete, because the model's default `0.0` was
   indistinguishable from a measurement — so counts became nullable, `usage_status` was added, and `0`
   is now reserved for a
   measured zero. Full story: `docs/ROADMAP.md` PHASE 13; `routers/jobs.py` (`get_match`);
   `apps/api/alembic/versions/0009_usage_observability.py`.

## The three questions you will be asked about how this was built

They are not technical, they are the ones an interviewer actually asks about a project of this size, and
a rehearsed non-answer costs more than the truth does. Answer with the split, then with an example.

### Q62 — How much of this did AI write?

**Short answer.** Most of the code, at a speed I could not have matched by hand — and none of the
requirements, acceptance criteria, architecture decisions, test design or defect diagnoses. The honest
way to say it is that I ran the project and the model typed it: I decided what had to be true, and I
built the machinery that could tell me whether it was.

**Deep dive.**

- **What the model did:** wrote the implementation, in phases I defined, against specifications and
  acceptance criteria I wrote first (`docs/PRD.md`, `docs/ROADMAP.md` with per-phase exit criteria).
- **What I did, and can point at:** the phase plan and its exit criteria; the 23 ADRs, each of which
  records the alternative I rejected and why; the decision that the model may never produce a number
  (ADR-014); the evaluation design, including the gate severities and the written rationale for every
  threshold; the corpus I rewrote when I found the first one was circular; and every defect diagnosis in
  `docs/ROADMAP.md` — because a generated implementation does not diagnose itself.
- **What made this different from "asking a model for an app":** every phase had to _run_, not just
  compile. A phase was finished when its tests passed, its artefacts regenerated, and its defects were
  either fixed or written down. That constraint is what turned a fast generator into a project.

**Evidence in repo.** `docs/ROADMAP.md` (per-phase findings, each naming how the defect was found);
`docs/DECISIONS.md` (ADR-014 and the rejected alternatives); `evals/config.py` (every threshold with its
rationale); `docs/QUALITY.md` §5–§7 (the evaluation that found the product's own bugs).

### Q63 — So is this "vibe coded"? Did the AI write it and you just shipped it?

**Short answer.** If that means "generated without verification", no — and the repository is built to
prove it. The distinguishing feature of this project is not how the code was produced; it is that
**nothing in it is trusted on the strength of having been produced**. There is an evaluation harness, a
browser suite, a release proof and a published list of what could not be verified.

**Deep dive.**

- **The cheap test of that claim:** ask what the project's own measurements say is _wrong_ with it.
  `unsafe_support_rate` is 5% against a target of 2%, keyword-only retrieval beats the hybrid, there is
  no durable vector index, and the deployment has no public URL. Those are in the README, not in a
  footnote.
- **The stronger test:** whether independent checks ever contradicted the implementation. They did, ten
  times, and the fixes are commits with the diagnosis attached — for example a rate limiter that
  charged page _reads_ to a model-spend budget (found by a browser suite, 33 requests against a bucket
  of 20), and a `git_dirty` flag that could only ever be true (found while generating a release
  artefact, not by reading code).
- **And the newest one, which is the honest ending to this answer:** CI ran for the first time on a
  clean machine and found six defects, three of them in the product — a migration that had never run on
  PostgreSQL, a prompt registry that resolves only for an editable install, and an image missing the
  dependencies that read a PDF. All three were invisible locally, where the whole suite was green.

**Evidence in repo.** `reports/release-readiness.md` (what is proved, what is not); `docs/ROADMAP.md`
PHASE 15 findings (the six defects CI found); `.github/workflows/ci.yml` (six jobs, including one that
brings the whole containerized stack up and runs the browser suite against it).

### Q64 — What was the hardest part? (three versions of the answer)

**Short answer, AI interviewer.** Making the claim gate _conservative without making it useless_ — the
tension between `support_recall` (do not reject honest sentences) and `unsafe_support_rate` (do not
accept invented ones), decided by rules rather than by a model, and then measured. The first corpus said
100% recall because it was labelled by the rules under test; the real number was 0%, and two genuine
policy defects were behind it.

**Short answer, software interviewer.** The transaction boundary around observability: a failed request
rolled its transaction back, which erased the record of the failure along with the failure, so the
system was blind exactly when it mattered. The fix was a failure journal written by the outermost
middleware on its own session after the transaction had settled — and the two rejected alternatives are
documented in the module, because the interesting part of that answer is why the obvious fixes do not
work.

**Short answer, HR.** Scoping. Fifteen phases, one person, and the discipline to stop: the last phase
was not "add features", it was "prove what exists, publish the gaps, and write the material that lets
somebody else evaluate it in fifteen minutes".

**Evidence in repo.** `docs/QUALITY.md` §5 (the corpus replacement and the two defects);
`packages/ai/careerforge_ai/services/failure_journal.py` (the fix and its rejected alternatives, in the
docstring); `docs/ROADMAP.md` (the phase exit criteria, including PHASE 15's "no new features" rule).

### Q65 — What was your biggest failure on this project?

**Short answer.** The first evaluation I built measured itself. It reported `support_recall 1.0000` — a
perfect score — because the corpus labels were generated by the same rules that were being evaluated. I
believed it long enough to be pleased with it.

**Deep dive.**

- **How I found it:** by asking what the benchmark would look like if the system were wrong. The second
  question about any metric is "who wrote the labels, and did they know the answer?", and the answer here
  was "my own implementation did".
- **What it cost:** the honest number was `0.0000`, and behind it two real defects in the decision
  policy — scope-inflated claims were being granted _supported_, and a model-reported blocker was
  softened by the mere presence of retrieval hits.
- **What replaced it:** 60 hand-authored adversarial cases with human gold labels, split into nine
  evidence kinds, with the failure cases named (`ev-0036`, `ev-0039`) and published as the residual 5%.
- **The lesson I would actually give:** a benchmark you generate from your own implementation is a
  mirror. It is the single most useful thing I learned on this project, and it is why every claim in the
  README now points at an artefact rather than at the prose.

**Evidence in repo.** `docs/QUALITY.md` §5 (the old corpus, the replacement, the first honest run);
`evals/suites/evidence_validation.py` and the corpus modules; `reports/eval-report.json` (the numbers
that replaced the perfect one).

## Questions whose honest answer is: I did not measure that

Say the boundary out loud; it is more persuasive than a confident guess.

| Question                                               | Honest answer                                                                                                                                                                                                                                 | What would close it                                                                                                       |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **What is your accuracy with a real provider?**        | Unknown. Every published number is the deterministic zero-key provider (`LLM_PROVIDER=heuristic`); `python evals/run.py --provider deepseek` exists but needs a key and is manual, so calibration currently describes the zero-key path only. | Run the suites against a paid provider and publish the diff, including where the model changes the verdict.               |
| **What is your throughput / where does it fall over?** | Not measured. `reports/api-performance.json` is a 20-sample latency tripwire on one laptop (no concurrency, model-calling endpoints excluded), not a load test.                                                                               | A concurrent load test against PostgreSQL with the real queue backend, with the rate limiter in the picture.              |
| **How does pgvector behave at scale?**                 | Not measured, and not implemented: no migration declares a vector column, retrieval uses an in-process index, and the PostgreSQL path has only ever run in CI.                                                                                | Implement the embeddings table and ANN index, then re-run the retrieval suite with tens of thousands of chunks.           |
| **Does it work on a real phone?**                      | Not measured on hardware. The mobile project runs a 375px viewport in Chrome with touch emulation, which caught a real stacking-order bug, but no real-device test exists.                                                                    | A device farm run of the five main flows, including the drawer and the graph canvas.                                      |
| **Is it resistant to prompt injection?**               | Not measured. The defence is structural (untrusted text in the user position, schema-bounded output, no model-set numbers) and there is no adversarial corpus or measured resistance rate.                                                    | A labelled injection corpus with a measured rate, the way the claim gate has one.                                         |
| **Is the interview planner good?**                     | Weakly evidenced. The suite is 3 cases (`iv1.0`); it proves the shape (required-skill coverage 0.8333, duplicate rate 0.0000, cross-role leakage 0.0000) rather than quality.                                                                 | A corpus of postings and candidate profiles with human-graded questions, and a measure of whether a follow-up was earned. |

## If you had another month

Five items, in this order, and none of them is a feature. The reason each one is next is that it
currently makes a claim weaker than it needs to be.

1. **A real-provider evaluation corpus.** Every number published today describes the deterministic
   heuristic provider, because a paid run needs a key and is manual. Until the same suites run against
   DeepSeek or OpenAI and the diff is published, "the gate holds" is a statement about one
   implementation of the model boundary — and calibration, in particular, is a claim about the model's
   verdicts. This is first because it is the cheapest way to turn several existing claims from
   conditional into measured.
2. **An action-entailment model for scope inflation.** The two residual unsafe cases (`ev-0036`
   「吞吐提升明显」, `ev-0039` 「整机调试」) are not keyword problems: the action is evidenced and the
   _scope_ is not. Rule matching on nouns cannot settle "did the whole machine get debugged", so the
   next honest step is a model that compares the claim's action and scope against the source sentence —
   with the present 40-case set as its regression corpus, so the fix cannot quietly trade one error
   direction for the other.
3. **Retrieval fusion tuning, against a held-out set.** The keyword arm beats the hybrid at Hit@5
   (0.9831 vs 0.9661) and I have deliberately not tuned the weights, because 59 queries is a corpus to
   fit rather than a result to trust. Doing it properly means a larger labelled set, a held-out split,
   and a pre-registered metric — otherwise the improvement is the same overfitting with better
   numbers.
4. **Real-user feedback.** Every judgment in this repository about what matters is mine. The gate's
   rules encode my choices — which error direction is worse, what counts as vague, when a rewrite is
   safe — and none of that has been tested against what a candidate would actually send to an employer.
   The cheapest useful version is a handful of real users reviewing a batch of verdicts, with their
   disagreements recorded as labelled cases.
5. **Longer production observation.** The release proof is a snapshot: one fresh install, one restart,
   one seed. It cannot see schema drift over time, queue backlog, cache growth, or whether migration
   `0009` behaves the same on a database with months of history. This comes last because it needs the
   deployment that is currently blocked — but without it, "it works" has an unstated time horizon of
   about fifty seconds.
