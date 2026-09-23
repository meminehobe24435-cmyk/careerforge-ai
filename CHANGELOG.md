# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
