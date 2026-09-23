# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

- No application code has been written yet. Implementation begins at PHASE 1.
- All metrics referenced in the README are marked as targets; they will be replaced
  with values produced by real build/test/eval artifacts, and unmet targets will be
  reported as unmet.
