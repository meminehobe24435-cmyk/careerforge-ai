# Role mapping — how to present CareerForge to four different interviewers

The repository is the same; the **order of the story** is not. This file decides which part of the
project leads, which measurement gets quoted, and — just as important — what *not* to claim to a
given audience. The material itself lives in [`PORTFOLIO.md`](./PORTFOLIO.md) (bullets, STAR stories,
descriptions) and [`INTERVIEW_QUESTIONS.md`](./INTERVIEW_QUESTIONS.md) (45+ prepared answers).

## 0. Positioning, fixed

| | |
| --- | --- |
| Name | **CareerForge AI** |
| Category | **Evidence-Driven AI Career Operating System** |
| Brand line | *Most resumes describe what you claim to know. CareerForge shows the evidence.* |
| Never described as | "a résumé assistant", "a job board", "an AI agent demo" — the project is one thing, and calling it three things in three sentences is how an interviewer stops believing any of them |

The differentiator is not that it uses an LLM. It is that **the LLM is not trusted**: nothing is
generated until the candidate's own material has been assembled into an evidence graph, and every
generated sentence passes a gate. That single sentence is the answer to "what is it", and every role
variant below is a different emphasis on it.

## 1. Routing table

| Role | Project order | Lead with | Lead story | Do **not** claim |
| --- | --- | --- | --- | --- |
| **AI Application Engineer** | CareerForge **first** | Evidence graph → claim validator → evaluation → cost accounting | The benchmark that measured itself | That the public demo runs a real LLM (it runs the deterministic zero-key provider; real providers are a configuration switch) |
| **Software Engineer (backend/full-stack)** | CareerForge first if the JD is API/data-heavy, otherwise second | Architecture, API contract, migrations, transactions, CI, observability | The failed run that left no trace | That it is deployed and serving traffic (the image path has never been witnessed) |
| **Embedded / firmware** | Drone / STM32 project **first**, CareerForge second or third | Engineering breadth: Python, backend, testing discipline, CI, debugging | Browser CORS vs green Node smoke (a real-environment debugging story) | That CareerForge is an embedded project — it is not, and saying so costs credibility with the one interviewer who can tell |
| **Solution / Product Engineer** | CareerForge first | Product loop, explainability, documentation, demo, deployment thinking | The 375 px table that jsdom could not see | Business impact: there are no users, no revenue, no retention numbers, and inventing one ends the interview |

## 2. AI Application Engineer

**What they are hiring for.** Retrieval that works, agents that do not wander, evaluation that means
something, and an honest account of where the model fails.

**Lead with.** `packages/ai/careerforge_ai/agents/validator.py` (rules first, model may only judge
support), the hybrid retriever (`rag/retriever.py`), `evals/run.py` with its declared gates, and the
usage envelope that separates *reported* cost from *unknown* cost.

**Quote these measurements.**

- `unsafe_support_rate` **0.0500** (gate ≤ 0.075, target 0.02 **not met** — say the gap out loud)
- fabricated-number acceptance **0.0000**
- evidence macro F1 **0.8481**, accuracy **0.9000**, unsupported recall **0.9355**
- RAG Hit@1 **0.8475**, Hit@5 **0.9661**, MRR **0.9011** — and keyword-only Hit@5 **0.9831**, which is
  *better*, reported rather than tuned away
- calibration ECE **0.0316**, Brier **0.0904**, top bucket **+0.063 over-confident**

**Open with story 1** ("the benchmark that measured itself") and keep story 6 (`null` ≠ `0`) for the
follow-up about data semantics. **Expect:** "why not just prompt a model to check the claims?" → the
answer is ADR-014 plus the calibration numbers: a model verdict is an input to arithmetic, never the
number itself.

**Weakness to volunteer:** the evaluation runs on the deterministic provider, so the calibration
describes the zero-key path; a real-provider corpus is the first item on the "another month" list.

## 3. Software Engineer (backend, full-stack, platform)

**What they are hiring for.** Someone who can hold a system in their head: schemas, transactions,
contracts, failure modes, and a build that stays green.

**Lead with.** The layering rule (the AI core may not import a web framework or an ORM, enforced by
`scripts/check_layering.py`), the API envelope and error contract, Alembic migrations `0001`–`0009`
on both SQLite and PostgreSQL, the four-layer test strategy, and CI's five jobs.

**Quote these measurements.**

- **1,385** automated tests — 553 AI core · 400 API · 365 web · 45 browser · 22 metric
- core-domain coverage **92.5%** (and the reason that number is scoped to the core, not the repo)
- release proof **7/7** on the native path: fresh database → migrate → seed twice → production-mode
  API → built frontend → 25 contract smoke checks → restart
- 45 browser flows (desktop 27 + mobile 18), axe **0 critical / 0 serious**

**Open with story 5** ("the failed run that left no trace" — a transaction-boundary bug) and use
story 4 (`git_dirty`) as the "small bug, large semantic impact" anecdote.

**Weakness to volunteer:** the rate limiter and the queue are in-process, so a second replica would
multiply the effective budget; it is stated on `/system/health` and in `docs/DEPLOYMENT.md` rather
than hidden.

## 4. Embedded / firmware

**The honest framing.** CareerForge is **not** an embedded project. It is the evidence that you can
also build software at a scale your MCU work never reaches: HTTP contracts, relational schemas,
migrations, CI, observability, and a test suite that is measured rather than asserted.

**Order.** Your drone / STM32 / FreeRTOS project leads — it is where the hardware depth is. CareerForge
goes second or third, described as a software-engineering breadth project.

**What transfers, and is worth naming explicitly:**

| Embedded habit | Where it shows up in CareerForge |
| --- | --- |
| Determinism over vibes | Scoring is arithmetic with a versioned formula; the model never produces a number (ADR-014) |
| Bus/protocol contracts | One response envelope, cross-tenant reads return `404` not `403` |
| Timing and retry discipline | Provider chain ends at a zero-key fallback; timeouts, malformed JSON and 429s are injected in tests |
| Debugging with instruments, not guesses | Every API response carries a request id; every AI run has a step trace |
| Bounded resource use | Rate-limit budgets per group, cost accounting per call, upload caps |

**Quote these measurements.** 45 browser flows; 4/4 evaluation gates; the six real defects found at
release (the quota mis-count, the always-true provenance flag) — these are debugging stories, not AI
stories, and they are the ones an embedded interviewer will actually respect.

**Do not claim** embedded relevance you cannot support. Say instead: "this project proves I can carry
a system from schema to deployment on the software side; my firmware work is where the hardware depth
is."

## 5. Solution / Product Engineer

**What they are hiring for.** Someone who can sit between a customer and an engineering team: model
the problem, choose a scope, deliver something demonstrable, and explain the trade-offs.

**Lead with.** The product loop (material → evidence graph → JD analysis → explainable match → claim
validation → interview → tracker → analytics), the explainability rule ("every number shows the
definition it came from; a page that cannot get data shows nothing rather than a substitute"), and the
documentation set — README, demo script, deployment guide, release record.

**Quote these measurements.** 242 evaluation cases across 4 suites; 41 metrics each with a threshold,
a severity and a written rationale; 92.5% core coverage; the release-readiness report with its
`DEPLOYMENT BLOCKED` section — a delivery document that names what it could not prove is the single
most persuasive artefact for this role.

**Open with story 3** (the AI quota charged for page reads) — it is a *product* insight: the budget
was supposed to bound cost and was instead taxing page views. Then story 2 (CORS) as the
"we tested the wrong environment" lesson.

**Do not claim** traction. There are no users, no retention, no revenue. What is real: a working
product, a documented quality system, and a release process.

## 6. Vendor / ATS keyword map

The repository genuinely covers these; they can appear in a résumé *because the code is there*.

| Keyword | Where it is real |
| --- | --- |
| Python · FastAPI · Pydantic · SQLAlchemy · Alembic | `apps/api`, `packages/ai` (editable installs, no framework imports in the core) |
| TypeScript · React · Next.js (App Router) · Tailwind · React Flow · Recharts | `apps/web`, `packages/ui`, `packages/shared` |
| PostgreSQL · pgvector · Redis · SQLite parity | migrations `0001`–`0009`, CI's `api-postgres` job, compose file |
| RAG · hybrid retrieval · BM25 · RRF · embeddings | `careerforge_ai/rag/` |
| LLM · prompt engineering · structured output · provider fallback | `careerforge_ai/providers/`, prompt registry |
| AI agents · orchestration · DAG | `careerforge_ai/orchestrator/` |
| Evaluation · benchmarks · calibration · gates | `evals/`, `reports/` |
| Observability · tracing · cost accounting · metering | `/app/ai-runs`, `/app/costs`, usage envelope |
| Testing · pytest · Vitest · Playwright · axe | 1,385 tests, 45 browser flows, a11y gate |
| CI/CD · GitHub Actions · Docker · docker compose | `.github/workflows/ci.yml` (5 jobs), `infra/docker/` **[image path CI-unverified until the `images` job has run — check before claiming it]** |
| Security · JWT · RBAC · prompt injection · PII redaction | `docs/ARCHITECTURE.md` §10, `services/public_service.py` |

**Do not** repeat a keyword three times to please a parser. An ATS scores a keyword that appears in
context; a human reads the same line and notices the padding.

## 7. Ordering strategy

- **AI application / ML platform JD** → CareerForge first, described in one line, then the evidence
  and evaluation work.
- **Backend / platform JD** → CareerForge first if the JD mentions Python + a relational database +
  testing; otherwise second, after the most backend-heavy project on the résumé.
- **Embedded JD** → the STM32/FreeRTOS project first, CareerForge second or third, one line about
  software breadth.
- **Solution / product JD** → CareerForge first; lead with the product loop and the documentation, not
  with the model.

## 8. Rehearsal checklist

Before an interview, be able to answer these without opening anything (the full answers are in
[`INTERVIEW_QUESTIONS.md`](./INTERVIEW_QUESTIONS.md)):

- [ ] What the product does, in one sentence, with no acronyms
- [ ] Why the model is not allowed to produce a number
- [ ] The one number you are least proud of (`unsafe_support_rate` 5% against a target of 2%) and why
      it is not fixed yet
- [ ] The deployment status: `v1.0.0-rc.1`, no live URL, image path not yet witnessed — in one breath,
      without apologising
- [ ] The one thing you would do with another month, and why it is not a feature
