# Portfolio material

Everything an interviewer, an ATS or a résumé needs, in one file. Every number here is reproduced by
the commands in §13 and lives in a committed artefact — **if a figure is not in `reports/`, it is not in
this file.** Spoken versions are in [`INTERVIEW.md`](./INTERVIEW.md); the per-role routing (what to lead
with, what _not_ to claim) is in [`ROLE_MAPPING.md`](./ROLE_MAPPING.md); 61 prepared answers are in
[`INTERVIEW_QUESTIONS.md`](./INTERVIEW_QUESTIONS.md); the five files to open in an interview are in
[`CODE_TOUR.md`](./CODE_TOUR.md).

|                  |                                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------- |
| Release          | **`v1.0.0-rc.1`** (tagged and pushed)                                                                    |
| Repository       | [github.com/meminehobe24435-cmyk/careerforge-ai](https://github.com/meminehobe24435-cmyk/careerforge-ai) |
| Live demo        | **none yet** — no hosting credential is available to this machine; see §11                               |
| Verified locally | 1,385 tests · 45 browser flows · 4/4 evaluation gates · 92.5% core coverage · release proof 7/7          |

---

## 1. Project summary

|              |                                                                                                             |
| ------------ | ----------------------------------------------------------------------------------------------------------- |
| **Name**     | CareerForge AI                                                                                              |
| **Category** | Evidence-Driven AI Career Operating System                                                                  |
| **One line** | An AI career platform that refuses to write a sentence the candidate's own evidence cannot support          |
| **Stack**    | Next.js 15 · FastAPI · PostgreSQL 16 + pgvector · Redis · Python 3.12 AI core                               |
| **Scale**    | 117 commits · 1,385 automated tests · 242 evaluation cases · 41 gated metrics                               |
| **Status**   | Release candidate, verified end to end on the native path; containerized proof running in CI; no public URL |

> **Most resumes describe what you claim to know. CareerForge shows the evidence.**

## 2. Problem

Large language models made a beautiful résumé free to produce, which destroyed the value of writing
well and created a new scarcity: **being able to prove it**. Existing tools optimise the wrong thing —
they generate fluent text and leave the candidate to defend it in an interview, where one embellished
number is a rejected offer rather than a typo. The hard part is not generation. It is **refusing to
generate**, and being able to show why.

## 3. Solution

A product loop in which nothing is written before the evidence exists:

```
material  →  Evidence Graph  →  JD analysis  →  explainable match  →  claim validation  →  interview  →  tracker  →  analytics
(resume,      (nodes, edges,     (three-level     (five weighted       (rules → retrieval   (adaptive,    (board,      (funnel,
 GitHub,       confidence from    skill tree,      dimensions,          → model verdict →    difficulty    events)      rates)
 manual)       an audited         JD-quoted        deterministic)       arithmetic)          adjusted)
               formula)           evidence)
```

Four rules make it a system rather than a wrapper:

1. **The model never produces a number.** Scoring is arithmetic with a versioned formula (ADR-014);
   the model's only job is to judge whether evidence supports a claim.
2. **Rules run before the model.** A quantified claim with no quantitative evidence is rejected
   deterministically — the model is never consulted, so it cannot be talked into it.
3. **Unknown is not zero.** A provider that does not report token usage produces `null` counts and a
   documented floor, not a `0` that reads as a measurement.
4. **Everything degrades to something honest.** With no API key the provider chain ends at a
   deterministic rule engine, so the whole product — and its entire evaluation — runs at zero cost.

## 4. Architecture

```
Frontend            Next.js 15 · App Router · TypeScript strict · Tailwind v4 · React Flow · Recharts
    │  REST + SSE
API                 FastAPI · Pydantic v2 · SQLAlchemy 2.0 async · Alembic (0001–0009)
    │
AI Core             Orchestrator · 9 agents · Hybrid RAG · Evidence Graph · Scoring
    │               (no web-framework and no ORM imports — enforced by scripts/check_layering.py)
Ports               LLMProvider · VectorStore · Queue · GitHub · Storage
    │
Infrastructure      PostgreSQL + pgvector · Redis · worker · object storage
```

The layer rule is the load-bearing decision: the AI core is independently testable and evaluable
because it cannot reach into the web framework. Full design in [`ARCHITECTURE.md`](./ARCHITECTURE.md);
the 23 decisions with their rejected alternatives in [`DECISIONS.md`](./DECISIONS.md).

## 5. Core innovation

**The claim gate.** A résumé sentence becomes publishable only through a four-stage decision:

| Stage            | Who decides                                      | Why it is there                                                                                                                      |
| ---------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| Rule blockers    | deterministic code                               | quantified claims without quantitative evidence, unbacked superlatives, technologies absent from the taxonomy                        |
| Hybrid retrieval | BM25 + vector + RRF over the user's own evidence | technical nouns (`STM32F407`) need lexical recall; intent needs semantics                                                            |
| Model verdict    | the LLM, and only about _support_                | it may say "the evidence does not support this", never "confidence 0.8"                                                              |
| Arithmetic       | a versioned formula (`confidence@1.0.0`)         | 0.30 source authority + 0.15 recency + 0.20 specificity + 0.20 corroboration + 0.15 extraction quality, mirrored by a database CHECK |

## 6. Quality

The project treats "does the AI work" as a measurement problem with published gaps:

- **4 evaluation suites, 242 labelled cases, 41 metrics**, each with a threshold, a severity and a
  written rationale; missing a `gate` fails the build, missing a `report` prints and continues.
- **A committed baseline** so a change is a diff (`improved 4 · same 35 · regressed 0`) rather than an
  argument — and calibration is wired into that diff.
- **1,385 automated tests** across four layers chosen for what _only_ that layer can observe: pure
  arithmetic, the contract as shipped, rendering rules, and a real browser.
- **The gaps stay published**: `unsafe_support_rate` 5% against a target of 2%, keyword-only retrieval
  beating the hybrid at Hit@5, no durable vector index, no live provider run.

## 7. Key metrics

| Metric                       | Value                                                                         | Artefact                            |
| ---------------------------- | ----------------------------------------------------------------------------- | ----------------------------------- |
| Tests                        | 1,385 (553 AI core · 400 API · 365 web · 45 browser · 22 metric)              | test runs                           |
| Browser E2E                  | 45 passed (desktop 27 · mobile 18), axe 0 critical / 0 serious                | Playwright                          |
| Evaluation                   | 4/4 suites, 242 cases, 41 metrics, gates pass                                 | `reports/eval-report.json`          |
| Unsafe support rate          | 0.0500 (gate ≤ 0.075; target 0.02 **not met**)                                | `reports/eval-report.json`          |
| Fabricated-number acceptance | 0.0000                                                                        | `reports/eval-report.json`          |
| Evidence macro F1            | 0.8481 (accuracy 0.9000 · unsupported recall 0.9355)                          | `reports/eval-report.json`          |
| RAG retrieval                | Hit@1 0.8475 · Hit@5 0.9661 · MRR 0.9011 (keyword-only Hit@5 0.9831 — better) | `reports/eval-report.json`          |
| Calibration                  | ECE 0.0316 · Brier 0.0904 (top bucket +0.063 over-confident)                  | `reports/confidence-calibration.md` |
| Core-domain coverage         | 92.5% (1,556/1,683 statements)                                                | `reports/coverage-summary.md`       |
| Release proof                | 7/7 native steps                                                              | `reports/release-proof.json`        |

## 8. Engineering stories

Six, each with the lesson. Every one is a real commit — the defect, the diagnosis and the fix are in
`git log`.

### S1 — The benchmark that measured itself

- **Situation.** The first evidence evaluation reported a beautiful **100% support recall**.
- **Task.** Decide whether that number meant anything before quoting it.
- **Action.** Read the dataset generator: the corpus was labelled _by the same rules under test_. The
  evaluation was grading its own homework. Replaced it with 60 hand-authored adversarial cases
  (fabricated metrics, scope inflation, vague magnitude, out-of-scope claims) with human gold labels.
- **Result.** The honest number was `support_recall 0.0000` — and behind it, two real defects in the
  decision policy: scope-inflated claims were granted _supported_, and a model-reported blocker was
  softened by the mere presence of retrieval hits. After the fixes: unsupported recall **0.350 →
  0.935**, unsafe acceptance **0.100 → 0.050**.
- **Lesson.** A benchmark generated from your own implementation measures your implementation, not the
  world. The first question about any metric is "who wrote the labels, and did they know the answer?"

### S2 — Green Node smoke, dead browser

- **Situation.** A 25-check API smoke suite passed against the running stack while the product was
  unusable in a browser.
- **Task.** Explain why every request worked from Node and none from the page.
- **Action.** Reproduced it in a real browser: the web app's origin was not in the API's
  `CORS_ORIGINS`, so the browser blocked every response _before_ the app could read it. Node's `fetch`
  does not enforce CORS, which is exactly why the smoke suite was blind to it.
- **Result.** A permanent regression spec asserting both directions — the allowed origin can read the
  API from page context (including a preflighted authenticated call), a non-allowed origin is not
  granted, and a wildcard is explicitly refused.
- **Lesson.** "It passes from the terminal" is not a statement about the browser. Choose the harness for
  what it _enforces_, not for what it can reach.

### S3 — The AI budget that charged for page reads

- **Situation.** Late in the release run the browser suite began failing with
  `Rate limit exceeded for ai requests`, on an analysis the user had every right to run.
- **Task.** Decide whether the limiter was too tight or the accounting was wrong.
- **Action.** Read the API log instead of the error: **33 requests to AI-marked paths in the 60 seconds**
  ending at the first `429`, against a bucket of 20 — and **ten of them were `GET`s**
  (`GET /jobs/{id}/match`, `GET /ai/interview/{id}`) that read a stored row and never touch a provider.
- **Result.** The budget now covers only the methods that can spend (`POST`/`PUT`/`PATCH` on AI paths);
  reads are charged to `read`. Documented in `docs/API.md` §1.7 and pinned by two tests: a
  classification test and a behavioural one proving five reads leave the AI tokens intact while the
  third spending call is still refused.
- **Lesson.** A quota is a statement about cost; when it counts things that cost nothing, it silently
  stops protecting what it was built to protect.

### S4 — Every report said the tree was dirty

- **Situation.** The release-candidate evaluation artefact recorded `git_dirty: true` from a tree that
  had just been verified clean.
- **Task.** Explain the contradiction before publishing an artefact that would look careless.
- **Action.** Called the helper directly: `git status --porcelain` on a clean tree returned the string
  `"unknown"`, because the helper replaced _any_ empty output with that sentinel — and the caller read it
  with `bool(...)`, where a non-empty string is true.
- **Result.** Three cases distinguished instead of two (text = dirty, empty = clean, `None` = git could
  not answer, which counts as dirty because cleanliness was not proved), with a test per case.
- **Lesson.** A flag that always holds the same value is not provenance, it is decoration — and a
  provenance field's failure mode is worse than having none, because people trust it.

### S5 — A failed run that left no trace

- **Situation.** The observability layer promised every failed AI run was recorded. A 500 produced no
  run row at all.
- **Task.** Make failure visible without breaking the transaction that the failure rolled back.
- **Action.** Traced it to the write happening _inside_ the request transaction, which `get_db` rolls
  back on any exception — erasing the evidence of the failure along with the failure. Wrote the record
  to a **failure journal** instead, flushed by the outermost middleware on its own short-lived session,
  after the request transaction has settled.
- **Result.** Failed runs survive, carrying `status = failed`, a sanitised error code and a request id,
  with nothing secret written. Two rejected alternatives are documented in the module (SAVEPOINT still
  rolls back; a second session mid-transaction deadlocks SQLite).
- **Lesson.** Observability that shares a transaction with the thing it observes has the same lifetime
  as that thing — which is exactly backwards.

### S6 — `null` is not `0`

- **Situation.** The cost page showed `$0.00` for runs that had certainly spent tokens.
- **Task.** Decide what a cost report should say when the provider does not tell you.
- **Action.** Found that the structured-output path returned only the parsed schema and dropped the
  provider's usage envelope, so every agent recorded zero tokens. Introduced a usage envelope for all
  three call shapes carrying `usage_status`: `reported`, `estimated`, `cached`, `unavailable`.
- **Result.** When nothing was reported the counts became SQL `NULL` — not `0`, not a sentinel. `SUM`
  skips them and the page states that the total is a floor; a cache hit reports `cached` with zero
  tokens rather than re-billing the original call; the heuristic provider declares `unavailable` and
  keeps its local count where it can never be summed into a cost.
- **Lesson.** `0` and "we were not told" are different measurements. Codifying one as the other turns a
  missing fact into a false one, and the false one is what gets quoted.

### Two more to have ready

- **Hybrid retrieval loses to BM25 at Hit@5** (0.9661 vs 0.9831). Reported, not tuned: picking fusion
  weights to win on 59 queries is fitting the corpus, and an interviewer can tell a good number from an
  honest one.
- **A 375 px table pushed its own columns off screen** while every component test passed, because jsdom
  has no layout engine. Found in a screenshot, fixed with a card layout below `sm`, now guarded by an
  overflow spec at 375 / 768 / 1440.

## 9. Résumé bullets

Four role variants, each in Chinese and English. Each bullet carries an action, a technical detail and
a result — no 熟悉 / 了解 / 掌握, and no adjective standing in for evidence.

### 9.1 软件工程师（后端 / 全栈）— 中文

- 从 0 设计并实现全栈 AI 系统的分层架构：AI 核心禁止依赖 Web 框架与 ORM，由 `check_layering.py` 在 CI 中强制守卫。
- 实现 FastAPI + PostgreSQL 后端：统一响应信封与错误码契约、跨租户越权返回 404、九次迁移在 SQLite 与 PostgreSQL 上均可执行。
- 建立四层测试与 6 个 CI 作业：1,385 项自动化测试、45 条真实浏览器流程、核心域覆盖率 92.5%。
- 把可观测性做成产品面：模型调用逐次计量、失败运行由独立 journal 落盘、成本区分「已上报」与「不可知」。

### 9.2 Software Engineer (backend / full-stack) — English

- Designed and built the layered architecture of a full-stack AI system, in which the Python AI core is
  forbidden — by an enforced script — from importing the web framework or the ORM.
- Implemented the FastAPI + PostgreSQL backend: one response envelope, a documented error-code
  contract, cross-tenant reads returning `404`, and nine Alembic migrations that run on both SQLite and
  PostgreSQL.
- Built a four-layer test strategy and six CI jobs: **1,385 automated tests**, **45 real-browser flows**,
  **92.5%** core-domain coverage.
- Made observability a product surface: per-call metering, a failure journal that survives the request's
  rollback, and cost accounting that separates _reported_ from _unknown_.

### 9.3 AI 应用工程师 — 中文

- 设计断言验证门禁：确定性规则先行、模型只判「有无支撑」、置信度由版本化算术给出，伪造数字通过率 0.000。
- 构建混合检索（BM25 + 向量 + RRF）并纳入评测：Hit@1 0.8475、Hit@5 0.9661、MRR 0.9011。
- 建立 4 套评测（242 例、41 指标、逐项阈值与理由），实测 macro F1 0.8481，不安全通过率降至 5.00%。
- 把置信度校准纳入被比较的指标集（ECE 0.0316、Brier 0.0904），让校准漂移能在 diff 与门禁中出现。

### 9.4 AI Application Engineer — English

- Designed the claim gate: deterministic rules run first, the model may only judge support, confidence
  comes from arithmetic — fabricated-number acceptance **0.000**.
- Built hybrid retrieval (BM25 + vector + RRF) and put it under evaluation: **Hit@1 0.8475 · Hit@5
  0.9661 · MRR 0.9011**, with keyword-only retrieval published as _better_ rather than tuned away.
- Built four evaluation suites (**242 cases, 41 metrics**, each with a threshold and a written
  rationale): evidence macro F1 **0.8481**, unsafe acceptance down to **5.00%**.
- Wired calibration into the compared metric set (**ECE 0.0316 · Brier 0.0904**) so a drift appears in a
  diff or fails a gate, instead of living in a side artefact nobody reads.

### 9.5 解决方案 / 产品工程师 — 中文

- 定义完整产品闭环：材料导入 → 证据图谱 → JD 分析 → 可解释匹配 → 断言验证 → 模拟面试 → 投递看板 → 求职分析。
- 把不可信的 AI 变成可核对的数字：每个指标给出算法版本与口径，接口缺失时页面显示「不可用」而非替代数据。
- 交付可演示的产品与文档体系：README、演示脚本、质量文档、部署指南、发布记录，所有数字可追溯到产物。
- 完成公开发布准备：GitHub 仓库与 About/Topics、发布候选 tag、逐项列明「已验证 / 未验证」的发布记录。

### 9.6 Solution / Product Engineer — English

- Defined the product loop end to end: material → evidence graph → JD analysis → explainable match →
  claim validation → adaptive interview → application board → analytics.
- Turned untrustworthy AI output into checkable numbers: every metric ships the definition and
  algorithm version it was computed with, and a page that cannot get data shows nothing rather than a
  substitute.
- Delivered a demonstrable product plus its documentation set (README, demo script, quality document,
  deployment guide, release record), with every figure traceable to an artefact.
- Prepared the public release: GitHub repository with description and topics, a release-candidate tag,
  and a release record that names each item as verified or not verified.

### 9.7 嵌入式软件工程师（CareerForge 作为软件广度补充）— 中文

- 独立完成跨栈软件项目以补充嵌入式背景：Python/FastAPI 后端 + Next.js 前端 + PostgreSQL 数据层。
- 用工程规范约束自己：分层依赖守卫、单文件 500 行上限、设计令牌检查、pre-commit 与 6 个 CI 作业。
- 以 1,385 项自动化测试与 45 条真实浏览器流程守住回归（桌面 27 条、移动 18 条）。
- 在发布收口中定位真实缺陷：AI 配额把读请求计入调用、CORS 只在浏览器暴露、报告来源标记恒为 true。

### 9.8 Embedded Software Engineer (CareerForge as engineering breadth) — English

- Built a cross-stack software project alongside my firmware background: Python/FastAPI backend,
  Next.js frontend, PostgreSQL data layer.
- Held myself to explicit engineering rules: an enforced layering guard, a 500-line file ceiling,
  design-token checks, pre-commit hooks and six CI jobs.
- Guarded regressions with **1,385 automated tests** and **45 real-browser flows** (27 desktop, 18
  mobile).
- Found and fixed real defects during release: an AI quota that charged page reads, CORS failures only a
  browser could expose, a provenance flag that was always true, and a migration that had never run on
  PostgreSQL.

## 10. Role variants (project descriptions)

### 10.1 Software Engineer — 150 字

> CareerForge AI 是一个从 0 到发布候选的 AI 求职操作系统。我独立完成架构与实现：Python AI 核心不依赖
> Web 框架与 ORM（由脚本守卫强制），FastAPI 提供统一响应信封与错误码契约，PostgreSQL 承载 32 张表与
> 九次迁移，Next.js 15 负责 8 个产品页面。工程侧建立四层测试策略与 6 个 CI 作业，1,385 项自动化测试
> 覆盖核心域 92.5%，另有 45 条真实浏览器流程与可访问性门禁。

### 10.2 Software Engineer — 300 字

> CareerForge AI 是一个 Evidence-Driven 的 AI 求职操作系统，我从零设计并实现到发布候选（v1.0.0-rc.1）。
> 架构上刻意分层：Python AI 核心（编排器、混合检索、证据图谱、评分）**不允许** import Web 框架或 ORM，
> 由 `check_layering.py` 在 CI 里强制，因此它可以独立测试与评测；FastAPI 层负责统一响应信封、错误码契约
> 与限流；PostgreSQL 16 承载 32 张表，九次 Alembic 迁移在 SQLite（本地零依赖路径）与 PostgreSQL（CI 与
> 生产）上都可执行 —— 后者正是发布阶段被 CI 发现有问题、随后修好的地方。
>
> 工程侧的重点是「可验证」：四层测试策略按「哪一层才能看到这类缺陷」分配——纯算术、真实契约、渲染规则、
> 真实浏览器；1,385 项自动化测试覆盖核心域 92.5%，45 条 Playwright 流程覆盖桌面与移动（含 axe 0 critical
> / 0 serious）。发布前用 7 步原生链路验证（全新数据库 → 迁移 → 两次 seed → 生产模式 API → 构建前端 →
> 25 项契约冒烟 → 重启），并在 CI 中把整套 compose 拓扑真正拉起来跑浏览器套件。可观测性是产品面：每次
> 模型调用落库、失败运行由独立 journal 落盘、成本区分「已上报」与「不可知」。

### 10.3 AI Application Engineer — 150 字

> CareerForge 的核心不是「调用 LLM」，而是**不信任 LLM**：模型只允许判断「证据是否支撑这句话」，数字全部
> 由确定性算术产生。规则阶段先拦下无据的量化断言，混合检索（BM25 + 向量 + RRF）在用户自己的证据上取证，
> 最后按版本化公式给出置信度。我用 60 例人工编写的对抗语料评测它：macro F1 0.8481、伪造数字通过率 0.000、
> 不安全通过率 5.00%（目标 2%，未达标且公开）。4 套评测、242 例、41 个带阈值与理由的指标，全部可在零 API
> key 下复现。

### 10.4 AI Application Engineer — 300 字

> CareerForge 的出发点是：AI 写简历最容易造成的伤害不是语句不通，而是**看起来很可信但无法证实的断言**。
> 因此我把生成变成一条被门禁约束的流水线：确定性规则先跑（无据的量化断言、无支撑的最高级措辞、图谱里完全
> 不存在的技术），混合检索（BM25 + 向量 + RRF）在候选人自己的证据上取证，模型只被允许回答「这些证据是否
> 支持这句话」，置信度则由版本化公式计算——模型永远不产生数字。
>
> 评测是项目的一半：4 套标注套件、242 个用例、41 个指标，每个指标都带阈值、严重级别与书面理由（漏掉门禁
> 就红，漏掉报告项就打印并继续）。第一版数据集其实是「用规则生成标签再测规则」，support recall 漂亮到
> 100% 却毫无意义；换成 60 例人工对抗语料后真实数字是 0.0000，并暴露了两个真实策略缺陷。修复后 macro F1
> 0.8481、伪造数字通过率 0.000、不安全通过率从 10% 降到 5.00%（目标 2%，未达标，缺口公开）。校准也纳入
> 比较集（ECE 0.0316、Brier 0.0904），可观测性覆盖每次调用的 token、延迟、成本与降级状态——用量未上报时
> 记 `null` 而不是 0。

### 10.5 Solution / Product Engineer — 150 字

> CareerForge AI 把「AI 给的职业建议凭什么可信」这个问题做成了一条产品闭环：材料导入 → 证据图谱 →
> JD 分析 → 可解释匹配 → 断言验证 → 自适应模拟面试 → 投递看板 → 求职分析。设计原则是**不给读者看不出来源
> 的数字**：每个指标随算法版本与口径一起出现，接口拿不到数据时页面显示「不可用」而不是替代值。交付物包括
> 可演示产品、README、演示脚本、质量文档、部署指南，以及一份逐项说明「验证了什么、没验证什么」的发布记录。

### 10.6 Solution / Product Engineer — 300 字

> CareerForge AI 解决的是一个具体而常见的问题：AI 让一份漂亮的简历变得廉价，于是「能被证实」变成了新的稀缺
> 资源。我把它做成了一条完整闭环：材料导入（简历 / GitHub / 手工条目）→ 证据图谱 → JD 智能分析 → 五维可
> 解释匹配 → 断言验证门禁 → 自适应模拟面试 → 投递看板 → 求职分析。产品原则贯穿始终——页面上每个数字都要
> 能说出它来自哪个接口、哪个算法版本、哪个口径；拿不到数据时显示「不可用」，绝不用替代值把空白填满。
>
> 交付上我把它当成一次真实发布来做：可演示的产品、8 个页面、README 与演示脚本、质量文档、部署指南、发布
> 记录；发布记录里逐项列出「已验证」和「未验证」，包括本机没有容器运行时、因此 `docker compose up` 从未
> 执行过这样的事实——这一点随后在 CI 里被补上，并且立刻暴露出一个只在 PostgreSQL 上出现的迁移缺陷。评测同样
> 按产品口径设计：4 套评测、242 例、41 个指标，其中把「不安全通过率」（把无证据的断言判为有证据）单独设为
> 最严格的门禁，因为它正是这个产品存在要防止的错误。

### 10.7 嵌入式岗位的用法

一句话即可：「除了 STM32/FreeRTOS 的无人机飞控项目，我独立做了一个跨栈软件项目 CareerForge AI
（Python/FastAPI + Next.js + PostgreSQL），用来验证自己在软件工程侧的广度：分层架构、数据库迁移、四层测试、
CI 与发布流程。」把嵌入式深度的话头留给无人机项目。

## 11. Links and current state

|                     |                                                                                                                                                                                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Repository          | https://github.com/meminehobe24435-cmyk/careerforge-ai                                                                                                                                                                                           |
| Release             | `v1.0.0-rc.1` — tagged, pushed, and the reason it is not `v1.0.0` is written down                                                                                                                                                                |
| About / Topics      | description + 16 topics set (ai, llm, rag, agents, career, resume, job-search, interview, nextjs, fastapi, typescript, python, postgresql, pgvector, evaluation, observability)                                                                  |
| Live demo           | **none yet.** No hosting account or credential is available to this machine, so no URL is published and none is faked. `docs/DEPLOYMENT.md` §2 is the exact procedure; CI now runs the whole stack in containers as the closest available proof. |
| Offline demo assets | `assets/evidence-graph-demo.gif` (0.46 MB) + the four screenshots in §12.1                                                                                                                                                                       |
| What is verified    | local: 1,385 tests · 45 browser flows · 4/4 eval gates · 92.5% core coverage · release proof 7/7                                                                                                                                                 |
| What is not         | a public URL, and a real-provider (DeepSeek/OpenAI) evaluation run                                                                                                                                                                               |

## 12. Presentation kit

### 12.1 Four screenshots (and only four)

Eighteen exist in `assets/screenshots/`; a résumé or portfolio should use four, in this order, all at
`-1440.png`:

1. `evidence-graph-1440.png` — the core idea, visible at a glance
2. `jobs-1440.png` — JD analysis with the three-level skill tree and the score breakdown
3. `validator-1440.png` — a supported claim beside a fabricated one, with the reasons
4. `ai-runs-1440.png` — the engineering proof: real runs, steps, model calls, latency

### 12.2 Five-slide deck outline (content only)

| Slide | Title                    | Content                                                                                                                  |
| ----- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| 1     | Problem + product        | "A beautiful résumé is free; proof is not." The loop diagram (§3), one screenshot                                        |
| 2     | Architecture             | The layer diagram (§4) + the rule that the AI core cannot import the web framework                                       |
| 3     | Evidence graph           | One candidate's graph: node → evidence → the confidence factors that produced the number                                 |
| 4     | Evaluation & reliability | The 4-suite/242-case/41-metric table, macro F1, unsafe support 5% **and the 2% target it misses**, calibration ECE/Brier |
| 5     | Engineering lessons      | Three of the six stories in one line each — the self-referential benchmark, the quota that charged reads, `null` ≠ `0`   |

### 12.3 If the demo fails in the room

Do **not** debug a cloud service for eight minutes. Say this, then move:

> "This demo is deployed, but I also keep the product reproducible locally. Let me show you the recorded
> Evidence Graph interaction and then walk through the underlying code."

Then play `assets/evidence-graph-demo.gif`, open [`CODE_TOUR.md`](./CODE_TOUR.md), and start from the
claim validator. The offline path also includes a two-command local start (README quick start for the
zero-dependency path, `docs/DEPLOYMENT.md` §1 for compose) and the four screenshots above, so a
presentation never depends on a network.

### 12.4 One-line project descriptions

**English (GitHub / CV):**

> Evidence-driven AI career OS for job analysis, verifiable resume claims, adaptive interviews and career intelligence.

**中文（BOSS / 牛客 / 校招系统）：**

> 证据驱动的 AI 求职操作系统：把简历、项目与代码整理成证据图谱，用可解释的匹配与断言验证，让每一句简历都有据可查。

## 13. Reproducing every number here

```bash
python evals/run.py                      # 4 suites, 242 cases, 41 metrics → reports/eval-report.json
python scripts/coverage_report.py        # core-domain coverage → reports/coverage-summary.md
python scripts/release_proof.py          # 7-step native proof → reports/release-proof.json
pytest packages/ai apps/api evals -q     # 975 Python tests
pnpm --filter @careerforge/web test      # 365 component tests
pnpm --filter @careerforge/web test:e2e  # 45 browser flows (desktop + mobile)
```

The published figures in §7 come from the release-candidate run recorded in `reports/`. If you re-run
these and a number differs, **the new number is the true one** and this file is out of date — that is
the entire point of quoting the artefact rather than the prose.
