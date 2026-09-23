# Architecture Decision Records (ADR)

> 本文档记录 CareerForge AI 的**关键工程决策**：每个决策包含背景、选择、被否决的替代方案与后果。
>
> 面试友好提示：ADR 的价值不在"选了什么"，而在**"为什么这样选、代价是什么、什么时候该换"**。每一条都值得在面试中被追问。

| 编号                                                               | 决策                                    | 状态        | 阶段 |
| ------------------------------------------------------------------ | --------------------------------------- | ----------- | ---- |
| [ADR-001](#adr-001-monorepo-结构pnpm-workspaces--turborepo)        | Monorepo 结构                           | ✅ Accepted | 1    |
| [ADR-002](#adr-002-nextjs-15-app-router--rsc)                      | Next.js 15 App Router + RSC             | ✅ Accepted | 1    |
| [ADR-003](#adr-003-fastapi--pydantic-v2-作为后端框架)              | FastAPI + Pydantic v2                   | ✅ Accepted | 1    |
| [ADR-004](#adr-004-postgresql--pgvector-为主sqlite-为降级路径)     | PostgreSQL + pgvector 为主，SQLite 降级 | ✅ Accepted | 1    |
| [ADR-005](#adr-005-evidence-graph-用邻接表而非图数据库)            | Evidence Graph 用邻接表                 | ✅ Accepted | 3    |
| [ADR-006](#adr-006-评分必须确定性llm-不参与数值)                   | 评分确定性化                            | ✅ Accepted | 5    |
| [ADR-007](#adr-007-自研-agent-orchestrator-而非-langgraph)         | 自研 Agent Orchestrator                 | ✅ Accepted | 1    |
| [ADR-008](#adr-008-混合检索--rrf-融合)                             | 混合检索 + RRF                          | ✅ Accepted | 3    |
| [ADR-009](#adr-009-多-provider-抽象与-heuristic-provider-一等公民) | Provider 抽象 + Heuristic 一等公民      | ✅ Accepted | 1    |
| [ADR-010](#adr-010-队列端口本地进程内--生产-redis)                 | 队列端口（进程内 / Redis）              | ✅ Accepted | 1    |
| [ADR-011](#adr-011-用-text--check-而非-postgresql-原生-enum)       | text + CHECK 代替原生 enum              | ✅ Accepted | 1    |
| [ADR-012](#adr-012-prompt-外置并版本化)                            | Prompt 外置版本化                       | ✅ Accepted | 11   |
| [ADR-013](#adr-013-把置信度公式写成数据库-check-约束)              | 置信度公式落到 DB 约束                  | ✅ Accepted | 3    |
| [ADR-014](#adr-014-防幻觉门禁规则层先于-llm-层)                    | 门禁：规则先于 LLM                      | ✅ Accepted | 6    |
| [ADR-015](#adr-015-自建-jwt-认证而非托管-auth-服务)                | 自建 JWT 认证                           | ✅ Accepted | 1    |
| [ADR-016](#adr-016-流式用-sse-而非-websocket)                      | 流式用 SSE                              | ✅ Accepted | 7    |
| [ADR-017](#adr-017-游标分页)                                       | 游标分页                                | ✅ Accepted | 1    |
| [ADR-018](#adr-018-图可视化用-react-flow看板用-dnd-kit)            | React Flow + dnd-kit                    | ✅ Accepted | 3    |
| [ADR-019](#adr-019-设计令牌用-css-变量--tailwind-v4禁止硬编码色值) | 设计令牌变量化                          | ✅ Accepted | 1    |
| [ADR-020](#adr-020-种子数据必须自洽并带断言)                       | 种子数据自洽断言                        | ✅ Accepted | 2    |
| [ADR-021](#adr-021-统一响应信封--requestid)                        | 统一信封 + requestId                    | ✅ Accepted | 1    |
| [ADR-022](#adr-022-ai-核心库不依赖-web-框架)                       | AI 核心库零框架依赖                     | ✅ Accepted | 1    |

---

## ADR-001 Monorepo 结构（pnpm workspaces，Turborepo 暂缓）

**背景**：项目包含前端（Next.js）、后端（FastAPI）、Python AI 核心库、共享类型与 UI 包，前后端类型契约必须保持一致。

**决策**：单一仓库，`apps/{web,api}` + `packages/{ai,shared,ui,config}`；TS 侧用 **pnpm workspaces** 管理，任务编排用 `pnpm -r` / `pnpm --parallel`；Python 侧 `packages/ai` 作为可独立安装的包，由 `apps/api` 以路径依赖引入。

**Turborepo 暂缓（v1.0 不使用）**：Turborepo 的核心价值是**跨包任务缓存与增量构建**。当前仓库只有 1 个可构建的前端应用，任务图几乎是线性的，引入它只会增加一个二进制依赖与一份配置文件，收益为零。触发引入的条件写在这里：**当 `packages/*` 中出现第 2 个需要独立构建产物的包，或 CI 构建时间超过 3 分钟时**，再评估引入。这是有意的"延迟决策"，而不是遗漏。

**被否决**：

- 多仓库（polyrepo）：类型契约与版本同步成本高，作品集场景下无收益。
- 把 AI 代码直接塞进 `apps/api`：无法独立测试与评测，违背"AI 核心可独立运行"的目标。
- 现在引入 Turborepo：为工具而工具，增加无收益的复杂度。

**后果**：

- ✅ 契约漂移可通过 CI 检测（OpenAPI 生成 + diff）
- ✅ `python evals/run.py` 可在不启动 API 的情况下跑评测
- ✅ 依赖树更小、安装更快、失败面更少
- ⚠️ 需要维护两套包管理（pnpm + pip），文档必须写清
- ⚠️ 任务并行度依赖 pnpm 自身能力，缺少细粒度缓存

---

## ADR-002 Next.js 15 App Router + RSC

**背景**：需要 SSR 首屏性能、深色主题无闪烁、大量数据密集型页面，同时要有强交互（图谱、看板、流式）。

**决策**：Next.js 15 App Router。Server Components 负责数据获取与首屏；Client Components 只在需要交互处（图谱、看板、图表、流式）使用；数据获取用 TanStack Query（客户端）与 RSC fetch（服务端）分工。

**被否决**：

- Vite + React SPA：首屏与 SEO 弱，主题闪烁难处理，作品集观感低一档。
- Pages Router：App Router 的布局嵌套与流式更适配本项目。

**后果**：

- ✅ 首屏 LCP 目标可达 ≤ 1.5s；主题在服务端注入，无 FOUC
- ⚠️ 必须清楚划分 Server/Client 边界，否则把交互组件误放进 RSC 会报错（文档与 lint 规则约束）

---

## ADR-003 FastAPI + Pydantic v2 作为后端框架

**背景**：后端是 AI 密集型 API，需要强类型请求/响应、自动 OpenAPI、异步 I/O、快速迭代。

**决策**：FastAPI + Pydantic v2。Pydantic 同时承担三重职责：HTTP 契约、AI 结构化输出的校验器、领域对象。SQLAlchemy 2.0 async 做持久化，Alembic 做迁移。

**被否决**：

- Django：重、同步生态为主、AI 场景下异步支持不自然。
- Flask：无内建校验与 OpenAPI，样板代码多。
- Node/NestJS 全栈：可与前端共享类型，但 Python 在 AI 生态（pydantic、numpy、PDF 解析）上优势明显。

**后果**：

- ✅ 一个 Schema 定义，同时约束 API 与 LLM 输出（**这是防幻觉的结构性基础**）
- ✅ `/docs` 自动生成，演示时可直接展示 API
- ⚠️ Pydantic v2 与 v1 语法差异需注意（全项目统一 v2）

---

## ADR-004 PostgreSQL + pgvector 为主，SQLite 为降级路径

**背景**：需要关系数据 + 向量检索 + 全文检索。但开发环境**可能没有 Docker/PostgreSQL**（本项目初始环境即如此）。

**决策**：定义 `VectorStore` 与 `SearchBackend` 端口。

- 生产：PostgreSQL 16 + pgvector（HNSW）+ tsvector/GIN
- 本地：SQLite + numpy 精确余弦 + FTS5
- 通过 `db/compat.py` 的 TypeDecorator 让**同一套 ORM 模型**跑在两种后端

**被否决**：

- 只支持 Postgres：无 Docker 环境无法运行，项目直接残废。
- 用 Chroma/FAISS 作为唯一向量库：多一个独立进程与存储，且失去"关系 + 向量同库事务一致"的优势。
- ORM 层写两套：维护成本翻倍。

**后果**：

- ✅ 零依赖可跑（`pnpm dev` + `uvicorn`），演示环境不可控时依然稳
- ✅ CI 同时跑 SQLite 与 Postgres，暴露方言漂移
- ⚠️ 必须避免 Postgres 专有语法泄漏到通用查询；复杂聚合需在服务层而非 SQL 中完成
- ⚠️ SQLite 端向量检索是 O(n) 精确搜索，超过 5 万向量需告警（文档写明）

---

## ADR-005 Evidence Graph 用邻接表而非图数据库

**背景**：Evidence Graph 是产品核心，需要多跳溯源查询（Claim → Evidence → Source）。

**决策**：用两张表（`evidence` + `evidence_links`）实现多态邻接表，配合 `(user_id, from_type, from_id, relation)` 与 `(user_id, to_type, to_id, relation)` 双向索引。子图查询在服务层做 2–3 跳遍历，并限制返回节点数。

**被否决**：

- Neo4j：引入独立存储与运维成本；单用户图谱规模（≤ 数千节点）远未到图数据库的必要门槛；且会失去与业务数据的事务一致性。
- 递归 CTE 全量查询：深度不可控，性能风险高。

**后果**：

- ✅ 与业务数据同库同事务，证据与业务实体永不脱节
- ✅ 部署组件数不增加
- ⚠️ 多态外键**无法建真实外键约束** → 用应用层完整性校验 + 定期 `integrity_check` 任务兜底
- ⚠️ 若未来需要复杂图算法（中心性、社区发现），需要重新评估

---

## ADR-006 评分必须确定性，LLM 不参与数值

**背景**：AI 产品最容易失去信任的地方是"分数不可复现"——同一份简历两次得到 84 和 91。且评测与回归测试需要稳定的数值。

**决策**：Job Match（5 维加权）、Evidence Confidence（5 因子）、Profile Strength、Gap Priority **全部由确定性算法计算**。LLM 仅用于：文本抽取、叙述生成（"为什么这条是强项"）、面试评分中的定性维度。

**被否决**：

- 让 LLM 直接输出匹配分：不可复现、无法解释、无法回归测试、易被 prompt 影响漂移。
- 纯规则无 LLM：抽取质量差，且无法生成自然语言解释。

**后果**：

- ✅ 分数可复现（有专门测试断言两次运行完全一致）
- ✅ "Why 86?" 能展示真实公式，而非事后编造解释
- ✅ 权重可配置可调优，且有评测集支撑
- ⚠️ 规则需要持续维护（新增技能类别、新的 level 映射）

---

## ADR-007 自研 Agent Orchestrator 而非 LangGraph

**背景**：需要多 Agent 工作流编排，具备重试、降级、缓存、超时、追踪能力。

**决策**：自研轻量编排器（约 400 行以内）：`Step`（输入/输出 Schema + 超时 + 重试 + fallback + cache_ttl）+ `Workflow`（显式 DAG）+ `RunContext` + 步骤级追踪落库。

**被否决**：

- LangGraph：抽象层厚，调试困难；其 checkpoint/state 模型与本项目"步骤即追踪单元"的模型重复；且会把可观测性绑在框架内部结构上。
- LangChain 全家桶：为用而用，依赖重、抽象泄漏多。
- 纯顺序函数调用：无重试/缓存/追踪的统一实现，代码会散落重复逻辑。

**后果**：

- ✅ 每个步骤是纯函数，可单测、可快照、可 mock
- ✅ 追踪结构与数据库表一一对应，AI Runs 页面天然有数据
- ✅ 依赖轻，安装快，无版本冲突
- ⚠️ 复杂条件分支/循环需自行表达能力（当前工作流形态简单，够用）
- ⚠️ 无社区生态支持，需要自己写文档（本项目已写）

---

## ADR-008 混合检索 + RRF 融合

**背景**：求职场景的查询充满**精确技术名词**（`STM32F407`、`CANopen`、`heap_4`），纯向量检索会把这些泛化掉；纯关键词又无法处理"多任务实时调度"这类语义查询。

**决策**：语义检索（pgvector 余弦）+ 关键词检索（tsvector / FTS5）+ 元数据过滤三路并行，用 **Reciprocal Rank Fusion**（`k=60`）融合：`score = Σ 1/(k + rank_i)`。

**被否决**：

- 纯向量：技术名词召回差，幻觉风险高。
- 加权求和原始分数：不同通道分数不可比，需归一化，脆弱。
- 仅用交叉编码器重排：延迟高，成本高（列为 v1.1 可选增强）。

**后果**：

- ✅ 无需跨通道分数归一化，工程稳健
- ✅ 每条结果可标注命中通道，支撑可解释 UI
- ⚠️ 需维护两套索引，写入时双写（有测试保证一致）

---

## ADR-009 多 Provider 抽象与 Heuristic Provider 一等公民

**背景**：项目必须能在**没有任何 API Key** 的环境中完整运行（面试官本机、CI、离线演示），同时生产环境应支持 DeepSeek/OpenAI/本地 Ollama。

**决策**：定义 `LLMProvider` 协议（`chat` / `stream` / `embed` / `structured_output`），实现 DeepSeek / OpenAI / Ollama / **Heuristic** 四个 provider，外加 `Cached` / `Routed` / `Resilient` 三个装饰器。Heuristic provider 用规则 + 模板 + TF-IDF 排序，产出**结构合法**（通过 Pydantic 校验）的响应。

**被否决**：

- 只支持一个厂商：换厂商即改代码，且无 Key 就完全不可用。
- 无 Key 时直接返回空结果：产品演示价值归零。

**后果**：

- ✅ 零 Key 全功能可跑，CI 有 `no-llm` 任务常驻验证
- ✅ 评测可复现（heuristic 完全确定）
- ✅ 降级时 UI 显式标注（`degraded: true`），诚实且不假装
- ⚠️ Heuristic provider 需要为每种输出 Schema 写规则，是一笔实打实的额外工作量
- ⚠️ 必须防止"降级后静默给出低质量结果"——用 UI 徽章与 `agent_runs.status=degraded` 暴露

---

## ADR-010 队列端口：本地进程内 / 生产 Redis

**背景**：简历解析、嵌入、GitHub 分析是长任务，不应阻塞 HTTP 请求。但开发环境可能没有 Redis。

**决策**：定义 `QueuePort`（`enqueue` / `cancel` / `status`）。本地用 `InProcessQueue`（asyncio 任务 + `background_jobs` 表），生产用 Redis 后端 worker。**任务状态一律落 `background_jobs` 表**，因此两种实现的可观测性完全一致。

**被否决**：

- 只用 FastAPI `BackgroundTasks`：进程重启即丢失任务，无重试、无状态查询，前端无法做进度条。
- 强依赖 Celery：重依赖 + 需要 broker，无 Redis 时不可用。

**后果**：

- ✅ 无 Redis 也能有真实的任务进度 UI（SSE 从 `background_jobs` 读）
- ✅ 迁移到生产仅换 Port 实现
- ⚠️ 进程内实现的并发与多 worker 语义不同，文档须明确"本地仅单进程语义"

---

## ADR-011 用 text + CHECK 而非 PostgreSQL 原生 ENUM

**背景**：状态字段多（claim status、application status、evidence kind 等）。

**决策**：统一 `text` + `CHECK` 约束，ORM 层用 Python `Enum` 做类型安全。

**被否决**：

- 原生 `ENUM`：新增枚举值需要 `ALTER TYPE`，在迁移与回滚中麻烦；跨方言（SQLite）不兼容。

**后果**：

- ✅ SQLite/Postgres 一致；迁移简单（改 CHECK 即可）
- ✅ 应用层仍享受强类型（Pydantic + Python Enum）
- ⚠️ 约束变更需要显式迁移（掉约束 + 加约束），不能靠 autogenerate

---

## ADR-012 Prompt 外置并版本化

**背景**：Prompt 是核心资产，散落在代码里无法 review、无法 diff、无法归因"这次结果变差是哪个 Prompt 改的"。

**决策**：所有 Prompt 以 Markdown 存放于 `prompts/`，含 YAML front-matter（`name` / `version` / `variables` / `notes`）。启动时同步到 `prompt_versions` 表（内容 SHA256 变化即新增版本）。每次 AI 调用记录所用 `prompt_version`。

**被否决**：

- Prompt 写死在代码字符串：无法归因、无法 A/B。
- 外部 Prompt 管理平台（LangSmith 等）：引入外部依赖与账号，作品集场景过重。

**后果**：

- ✅ Prompt 变更可 diff、可回滚、可在 UI 中查看
- ✅ `agent_runs` 与 `llm_calls` 能精确归因到版本
- ⚠️ 需要渲染引擎处理变量与条件块（自研，约 80 行）

---

## ADR-013 把置信度公式写成数据库 CHECK 约束

**背景**：置信度是产品信任的地基。若某条代码路径绕过公式写入"好看的"数字，产品承诺即被破坏，且很难发现。

**决策**：在 `evidence` 表加 `CHECK` 约束，断言 `confidence` 等于五因子加权公式的结果（容差 0.002）。

**被否决**：

- 只在应用层计算：无强制力，回归时可能被悄悄破坏。
- 生成列（`GENERATED ALWAYS AS`）：更严格，但让"人工调权/历史数据迁移"变得困难，且 SQLite 兼容性差。

**后果**：

- ✅ **把产品承诺编译进数据库**，任何违规写入直接失败
- ✅ 面试可讲："我们不只写在文档里，数据库会拒绝违规数据"
- ⚠️ 权重调整需要迁移（DROP + ADD 约束）；这是有意的摩擦
- ⚠️ 浮点精度需固定 `numeric(4,3)` 与容差，已在文档与测试中明确

---

## ADR-014 防幻觉门禁：规则层先于 LLM 层

**背景**：LLM 对"提升 70%"这类量化断言往往倾向于"合理想象"，即使证据里没有。

**决策**：Claim 验证按固定顺序执行：

1. **规则层**（确定性）：数字/倍数/绝对化措辞检测 → 若断言含量化数字而证据集中无任何量化支撑，直接判 `UNSUPPORTED`/`CONTRADICTED`，**不进入 LLM**。
2. **检索层**：混合检索取 Top-K 证据。
3. **LLM 层**：仅在规则未否决时做语义判定与安全改写。
4. **门禁层**：`confidence ≥ 0.75 且独立来源 ≥ 2` 才允许写入简历。

**被否决**：

- 完全交给 LLM 判断：不可靠、不可复现、可被巧妙的措辞绕过。
- 完全用规则：无法处理"参与无人机项目开发"这类需要语义映射的软性断言。

**后果**：

- ✅ 最危险的幻觉类型（伪造数字）被**确定性**拦截，有专门评测集断言 100% 拦截
- ✅ 规则触发原因可在 UI 中展示（用户学到"为什么不能这么写"）
- ⚠️ 规则需持续扩充（新的话术模式、中英文差异）

---

## ADR-015 自建 JWT 认证而非托管 Auth 服务

**背景**：需要登录与 Demo 体验。候选方案：Supabase Auth / Auth.js / 自建。

**决策**：自建 JWT（bcrypt + HS256 + refresh 轮换）。前端仅做 token 存储与刷新。

**被否决**：

- Supabase Auth：引入外部服务依赖，离线/无网络环境不可用，且 Demo 账号预置数据与外部用户体系的绑定增加复杂度。
- Auth.js 全流程：Next.js 侧方便，但后端是 FastAPI，仍需自建 token 校验，收益减半。
- 完全不做认证：无法演示多租户隔离（`user_id` 作用域是整个安全设计的基础）。

**后果**：

- ✅ 零外部依赖，离线可跑，Demo 登录语义完全可控
- ✅ 可演示资源级授权与 `404` 防泄露策略
- ⚠️ 需自行处理 token 轮换、吊销、密码强度等（范围受控，已实现最小安全集）
- ⚠️ 不适用于真正的生产多租户（README 的 Limitations 会写明）

---

## ADR-016 流式用 SSE 而非 WebSocket

**背景**：面试对话与简历生成需要流式输出；任务进度也需要推送。

**决策**：统一使用 SSE（`text/event-stream`），事件类型 `stage` / `delta` / `result` / `error`。

**被否决**：

- WebSocket：双向能力当前用不上；需要额外连接管理、心跳、鉴权握手；在 Serverless/反向代理环境下运维复杂。
- 纯轮询：体验差（首 token 延迟高）、请求量大。

**后果**：

- ✅ 单向流式完全够用，实现简单，可用 `curl` 演示
- ✅ 与 HTTP 中间件（认证、限流、requestId）自然复用
- ⚠️ 代理需关闭缓冲（`X-Accel-Buffering: no`），部署文档须写明

---

## ADR-017 游标分页

**背景**：列表端点（证据、job runs、AI runs）数据量大且持续增长。

**决策**：主列表用游标分页（`(created_at, id)` 复合游标，Base64 编码），仅在需要跳页的管理场景用 offset。

**被否决**：全量 offset 分页 —— 深分页性能差、数据插入导致漂移重复。

**后果**：

- ✅ 深分页稳定且高效
- ⚠️ 前端无法直接跳页（UI 用"加载更多"，这是有意的设计选择）

---

## ADR-018 图可视化用 React Flow，看板用 dnd-kit

**背景**：Evidence Graph 需要自定义节点、交互与性能；投递看板需要拖拽。

**决策**：Graph 用 `@xyflow/react`（自定义节点组件 + 贝塞尔边 + 内置缩放/平移/框选）；看板用 `dnd-kit`（支持键盘拖拽，满足 a11y）。

**被否决**：

- Cytoscape.js：图算法强，但 React 集成与样式定制成本高。
- 自研 Canvas 图谱：开发成本高，交互细节（hit test、缩放、无障碍）难以短期做好。
- react-beautiful-dnd：已停止维护。

**后果**：

- ✅ 自定义节点即 React 组件，可直接复用设计系统
- ✅ dnd-kit 提供键盘与屏幕阅读器支持
- ⚠️ React Flow 在 > 1000 节点时需要虚拟化/聚合策略（已列入 PHASE 3 退出标准）
- ⚠️ **dnd-kit 的键盘支持有个边界，PHASE 8c 实测确认**：自带的
  `sortableKeyboardCoordinates` 只在拖拽起始的那个容器内游走，跨列移动根本到不了目标列——
  而看板存在的意义就是跨列。因此本项目自写坐标解析（`lib/keyboard-coordinates.ts`）：
  以拖拽的当前矩形为原点，取按键方向上最近的 droppable（卡片与列都是 droppable，空列因此可达），
  返回其坐标交给 dnd-kit 重新做碰撞检测。三条边界由 `kanban-keyboard.test.tsx` 固定：
  `→` 换一列、`→→` 换两列（位置累积而非回到起点）、`↓` 列内换位。
- ⚠️ 同一实测的第二个结论：dnd-kit 的键盘移动会被**钳制在滚动祖先的矩形内**，而碰撞检测测量的是
  `DragOverlay` 的包裹节点。两者都让"没有布局的测试环境"（jsdom 全部返回 0×0）产生荒谬结果——
  一次 `→` 会落到第四列。测试必须自带布局，见 `apps/web/src/test/layout.ts`（内含两条踩坑记录）。

---

## ADR-023 工作区包以源码形式被三种运行时消费

**背景**：`packages/shared` 与 `packages/ui` 的 `exports` 直接指向 `src/*.ts`（没有构建步骤）。
同一份源码因此被三种运行时加载：Next 的打包器、Vitest（Vite/esbuild）、以及
`node --experimental-strip-types`（`smoke:api` 契约冒烟脚本直接跑 API 客户端）。

**决策**：允许并在包内使用**显式 `.ts` 扩展名**的 import（`allowImportingTsExtensions: true`，
`noEmit` 前提下合法）。相对路径不再依赖打包器的"省略扩展名"宽容。

**背景中的关键事实**：Node 的 ESM 解析器按字面解析，不会尝试补 `.ts`。于是包内任何**值**导入
（`import type` 会被类型擦除，不受影响）在冒烟脚本这条路径上都是 `ERR_MODULE_NOT_FOUND`——
而它在 Next 与 Vitest 里完全正常，属于"只在一条路径上炸"的故障。
PHASE 8c 加 `isApplicationBoard` 守卫时就踩到了这个坑（`guards.ts` 从 `./types` 变成值导入）。

**被否决**：

- 给包加构建步骤（tsc/tsup 产出 `dist`）：多一个构建产物与一层陈旧副本风险，而本项目的
  可调试性恰恰建立在"编辑器里改一行、所有消费方立即看到"之上。
- 在冒烟脚本里手写重复的类型/守卫：契约就不再只有一份，守卫会与服务端漂移。

**后果**：

- ✅ 一份契约源码，三种运行时都能解析；守卫与类型不可能分叉
- ✅ 冒烟脚本用**真实客户端与真实守卫**打真实服务（PHASE 8c 实测 11/11 通过，含看板创建/守卫/
  重排/删除）
- ⚠️ 包内跨文件导入必须带 `.ts` 后缀，这是纪律而非可选项（`allowImportingTsExtensions` 只放行，
  不会自动补全）

---

## ADR-019 设计令牌用 CSS 变量 + Tailwind v4，禁止硬编码色值

**背景**：需要精心打磨的深色主题与可用的浅色主题，且要避免"廉价 AI 紫渐变"的观感。

**决策**：所有颜色/圆角/阴影/动效时长定义为 CSS 变量（`styles/tokens.css`），Tailwind 通过 `@theme` 消费；品牌色定义为"Forge 熔炉橙 + Evidence 证据绿 + Risk 危险红"的语义体系；CI lint 规则禁止组件文件出现硬编码 hex。

**被否决**：

- 直接在 Tailwind 配置里写死色板：主题切换需要重复定义，语义无法表达（不知道 `#34D399` 是"已证实"）。
- CSS-in-JS：与服务端组件/流式渲染配合不佳。

**后果**：

- ✅ 主题切换零成本，语义清晰（`text-evidence` 比 `text-emerald-400` 表意更准确）
- ✅ 视觉一致性由工具保障，而非靠自觉
- ⚠️ 新颜色必须先进 tokens，不能就地取色（有意约束）

---

## ADR-020 种子数据必须自洽并带断言

**背景**：Demo 是作品的门面，但种子数据极易变成"看起来有数据、点进去自相矛盾"的假象（比如 Claim 声称的证据并不存在）。

**决策**：种子脚本生成后执行**自洽性断言**：

1. 每条 `resume_claim` 的证据 id 必须真实存在于 `evidence`
2. 每条 `evidence.confidence` 必须满足置信度公式
3. `agent_runs` 的 token/cost 不得为 0
4. `applications` 的漏斗数字必须与 `application_events` 一致
5. 任意断言失败 → 种子脚本**失败退出**（CI 中使用）

**被否决**：手写静态 JSON 种子 —— 无法保证与业务规则一致，且随 schema 演进迅速腐坏。

**后果**：

- ✅ Demo 数据经得起面试官深挖（点开任何证据都真实存在）
- ✅ 种子脚本本身成为一套集成测试
- ⚠️ 生成耗时略长（可接受，几秒级）

---

## ADR-021 统一响应信封 + requestId

**背景**：前端需要统一的错误处理与用户可见的排障标识；AI 调用链路长，排障必须能串联。

**决策**：所有 API 返回 `{success, data, error, requestId}`；`requestId` 贯通 HTTP → Agent run → LLM calls，并回传响应头。

**被否决**：裸返回数据体（错误靠 HTTP 状态码猜）—— 前端处理分支爆炸。

**后果**：

- ✅ 前端统一拦截器处理成功/失败；错误 UI 能显示 requestId 供复制
- ✅ 排障时可以一条 id 查完整个链路
- ⚠️ 响应体略大（可忽略）

---

## ADR-022 AI 核心库零框架依赖

**背景**：AI 逻辑若与 FastAPI/SQLAlchemy 耦合，就无法独立评测，也无法在 CLI/脚本/未来 Worker 中复用。

**决策**：`packages/ai` 不得 import FastAPI 或 SQLAlchemy ORM。通过**参数注入纯数据对象**（Pydantic 模型 / dataclass）与**端口接口**（`VectorStore`、`LLMProvider`、`EvidenceRepo`）与外界交互。

**被否决**：直接在 Agent 里查数据库 —— 看似省事，但让评测必须起数据库，且无法对 Agent 做纯单测。

**后果**：

- ✅ `evals/run.py` 可在内存中跑完整评测，无需数据库
- ✅ Agent 可被纯单测覆盖（速度极快）
- ⚠️ 需要写一层数据装配代码（Repository → 纯对象），是有意的成本

---

## 附：被否决的替代方案汇总

| 方案                      | 为何不用                                          |
| ------------------------- | ------------------------------------------------- |
| LangChain / LangGraph     | 抽象泄漏、依赖重、可观测性被框架绑架（ADR-007）   |
| Neo4j / 图数据库          | 规模不必要、多一个存储、失去事务一致性（ADR-005） |
| Chroma / FAISS 独立向量库 | 多进程与存储，失去"关系+向量同库"优势（ADR-004）  |
| Supabase Auth             | 外部依赖，离线不可用（ADR-015）                   |
| Celery + Redis 强依赖     | 无 Redis 环境不可运行（ADR-010）                  |
| 让 LLM 直接给匹配分       | 不可复现、不可解释、不可回归测试（ADR-006）       |
| 纯向量 RAG                | 技术名词召回差（ADR-008）                         |
| WebSocket                 | 双向能力用不上，运维复杂（ADR-016）               |
| 纯前端 Mock 后端          | 无法体现系统设计能力，且作品无真实价值            |
| 多仓库拆分                | 契约漂移成本高于收益（ADR-001）                   |

---

**相关文档**：[ARCHITECTURE.md](./ARCHITECTURE.md) · [DATABASE.md](./DATABASE.md) · [ROADMAP.md](./ROADMAP.md)
