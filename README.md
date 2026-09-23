# CareerForge AI

> **Evidence-driven AI career operating system.**
> Turn your experience into verifiable career evidence.

<p align="center">
  <b>把经历变成证据，把证据变成竞争力。</b>
</p>

<!-- Badges: activated in PHASE 15 once the remote repository exists -->
![Status](https://img.shields.io/badge/status-in%20development-orange)
![Phase](https://img.shields.io/badge/phase-5%20%2F%2015-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.12-3776AB)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6)
![Next.js](https://img.shields.io/badge/Next.js-15-black)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-4169E1)

> 🚧 **Project status: actively under development (PHASE 5 / 15 complete).**
> The AI core (orchestration, providers, retrieval, evidence graph, scoring, 9 agents),
> the API (contract, auth, middleware, persistence) and the frontend shell are built and
> tested; uploaded documents are now parsed, chunked and stored through the queued
> worker. Every number in this README comes from a real build/test/eval artifact — never
> from an estimate.
> See [ROADMAP.md](./docs/ROADMAP.md) for the live phase tracker.

---

## The problem

Large language models made **writing a beautiful resume free**. That destroyed the value of writing well and created a new scarcity: **being able to prove it**.

Most AI resume tools happily generate:

> "Proficient in Redis"
> "Improved system performance by 50%"
> "Designed high-concurrency architecture"

…for candidates who never did any of it. In an interview, that is not an asset — it is a liability.

## The idea

CareerForge AI is not another resume generator. It is a **career operating system built on an evidence graph**:

```
Candidate → Experience → Project → Skill → Evidence
```

Every claim that lands on your resume must be traceable to something real — a file, a commit, a README, a document, an internship record. If it cannot be traced, the system **refuses to write it**.

> Most resumes describe what you **claim** to know.
> CareerForge shows the **evidence**.

---

## Core capabilities

| # | Capability | What it actually does |
|---|---|---|
| 01 | **Career Evidence Graph** | Interactive heterogeneous graph linking claims → skills → projects → repositories → files → commits, with a **deterministic confidence score** per evidence node |
| 02 | **JD Intelligence** | Structured JD parsing into a required / preferred / bonus skill tree, with the original JD sentence attached to every extracted skill |
| 03 | **Explainable Job Match** | 5-dimension weighted score (Skill 40 / Experience 25 / Project 20 / Education 5 / Evidence 10) with a `Why 86?` breakdown of formulas and contributing evidence — reproducible, not vibes |
| 04 | **AI Resume Copilot + Hallucination Gate** | Bullet-level resume diff where **every generated sentence passes a claim validator**; unsupported claims are rejected, weak ones get a safer rewrite |
| 05 | **Adaptive Interview Simulator** | Six interview modes; questions generated from *your* JD, resume and evidence graph; difficulty escalates L1 concept → L2 engineering → L3 debugging |
| 06 | **Career Analytics & Pipeline** | Application kanban, funnel/response/offer rates, and skill ↔ interview-success correlation with honest sample-size labelling |
| 07 | **Recruiter View** | A public, login-free candidate page where a recruiter can click any skill and see the underlying evidence — an interactive resume instead of a PDF |
| 08 | **AI Observability** | Every agent run, token, latency, cost and prompt version recorded; three-level caching with visible hit rates and budget guardrails |

### What makes it different

| | Typical AI resume tool | Generic LLM chat | **CareerForge AI** |
|---|---|---|---|
| Generated content is traceable to sources | ❌ | ❌ | ✅ **claim → evidence provenance** |
| Defends against fabricated claims | ❌ | ❌ | ✅ **validator + confidence gate** |
| Match score is explainable | ❌ single % | ⚠️ prose | ✅ **5-dim weighted + `Why?`** |
| Reads real code evidence | ❌ | ⚠️ manual paste | ✅ **file- and commit-level** |
| Interview prep uses your own data | ❌ generic bank | ⚠️ stateless | ✅ **JD + evidence graph driven** |
| Works with **zero** API keys | ❌ | ❌ | ✅ **deterministic heuristic provider** |

---

## Architecture

```
Frontend            Next.js 15 · App Router · TypeScript strict · Tailwind v4 · React Flow · Recharts
    │  REST + SSE
API                 FastAPI · Pydantic v2 · SQLAlchemy 2.0 async · Alembic
    │
AI Core             Agent Orchestrator · 9 Agents · Hybrid RAG · Evidence Graph Engine · Scoring Engine
    │               (zero web-framework dependencies — independently testable & evaluable)
Ports               LLMProvider · VectorStore · Queue · GitHub · Storage
    │
Infrastructure      PostgreSQL + pgvector · Redis · Worker · Object storage
```

| Component | Choice | Why |
|---|---|---|
| Frontend | Next.js 15 + RSC | SSR performance, no theme flash, data-dense dashboards |
| Backend | FastAPI + Pydantic v2 | One schema definition constrains both the HTTP contract **and** LLM structured output |
| Database | PostgreSQL 16 + pgvector | Relational + vector + full-text in a single transaction |
| Retrieval | Hybrid (dense + FTS) with **RRF** | Technical nouns (`STM32F407`, `heap_4`) need lexical recall; intent needs semantics |
| Agents | **Custom orchestrator** | Explicit, testable, observable DAG — no framework magic |
| Scoring | **Deterministic** | Reproducible, explainable, regression-testable; LLM never produces numbers |
| Local mode | SQLite + in-process queue + heuristic provider | The whole product runs and demos with **no Docker, no Redis, no API key** |

Full design: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) · Decisions: [`docs/DECISIONS.md`](./docs/DECISIONS.md)

---

## Documentation

| Document | Contents |
|---|---|
| [PRD.md](./docs/PRD.md) | Product definition, personas, requirements, non-goals, risks |
| [ARCHITECTURE.md](./docs/ARCHITECTURE.md) | System design, agent orchestration, RAG pipeline, security |
| [DATABASE.md](./docs/DATABASE.md) | 32-table schema, indexes, pgvector config, local parity layer |
| [API.md](./docs/API.md) | REST surface, error codes, SSE contracts, rate limits |
| [UI.md](./docs/UI.md) | Design system, tokens, sitemap, page specs, a11y, responsiveness |
| [ROADMAP.md](./docs/ROADMAP.md) | 16 phases with exit criteria and progress tracker |
| [DECISIONS.md](./docs/DECISIONS.md) | 22 ADRs with rejected alternatives |
| INTERVIEW.md | How to present this project (60s / 3min / 5min deep dive) — PHASE 14 |

---

## The evidence-confidence formula

Confidence is not an LLM opinion — it is a weighted, auditable formula:

```
confidence = 0.30 · source_authority     # commit/file 1.00 · README 0.85 · doc 0.80 · self-report 0.55
           + 0.15 · recency              # exp(-age_days / 540)
           + 0.20 · specificity          # line-level 1.00 · repo-level 0.75 · prose 0.45
           + 0.20 · corroboration        # min(1, 0.4 + 0.2 × independent_sources)
           + 0.15 · extraction_quality   # deterministic parser 1.00 · LLM 0.70 · heuristic 0.50
```

This formula is enforced **at the database level**:

```sql
CONSTRAINT ck_evidence_confidence_formula CHECK (
  abs(confidence - (0.30*source_authority + 0.15*recency_score + 0.20*specificity
                  + 0.20*least(1.0, 0.4 + 0.2*corroboration_count)
                  + 0.15*extraction_quality)) < 0.002
)
```

A claim is only allowed onto a resume when `confidence ≥ 0.75` **and** it is backed by ≥ 2 independent sources. Quantified claims (`"improved performance by 70%"`) with no quantitative evidence are rejected **by deterministic rules before the LLM is ever consulted**.

---

## Repository layout

```
careerforge-ai/
├── apps/
│   ├── web/                 # Next.js 15 frontend
│   └── api/                 # FastAPI backend
├── packages/
│   ├── ai/                  # careerforge_ai — agents, RAG, graph, scoring (framework-free)
│   ├── shared/              # shared TS types + generated API client
│   ├── ui/                  # shared UI primitives
│   └── config/              # eslint / tsconfig / tailwind presets
├── prompts/                 # versioned prompt registry (markdown + front-matter)
├── evals/                   # evaluation framework + labeled datasets
├── tests/                   # integration, e2e, fixtures
├── infra/                   # Dockerfiles, DB init, deployment
├── docs/                    # design documents + screenshots/GIFs
├── scripts/                 # seed, bench, dev helpers
└── docker-compose.yml
```

---

## Quick start

> ⚠️ Available from PHASE 1. Two supported paths:

**With Docker (full stack)**

```bash
git clone <repo> && cd careerforge-ai
cp .env.example .env
docker compose up --build
# web → http://localhost:3000 · api → http://localhost:8000/docs
```

**Without Docker (SQLite + in-process queue + heuristic provider — no API key needed)**

```bash
pnpm install
pnpm --filter api dev            # FastAPI on :8000
pnpm --filter web dev            # Next.js on :3000
```

**Demo account**

```
email:    demo@careerforge.ai
password: (demo login button — no password required)
```

The demo account is seeded with a complete candidate (Alex Chen): 3 projects, 9 skills, ~180 evidence records, 12 analyzed jobs, 16 applications, 5 interviews. **No page is ever empty.**

---

## Testing & evaluation

```bash
pytest packages/ai/tests -q     # AI core (currently 201 tests)
python evals/run.py             # labeled suites → reports/eval-report.json
pnpm typecheck && pnpm lint     # TypeScript strict + ESLint
python scripts/check_layering.py        # architecture guard
python scripts/check_file_length.py     # the 500-line rule
python scripts/check_design_tokens.py   # no raw colours in components
```

### Measured results

Produced by `python evals/run.py` on the current commit and committed to
[`reports/eval-report.json`](reports/eval-report.json), so these numbers can be
checked rather than trusted. Provider: **heuristic** (the zero-API-key path).

| Suite | Metric | Result | Target |
|---|---|---|---|
| JD extraction | required-skill F1 | **0.883** | ≥ 0.85 |
| JD extraction | required-skill precision / recall | 0.791 / **1.000** | — |
| JD extraction | company-blurb distractor leakage | **0.000** | ≤ 0.05 |
| JD extraction | quoted-evidence grounding | **1.000** | = 1.00 |
| JD extraction | role / location / education / years accuracy | **1.000** / **1.000** / **1.000** / 0.950 | ≥ 0.90 |
| JD extraction | requirement-level accuracy | 0.946 | — |
| Claim validation | fabricated-metric rejection | **1.000** | = 1.00 |
| Claim validation | false "supported" rate | **0.000** | ≤ 0.05 |
| Claim validation | supported-claim recall | **1.000** | ≥ 0.85 |
| Claim validation | safer-rewrite offered | 0.489 | — |
| Retrieval | Recall@5 | **0.966** (57/59) | ≥ 0.95 |
| Retrieval | Recall@1 | 0.847 | — |
| Retrieval | MRR | 0.901 | ≥ 0.85 |

**The datasets are generated with exact ground truth, not scraped** — real job ads
carry no labels, so precision and recall would be unmeasurable. They should be
read as indicators on a controlled corpus, not as market-representative accuracy.

### Known weaknesses, measured rather than omitted

| Weakness | Value | Cause |
|---|---|---|
| Bonus-skill F1 | 0.776 | Bonus skills are sparse and their phrasing is the most varied of the three levels |
| Required-skill precision | 0.791 | Residual over-extraction when a technology appears outside any recognised section |
| Safer-rewrite rate | 0.489 | A rewrite is only offered when a clause can actually be dropped; many claims are single-clause |
| Claim threshold margin | 0.011 / 0.009 | Character-level overlap cannot see paraphrase, so the supported/unsupported separation is narrow (unsupported tops out at 0.404, supported bottoms out at 0.424). Widening it needs semantic matching — which is exactly what `--provider deepseek` measures. |
| Retrieval paraphrase misses | 2 / 59 | The zero-key character-n-gram embedding misses two intent-style queries; both are recorded in the report with the ids returned instead |

The measurement loop is the point. The first run of these suites reported
**100% distractor leakage**, a **13.3% false-support rate**, and a **0.675
Recall@5**. All three were investigated; the first two were fixed in response to
the number and now sit at zero, while the third turned out to be partly a bug in
my own dataset — the query `vTaskDelayUntil` did not appear anywhere in the
corpus. After fixing it the same suite reads 0.966.

### Not yet measured

`interview_relevance` (PHASE 7), an end-to-end pipeline suite (PHASE 6) and
confidence calibration (needs hand-labelled evidence). A suite is added when the
component it measures exists — shipping a metric for something that has not been
built is the failure mode this project is about.

> The frontend has **no automated tests yet** (PHASE 12). Its dashboard success
> path has not been exercised against a running API, and responsive behaviour was
> reasoned from the styles written rather than measured in a browser.

---

## Security & privacy

- **Prompt injection:** untrusted documents are wrapped as declared *data*, never spliced into instruction positions; all LLM output is schema-validated
- **File uploads:** MIME + magic-number validation, size caps, parser timeouts, sandboxed execution
- **Auth:** JWT with resource-level authorization; cross-tenant access returns `404`, not `403`
- **Secrets:** environment-only, validated at startup, redacted in logs
- **Privacy-first:** Local Mode keeps raw resume text off the server; public profiles are opt-in per section; PII scanning before any export or publish; full data export and hard delete
- **Rate limiting:** per-IP and per-user token buckets, stricter on AI endpoints

Details: [ARCHITECTURE.md § Security](./docs/ARCHITECTURE.md#10-安全架构)

---

## Limitations (honest list)

CareerForge AI is a portfolio-grade system, not a production SaaS. Known boundaries:

- Single-tenant auth is intentionally minimal (no email verification, no SSO, no org accounts)
- The local SQLite vector path performs exact search — fine below ~50k vectors, not a distributed index
- Confidence weights are hand-tuned from design reasoning, not fitted on a large labeled corpus
- `GitHub App` / browser extension / VS Code extension are **not** implemented (listed as P2 in the PRD)
- Interview scores are heuristic-assisted and advisory, not a validated psychometric instrument

---

## Roadmap

See [ROADMAP.md](./docs/ROADMAP.md). Current: **PHASE 0 ✅ → PHASE 1 ✅ → PHASE 2 ✅ → PHASE 3 ✅ → PHASE 4 ✅ → PHASE 5 ✅
(dashboard + first live frontend↔API run) → PHASE 6 (Resume Copilot persistence and UI)**.

---

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md).

## License

[MIT](./LICENSE)

---

<p align="center">
  <i>Most resumes describe what you claim to know.<br/>CareerForge shows the evidence.</i><br/>
  <sub>大多数简历告诉别人你会什么，CareerForge 告诉别人你凭什么这么写。</sub>
</p>
