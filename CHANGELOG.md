# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — PHASE 2b · Career entities and the profile import path

- `educations`, `experiences`, `projects`, `achievements` and `profile_skills` (§2.2) with
  migration `0005`, verified column-for-column against the ORM models.
- `POST /profile/import` extracts entities from text or from a stored document and persists
  them; `GET /profile` returns what is stored. Both are the *assembled* profile every other
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

- **The evidence dimension measured the wrong list.** It was computed over the *highlighted*
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
