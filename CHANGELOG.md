# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
