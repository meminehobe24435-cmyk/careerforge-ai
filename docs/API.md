# CareerForge AI · API 设计

| 字段     | 值                                                                                       |
| -------- | ---------------------------------------------------------------------------------------- |
| 文档版本 | v1.0                                                                                     |
| Base URL | `http://localhost:8000/api/v1`                                                           |
| 规范     | REST + JSON；流式用 SSE；OpenAPI 3.1 自动生成于 `/api/v1/openapi.json`，交互文档 `/docs` |
| 关联     | [PRD.md](./PRD.md) · [DATABASE.md](./DATABASE.md) · [UI.md](./UI.md)                     |

---

## 1. 通用约定

### 1.1 响应信封（所有端点强制）

```jsonc
// 成功
{ "success": true, "data": { /* ... */ }, "error": null, "requestId": "req_01HQ8Z..." }

// 失败
{ "success": false, "data": null,
  "error": { "code": "VALIDATION_ERROR", "message": "Request validation failed",
             "details": [{ "field": "username", "issue": "required" }] },
  "requestId": "req_01HQ8Z..." }
```

- `requestId` 同时通过响应头 `X-Request-Id` 返回，并写入 `agent_runs.request_id` / `llm_calls.request_id`
- 客户端可在请求头提供 `X-Request-Id` 用于串联（缺失则服务端生成）

### 1.2 认证

| 项     | 约定                                                                                                         |
| ------ | ------------------------------------------------------------------------------------------------------------ |
| 方式   | `Authorization: Bearer <access_token>`（JWT HS256）                                                          |
| 有效期 | access 30 分钟；refresh 7 天（`POST /auth/refresh` 轮换）                                                    |
| Demo   | `POST /auth/demo` 无需凭据，返回 Demo 用户 token                                                             |
| 失败   | 缺失/无效 → `401 UNAUTHORIZED`；权限不足 → `403 FORBIDDEN`；**跨用户资源 → `404 NOT_FOUND`**（不泄露存在性） |

### 1.3 分页

统一游标分页（列表端点）：

```jsonc
// GET /jobs?limit=20&cursor=eyJjcmVhdGVkX2F0IjoiMjAyNi0wMS0wMVQwMDowMDowMFoifQ
{ "success": true, "data": {
    "items": [ /* ... */ ],
    "nextCursor": "eyJjcmVhdGVkX2F0Ijoi..." | null,
    "total": 42 } }
```

- `limit` 默认 20，最大 100
- 支持 `sort`（白名单字段）、`order`（`asc|desc`）、以及各端点声明的过滤参数
- 偏移分页仅在明确需要（如管理页）时用 `?page=&pageSize=`

### 1.4 长任务约定

耗时 > 2s 的操作返回 `202 Accepted`：

```jsonc
{
  "success": true,
  "data": {
    "taskId": "tsk_01HQ...",
    "status": "queued",
    "streamUrl": "/api/v1/tasks/tsk_01HQ.../stream",
  },
}
```

| 操作方式 | 端点                                                                            |
| -------- | ------------------------------------------------------------------------------- |
| 轮询     | `GET /tasks/{id}` → `{status, progress, stage, result, error}`                  |
| 流式     | `GET /tasks/{id}/stream`（SSE，事件 `stage` / `progress` / `result` / `error`） |
| 取消     | `POST /tasks/{id}/cancel`                                                       |
| 幂等     | 请求头 `Idempotency-Key`，24h 内相同键返回首次结果                              |

### 1.5 SSE 事件格式

```
event: stage
data: {"stage":"parsing","label":"Analyzing resume","progress":10}

event: delta
data: {"text":"基于 STM32 "}

event: result
data: {"<最终结构>"}

event: error
data: {"code":"AI_PROVIDER_ERROR","message":"..."}
```

前端必须实现阶段进度 UI（PRD FR-2.4），禁止裸 Spinner。

### 1.6 错误码表

| HTTP | code                      | 含义                                            |
| ---- | ------------------------- | ----------------------------------------------- |
| 400  | `VALIDATION_ERROR`        | 请求体/参数校验失败（含 `details`）             |
| 400  | `UNSUPPORTED_FILE_TYPE`   | 文件类型不在白名单（MIME + 魔数校验失败）       |
| 400  | `FILE_TOO_LARGE`          | 超过 10MB                                       |
| 401  | `UNAUTHORIZED`            | 未认证 / token 失效                             |
| 401  | `TOKEN_EXPIRED`           | access token 过期（客户端应 refresh）           |
| 403  | `FORBIDDEN`               | 权限不足                                        |
| 404  | `NOT_FOUND`               | 资源不存在或不属于当前用户                      |
| 409  | `CONFLICT`                | 唯一约束冲突（如重复导入同 JD）                 |
| 413  | `PAYLOAD_TOO_LARGE`       | 请求体超限                                      |
| 422  | `CLAIM_REJECTED`          | 断言未通过证据门禁（业务语义拒绝，非请求错误）  |
| 429  | `RATE_LIMITED`            | 触发限流（含 `Retry-After`）                    |
| 429  | `AI_BUDGET_EXCEEDED`      | 超出用户日 AI 预算（响应中标注已降级 provider） |
| 502  | `AI_PROVIDER_ERROR`       | 上游 LLM 失败（可重试）                         |
| 502  | `GITHUB_ERROR`            | GitHub API 失败                                 |
| 503  | `DEPENDENCY_UNAVAILABLE`  | DB/Redis/向量库不可用                           |
| 503  | `AI_PROVIDER_UNAVAILABLE` | 全部 provider 不可用（已尝试降级）              |
| 500  | `INTERNAL_ERROR`          | 未预期错误（已记录 requestId）                  |

### 1.7 速率限制

| 端点组                                      | 限制                               |
| ------------------------------------------- | ---------------------------------- |
| 认证（login/register）                      | 10 / 分钟 / IP                     |
| 读端点                                      | 300 / 分钟 / 用户                  |
| 写端点                                      | 60 / 分钟 / 用户                   |
| AI 端点（analyze/match/optimize/interview） | 20 / 分钟 / 用户；单用户日预算护栏 |
| 上传                                        | 20 / 小时 / 用户                   |

响应头：`X-RateLimit-Limit`、`X-RateLimit-Remaining`、`X-RateLimit-Reset`。

### 1.8 降级可观测字段

AI 相关响应统一携带：

```jsonc
"meta": { "provider": "deepseek", "model": "deepseek-chat", "promptVersion": "jd_analysis@v2",
          "degraded": false, "cacheHit": true, "confidence": 0.91, "tookMs": 1420 }
```

`degraded: true` 表示已从主 provider 降级（如 heuristic），前端必须显示提示徽章 —— **不隐瞒降级**。

---

## 2. 端点总览

### 2.1 认证与账户 `/auth` `/me`

> **状态：`/auth/*` 六个端点已实现（PHASE 1/2）**，路由表见 `apps/api/src/careerforge_api/routers/auth.py`。
> **`/me/*` 四个端点尚未实现**（PHASE 14 核对路由表时确认）：`GET/PATCH /me/settings`、
> `GET /me/export`、`DELETE /me` 只有本文档的条目，代码中没有对应路由，调用会得到 `404 NOT_FOUND`。
> 本表把它们标成「未实现」而不是删掉——删掉会让人以为需求不存在；留着不加标记则是文档在说谎。

| 方法   | 路径             | 说明                                         | 认证    |
| ------ | ---------------- | -------------------------------------------- | ------- |
| POST   | `/auth/register` | 注册                                         | —       |
| POST   | `/auth/login`    | 登录                                         | —       |
| POST   | `/auth/demo`     | 一键 Demo 登录                               | —       |
| POST   | `/auth/refresh`  | 刷新 token                                   | refresh |
| POST   | `/auth/logout`   | 注销（吊销 refresh）                         | ✅      |
| GET    | `/auth/me`       | 当前用户                                     | ✅      |
| GET    | `/me/settings`   | 隐私/AI 设置 — 未实现                        | ✅      |
| PATCH  | `/me/settings`   | 更新设置（Local Mode、公开项、预算）— 未实现 | ✅      |
| GET    | `/me/export`     | 导出全部数据（JSON）— 未实现                 | ✅      |
| DELETE | `/me`            | 彻底删除账号与数据 — 未实现                  | ✅      |

```jsonc
// POST /auth/demo  → 200
{
  "success": true,
  "data": {
    "accessToken": "eyJ...",
    "refreshToken": "eyJ...",
    "expiresIn": 1800,
    "user": {
      "id": "uuid",
      "email": "demo@careerforge.ai",
      "displayName": "Alex Chen",
      "isDemo": true,
      "storageScope": "cloud",
    },
  },
}
```

### 2.2 画像与 Career Profile `/profile`

> **状态：`GET /profile` 与 `POST /profile/import` 已实现（PHASE 2b）**，实体表见 §2.2（迁移 `0005`）。
> `POST /profile/import` 接受 `{ text }` 或 `{ documentId }`，是**同步**的：它跑一次确定性的抽取，
> 返回抽取结果与计数，用户正看着屏幕等。`origin` 由调用方声明（`import` / `user_corrected`），
> 服务端不替它猜——这是「抽取结果」与「人工修正」必须可区分的地方。
> **重复导入是更新而非重建**：实体按 `dedupe_key`（学校+学位、公司+职位、项目名）定位同一行并就地
> 更新，因此行的 UUID 不变，图谱中指向它的边继续有效。真被删掉的实体会连同它的边一起删除，
> 而不是留下一个打不开的占位节点。
> 声明技能与证据图谱会**合并**后再参与匹配：只在简历里声明、图谱里没有证据的技能仍是缺口（正确），
> 但图谱里有证据、简历里没写的技能会以 moderate 等级补上——存在证据却报缺口，等于告诉候选人
> 他们缺一个自己明明有的东西。
> 尚未实现：`PATCH /profile`、`/profile/strength`、逐实体 CRUD、`/profile/import/github`（PHASE 10）、
> `deep-dive`（WF-09）。

| 方法             | 路径                                                                   | 说明                                                                                                   |
| ---------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| GET              | `/profile`                                                             | 完整画像（education/experience/project/skill/achievement 聚合，每项带 `origin` 与 `evidenceStrength`） |
| PATCH            | `/profile`                                                             | 更新基本信息 — 未实现                                                                                  |
| POST             | `/profile/import`                                                      | 从 `text` 或 `documentId` 抽取并落库 → 200，返回计数与画像                                             |
| POST             | `/profile/import/github`                                               | 绑定 GitHub 触发分析 → 202 — PHASE 10                                                                  |
| GET              | `/profile/strength`                                                    | Profile Strength 拆解 + 改进建议 — 未实现（分数已随 `GET /dashboard` 返回）                            |
| GET/POST         | `/profile/educations` · `/experiences` · `/projects` · `/achievements` | 列表 / 新建 — 未实现                                                                                   |
| GET/PATCH/DELETE | `/profile/{entity}/{id}`                                               | 详情 / 更新 / 删除 — 未实现                                                                            |
| POST             | `/profile/projects/{id}/deep-dive`                                     | Project Deep Dive（WF-09）— 未实现                                                                     |
| POST             | `/profile/import/confirm`                                              | 确认/修正抽取结果（`origin=user_corrected`）— 未实现                                                   |

```jsonc
// GET /profile/strength → 200
{
  "success": true,
  "data": {
    "score": 82,
    "breakdown": [
      {
        "key": "completeness",
        "label": "资料完整度",
        "raw": 0.9,
        "weight": 0.3,
        "weighted": 27.0,
        "hint": "补充 1 段实习描述可再 +3",
      },
      {
        "key": "evidenceCoverage",
        "label": "证据覆盖率",
        "raw": 0.72,
        "weight": 0.25,
        "weighted": 18.0,
      },
      {
        "key": "evidenceQuality",
        "label": "证据质量",
        "raw": 0.81,
        "weight": 0.2,
        "weighted": 16.2,
      },
      {
        "key": "githubSignal",
        "label": "GitHub 信号",
        "raw": 0.78,
        "weight": 0.15,
        "weighted": 11.7,
      },
      {
        "key": "achievementBonus",
        "label": "成果加分",
        "raw": 0.9,
        "weight": 0.1,
        "weighted": 9.0,
      },
    ],
    "suggestions": [
      {
        "action": "为 CAN 补充证据",
        "impact": 4,
        "how": "把 CAN 相关代码推到 GitHub 或补充项目文档",
      },
    ],
  },
}
```

### 2.3 文档 `/documents`

> **状态：已实现（PHASE 2）**。上传先把字节暂存到 `UPLOAD_DIR`、写入 `pending` 行，
> 再入队 `document.ingest`；worker 解析、分块、写入后删除暂存文件。同一用户上传相同
> 字节（`sha256` 相同）幂等：返回既有文档、`deduplicated: true`、`taskId: null`。
> 无法解析的类型在**上传时**即返回 `400 UNSUPPORTED_FILE_TYPE`，不会先 202 再失败。
> `DELETE` 返回 `204` 且**无响应体**（RFC 9110 §6.4.1）——这是信封规则唯一的例外。

| 方法   | 路径                     | 说明                                                     |
| ------ | ------------------------ | -------------------------------------------------------- |
| POST   | `/documents`             | 上传（multipart `file` + `kind`）→ 202（自动触发 WF-01） |
| GET    | `/documents`             | 列表（`?kind=&status=`，`status` 在 SQL 层过滤）         |
| GET    | `/documents/{id}`        | 详情（Local Mode 下 `rawText` 为 null）                  |
| GET    | `/documents/{id}/chunks` | 分块列表（调试与解释用）                                 |
| GET    | `/documents/{id}/text`   | 存留的原文；未存留时返回 `unavailableReason`             |
| DELETE | `/documents/{id}`        | 删除（级联 chunks/evidence）→ 204 无响应体               |

### 2.4 GitHub Intelligence `/github`

| 方法 | 路径                                  | 说明                                            |
| ---- | ------------------------------------- | ----------------------------------------------- |
| POST | `/github/analyze`                     | `{ "username": "..." }` → 202（WF-02）          |
| GET  | `/github/profile`                     | Engineering Profile：语言占比、方向判定、置信度 |
| GET  | `/github/repositories`                | 仓库列表（含 `analysis` 摘要）                  |
| GET  | `/github/repositories/{id}`           | 仓库详情（README、关键文件、commits）           |
| POST | `/github/repositories/{id}/reanalyze` | 重新分析（忽略缓存）                            |
| GET  | `/github/rate-limit`                  | 当前限额状态                                    |

```jsonc
// GET /github/profile → 200
{
  "success": true,
  "data": {
    "username": "alexchen",
    "languages": [
      { "name": "C", "percent": 35.2 },
      { "name": "Python", "percent": 25.1 },
      { "name": "TypeScript", "percent": 18.4 },
      { "name": "C++", "percent": 12.3 },
      { "name": "Other", "percent": 9.0 },
    ],
    "engineeringProfile": [
      {
        "label": "Embedded Systems",
        "score": 0.92,
        "signals": ["FreeRTOS", "STM32 HAL", "PID", "UART DMA"],
      },
      { "label": "Backend", "score": 0.61, "signals": ["FastAPI", "PostgreSQL", "Docker"] },
      { "label": "AI Applications", "score": 0.55, "signals": ["RAG", "LLM orchestration"] },
    ],
    "totalStars": 47,
    "totalCommitsSampled": 312,
    "lastAnalyzedAt": "2026-02-11T08:12:00Z",
    "meta": { "provider": "heuristic", "degraded": true, "cacheHit": false, "tookMs": 812 },
  },
}
```

### 2.5 证据与图谱 `/evidence` `/evidence-graph` `/claims` ★

> **状态：已实现（PHASE 3）**。`evidence` / `evidence_links` 已落库（迁移 `0003`），置信度
> 由数据库 CHECK 约束保证「分数 = 五因子计算结果」。**图的节点是派生的**：技能节点来自
> `skills` 字典、候选人节点来自 `profiles`，只有证据与边是独立表，因此重新分析幂等
> （证据按内容去重、边按五元组去重）。
> `POST /evidence` 的置信度由服务端计算，请求体禁止传 `confidence`（多传字段直接 400）。
> **`POST /evidence` 是幂等的（PHASE 14）**：`evidence` 上有 `UNIQUE (user_id, kind, content_hash)`，
> 相同内容重复提交返回**已存在的那一行**（`200` + `created: false`），首次插入返回 `201` +
> `created: true`。此前它直接插入、不理会该约束，于是重复提交是 `500 INTERNAL_ERROR`——两个客户端
> （`apps/web/e2e/helpers/pages.ts`、`apps/web/scripts/capture-pages.mts`）因此都写了「先读再写」的
> 绕行，并把它作为后端缺陷记录在注释里。摄取流水线本来就会重放，正确的回答是把已有的那一行给它。
> `GET /evidence-graph` 的 `stats` 描述**本次返回的子图**，`totals` 描述全图，避免出现
> 「画布 10 个节点、摘要写 129」这类自相矛盾。`stats.meanConfidence` 在**本次子图里没有任何节点带
> 置信度**时为 `null`（PHASE 14）：此前的 `0.0` 会被读成「每个节点都得 0 分」，而事实是「还没有被评分」；
> `highConfidence`/`lowConfidence` 仍为 `0`，因为「没有高置信度节点」对该子图是真话。
> **断言门禁只有一条路径：`POST /evidence/validate`**（PHASE 14）。它由 `ResumeService.validate`
> 实现：为当前用户构建混合检索器（BM25 + 向量 + RRF），把候选人材料交给规则阶段，落库一条 claim。
> 曾经的 `POST /ai/validate/claim` **已删除**：它读 `app.state.retriever`（仓库里没有任何地方设置
> 这个属性），材料也只来自请求体，因此检索不到任何东西、`sources` 恒为空、`confidence` 恒为 `0.0`，
> 对自己材料明确支持的句子也判 `unsupported`——`supported` 在那条路径上结构上不可达（PHASE 13 实测）。
> 一个门禁、一条路径、一个决定判定结果的地方；第二个入口只会是第二份门禁逻辑，或者同一个问题的第二个
> 永久错误的答案。
> `POST /documents/{id}/analyze` 是**同步**端点：它只做确定性的本地计算，不调用模型，
> 因此不套用 §1.4 的 202 约定。

| 方法   | 路径                              | 说明                                                                             |
| ------ | --------------------------------- | -------------------------------------------------------------------------------- |
| GET    | `/evidence-graph`                 | 子图查询：`?focus=skill:stm32&depth=2&types=project,repo_file&limit=`            |
| GET    | `/evidence`                       | 证据列表（`?kind=&minConfidence=&limit=`）                                       |
| GET    | `/evidence/{id}`                  | 证据详情（locator、置信度拆解、来源）                                            |
| POST   | `/evidence`                       | 手工添加证据（`manual` 类型，置信度服务端计算）— **幂等**：201 新建 / 200 已存在 |
| DELETE | `/evidence/{id}`                  | 删除（同时删除引用它的边）                                                       |
| GET    | `/evidence/{id}/trace`            | 反向溯源：该证据支持了哪些 Claim                                                 |
| POST   | `/documents/{id}/analyze`         | 由已存文档构建证据与技能边（同步、幂等）                                         |
| POST   | `/evidence/validate`              | **Claim Validator（单条，唯一门禁路径）** — 见下方请求/响应示例                  |
| POST   | `/evidence/validate/batch`        | 批量验证（≤ 20 条，逐条落库）                                                    |
| GET    | `/claims`                         | 断言列表（`?status=&versionId=&jobId=`）— 未实现                                 |
| GET    | `/claims/{id}`                    | 断言详情（含检索详情与判定理由）— 未实现                                         |
| POST   | `/claims/{id}/accept` · `/reject` | 接受/拒绝 AI 改写建议 — 未实现                                                   |
| GET    | `/claims/{id}/validations`        | 验证历史 — 未实现                                                                |

```jsonc
// GET /evidence-graph?focus=skill:stm32&depth=2 → 200
{
  "success": true,
  "data": {
    "nodes": [
      { "id": "uuid-cand", "type": "candidate", "label": "Alex Chen", "confidence": null },
      { "id": "uuid-proj", "type": "project", "label": "Balance Robot", "confidence": 0.93 },
      {
        "id": "uuid-file",
        "type": "repo_file",
        "label": "motor_control.c",
        "confidence": 0.97,
        "meta": {
          "repo": "stm32-balance-car",
          "path": "Core/Src/motor_control.c",
          "locator": { "line": 42 },
        },
      },
      { "id": "uuid-skill", "type": "skill", "label": "STM32", "confidence": 0.95 },
      {
        "id": "uuid-claim",
        "type": "claim",
        "label": "基于 STM32 + FreeRTOS 开发实时控制系统",
        "confidence": 0.92,
      },
    ],
    "edges": [
      {
        "id": "e1",
        "source": "uuid-proj",
        "target": "uuid-file",
        "relation": "EVIDENCED_BY",
        "confidence": 0.97,
      },
      {
        "id": "e2",
        "source": "uuid-proj",
        "target": "uuid-skill",
        "relation": "DEMONSTRATES",
        "confidence": 0.95,
      },
      {
        "id": "e3",
        "source": "uuid-file",
        "target": "uuid-claim",
        "relation": "SUPPORTS",
        "confidence": 0.94,
      },
    ],
    "meta": { "nodeCount": 5, "edgeCount": 3, "truncated": false, "depth": 2 },
  },
}
```

```jsonc
// POST /evidence —— 首次 → 201；相同内容再次提交 → 200（沿用既有行）
// request（`extra="forbid"`：传 confidence 直接 400）
{ "title": "上线了一个内部工具",
  "snippet": "用 Python 写了一个自动生成周报的脚本",
  "locator": { "url": "https://example.com/tool" } }

// 201（首次）/ 200（重复）
{ "success": true, "data": {
    "id": "uuid-e9", "kind": "manual", "title": "上线了一个内部工具",
    "confidence": 0.55, "created": true,          // 重复提交时为 false，且 id 与首次相同
    "factors": { "sourceAuthority": 0.55, "recency": 0.9, "specificity": 0.5,
                 "corroboration": 0.6, "extractionQuality": 0.7,
                 "corroborationSources": 1, "recomputed": 0.55,
                 "formulaVersion": "confidence@1.0.0" },
    "locator": { "url": "https://example.com/tool", "path": null, "line": null } } }
```

```jsonc
// POST /evidence/validate —— 唯一门禁路径（routers/resume.py → ResumeService.validate）
// request：`extra="forbid"`；旧 /ai/validate/claim 的 { claim, evidence_text } 会被 400 拒绝
{ "text": "基于 FreeRTOS 开发多任务实时控制系统，任务调度周期 1ms",
  "section": "summary", "jobId": "uuid-job" }

// 200
{ "success": true, "data": {
    "claimId": "uuid-claim-1",              // 判定已落库（resume_claims.resume_version_id 为 null）
    "claim": {
      "claim": "基于 FreeRTOS 开发多任务实时控制系统，任务调度周期 1ms",
      "status": "partially_supported",
      "confidence": 0.68,
      "hasQuantifiedClaim": true,
      "independentSourceCount": 2,
      "ruleVersion": "claim_rules@1.0.0",
      "model": "heuristic@1.0.0",           // 判定所依据的模型；规则阶段未调用模型时为 null
      "sources": [
        {"evidenceId":"uuid-e1","title":"freertos.c","kind":"document_chunk","relevance":0.94,
         "channel":"both","locator":"Core/Src/freertos.c:18","url":null,"snippet":"…"},
        {"evidenceId":"uuid-e2","title":"README.md","kind":"manual","relevance":0.81,
         "channel":"semantic","locator":"","url":null,"snippet":"…"} ],
      "reasons": [
        {"rule":"numeric_without_evidence","severity":"warning","evidenceIds":[],
         "message":"「1ms 调度周期」在证据中未找到量化支撑，建议删除具体数值或补充实测数据"} ],
      "safeRewrite": { "text": "基于 FreeRTOS 开发多任务实时控制系统",
                       "removedClaims": ["任务调度周期 1ms"], "rationale": "删去无证据的量化表述" },
      "unknowns": ["实际调度周期未在证据中体现"] },
    // 门禁自己的降级状态：检索失败时 `degraded: true`，`warnings` 里写明原因
    "degraded": false,
    "warnings": [] } }
```

> **`degraded` / `warnings` 属于判定本身，不是装饰（PHASE 14）**：检索器抛异常时门禁仍会给出判定，
> 但那是「没检索到证据」而不是「没有证据支持」，响应必须说明，否则读者无法给它打折。这两个字段此前
> 被服务层丢弃（`ResumeService.validate` 把工作流 outcome 解包到一个未使用的变量里），只在运行轨迹里
> 可见。

**状态语义**：`supported` / `partially_supported` / `unsupported` / `contradicted`（详见 PRD 4.4）。
`contradicted` **只用于证据确实与之冲突**（时间线冲突，或模型报告了 `contradicting_evidence`）；
规则层 blocker（无同类量化支撑、技术名词不在证据中、最高级措辞）一律判 `unsupported`——被拒绝，
但不被诬指为已被反驳。规则 blocker **允许**附带 `safeRewrite`（删掉数字正是不支持数字的正确修法），
但若删掉数字后句中仍残留证据无法支撑的技术名词，则不提供改写：保留名字、只删数字，等于用看不出
删改痕迹的方式断言同一件无法支撑的事。状态为 `partially_supported` 且独立来源不足 2 条时，会写入
`single_source_only` 理由，降级必须说明原因。

### 2.6 岗位与匹配 `/jobs`

> **状态：已实现（PHASE 4）**：`/jobs/analyze`、`/jobs`、`/jobs/{id}`、`/jobs/{id}/skill-tree`、
> `DELETE /jobs/{id}`、`/jobs/{id}/match`（POST/GET）。解析与匹配都是**同步**的，符合本文档
> 的约定：JD 解析是「用户正盯着输入框」的操作，匹配则是确定性算术，把它们塞进队列只会多一次
> 轮询。
> 同一段 JD 文本重复提交会**更新同一条岗位**（按 `description_sha256` 去重），因此匹配历史
> 不会被拆到两张卡片上。每次匹配都**新增一行**而非覆盖：分数变化时，上一行说明了它从多少变来、
> 由哪个算法版本产生。
> `strengths` / `gaps` / `unknowns` 在响应中是 camelCase 且明确的模型；`why.formula` 是真实
> 公式而非描述，`dimensions[*].weighted` 之和等于 `score`（有测试断言这一点）。
> **`GET /jobs/{id}/match` 读库，因此它只能回答库里有的东西（PHASE 14）**：`job_matches` 存了分数、
> 五个维度的分数与权重、`why`、`strengths`/`gaps`/`unknowns`，**没有**存 `evidenceCoverage`、
> `confidence`、`degraded`、`narrative`、`warnings`，也没有按维度存 `evidenceIds` / `notes`。
> 这些字段在 GET 响应里是 `null`（而不是模型的 `0.0` / `false` / `[]`）：此前的默认值会被当成测量值，
> 于是同一次匹配在 GET 上显示「证据覆盖率 0%」，而 POST 刚刚测出 100%。要拿到这五个数字就重新算一次
> （`POST`），这是唯一诚实的途径。GET 与 POST 的响应结构相同，只有这几个字段有值/无值的区别。
> 尚未实现：`PATCH /jobs/{id}`（纠正解析结果）、`POST /jobs/match`（不落库的即时匹配）、
> `POST /jobs/{id}/skill-gap` 与 `/learning-plan`（CoachAgent 已有，端点待接；两行此前只写了
> 「PHASE 8」，读起来像已交付，PHASE 14 核对路由表时确认仍未挂载）。
> `POST /jobs/{id}/applications`（加入投递看板）已实现，见 §2.9。
> `experience` 与 `project` 两个维度自 PHASE 2b 起由 §2.2 的职业实体表驱动；空缺的维度会如实
> 记为 0 并在 `unknowns` 里说明「没有这类数据」，而不是用假设填补。

| 方法   | 路径                       | 说明                                                         |
| ------ | -------------------------- | ------------------------------------------------------------ |
| POST   | `/jobs/analyze`            | `{ "text": "JD..." }` → 200（WF-03），同步返回解析结果       |
| GET    | `/jobs`                    | 列表（`?q=` 按岗位名子串）                                   |
| GET    | `/jobs/{id}`               | 详情（含 `analysis` 原文与全部要求行）                       |
| GET    | `/jobs/{id}/skill-tree`    | Required / Preferred / Bonus 三层树（每项带 JD 原文出处）    |
| PATCH  | `/jobs/{id}`               | 修正解析结果（用户纠正提升 `parse_confidence`）— 未实现      |
| DELETE | `/jobs/{id}`               | 删除（级联要求行与匹配历史）                                 |
| POST   | `/jobs/{id}/match`         | 计算匹配（WF-04）→ 同步，落库并返回完整 `why` 与五个测量字段 |
| GET    | `/jobs/{id}/match`         | 最新匹配结果（读库，不重算；未存储的字段为 `null`）          |
| POST   | `/jobs/match`              | 不保存 JD 的即时匹配 — 未实现                                |
| POST   | `/jobs/{id}/skill-gap`     | 缺口矩阵 — 未实现（CoachAgent 已有，端点未挂载）             |
| POST   | `/jobs/{id}/learning-plan` | 30 天计划 + mini projects（WF-08）— 未实现                   |
| POST   | `/jobs/{id}/applications`  | 加入投递看板（见 §2.9）                                      |

```jsonc
// POST /jobs/{id}/match → 200（GET 同构，但 evidenceCoverage / confidence / degraded /
//                          narrative / warnings 与各维度的 evidenceIds / notes 为 null）
{
  "success": true,
  "data": {
    "jobId": "uuid-job",
    "score": 86.0,
    "dimensions": {
      "skill": {
        "key": "skill",
        "label": "技能匹配",
        "score": 91.0,
        "weight": 0.4,
        "weighted": 36.4,
        "formula": "0.40·skill + …",
        "notes": ["无证据的技能按 40% 计入"],
        "evidenceIds": ["uuid-e1", "uuid-e1", "uuid-e2"],
      },
      "experience": {
        "key": "experience",
        "label": "经验匹配",
        "score": 88.0,
        "weight": 0.25,
        "weighted": 22.0,
        "formula": "…",
        "notes": [],
        "evidenceIds": [],
      },
      "project": {
        "key": "project",
        "label": "项目匹配",
        "score": 84.0,
        "weight": 0.2,
        "weighted": 16.8,
      },
      "education": {
        "key": "education",
        "label": "学历匹配",
        "score": 100.0,
        "weight": 0.05,
        "weighted": 5.0,
      },
      "evidence": {
        "key": "evidence",
        "label": "证据强度",
        "score": 78.0,
        "weight": 0.1,
        "weighted": 7.8,
      },
    },
    "strengths": [
      {
        "canonicalId": "stm32",
        "displayName": "STM32",
        "requirement": "required",
        "userLevel": "advanced",
        "evidenceCount": 12,
        "confidence": 0.95,
        "reason": "3 个项目 + 12 条代码证据",
      },
    ],
    "gaps": [
      {
        "canonicalId": "can",
        "displayName": "CAN",
        "requirement": "required",
        "severity": "high",
        "jdEvidence": "熟悉 CAN/CANopen 总线",
      },
    ],
    "unknowns": [
      {
        "canonicalId": "rt_thread",
        "displayName": "RT-Thread",
        "requirement": "preferred",
        "reason": "简历未提及且无相关证据",
        "askUser": "你是否接触过 RT-Thread？",
      },
    ],
    "why": {
      "formula": "0.40·skill + 0.25·experience + 0.20·project + 0.05·education + 0.10·evidence",
      "algorithmVersion": "match@1.0.0",
      "evidenceUsed": ["uuid-e1", "uuid-e2", "uuid-e7"],
      "notes": ["证据强度维度因 CAN/AUTOSAR 缺失被扣分，反映「要求但无证据」的真实风险"],
      "explanation": "…",
      "computedAt": "2026-02-12T09:15:00+00:00",
    },
    "evidenceCoverage": 1.0, // 0..1；GET 读库时为 null
    "confidence": 0.95, // strengths 的平均证据置信度；GET 读库时为 null
    "degraded": true, // 产生这次匹配的运行是否降级；GET 读库时为 null
    "narrative": "", // 叙述步骤失败时为空字符串（这是一次真实的测量）
    "warnings": ["尚无证据：请先上传简历并运行分析，证据强度维度才有数据可算。"],
  },
}
```

### 2.7 简历 Copilot `/resume`

| 方法  | 路径                                          | 说明                                                   |
| ----- | --------------------------------------------- | ------------------------------------------------------ |
| POST  | `/resume/optimize`                            | `{ jobId \| text, versionId?, tones? }` → 202（WF-05） |
| GET   | `/resume/versions`                            | 版本列表                                               |
| GET   | `/resume/versions/{id}`                       | 版本详情（结构化 bullet + claim 状态）                 |
| POST  | `/resume/versions/{id}/rollback`              | 回滚为当前版本                                         |
| PATCH | `/resume/versions/{id}/claims/{claimId}`      | 接受/拒绝单条改写                                      |
| GET   | `/resume/versions/{id}/export?format=md\|pdf` | 导出                                                   |
| GET   | `/resume/diff?from=&to=`                      | 版本对比                                               |

```jsonc
// GET /resume/versions/{id} → 200（节选）
{
  "success": true,
  "data": {
    "id": "uuid-v3",
    "label": "Embedded Engineer @ 某公司 定制版",
    "targetJobId": "uuid-job",
    "integrityScore": 0.86,
    "claimStats": { "supported": 11, "partiallySupported": 3, "unsupported": 1, "contradicted": 0 },
    "bullets": [
      {
        "id": "uuid-c1",
        "section": "project",
        "status": "supported",
        "confidence": 0.92,
        "original": "参与无人机项目开发。",
        "optimized": "基于 PX4 完成无人机控制链路集成与调试，负责嵌入式控制模块、通信接口及飞控参数验证。",
        "evidence": [{ "evidenceId": "uuid-e9", "title": "px4_ctrl.cpp", "kind": "repo_file" }],
      },
      {
        "id": "uuid-c2",
        "section": "project",
        "status": "contradicted",
        "confidence": 0.21,
        "original": "优化算法性能，提升 70%。",
        "optimized": null,
        "reasons": [
          {
            "rule": "numeric_without_evidence",
            "severity": "blocker",
            "message": "「70%」无任何实测数据支撑，已拒绝写入简历",
          },
        ],
        "safeRewrite": "重构控制回路，降低单周期计算开销（需补充实测数据后可量化表述）",
      },
    ],
  },
}
```

### 2.8 AI 端点 `/ai`（含模拟面试 `/ai/interview`）

> **状态：已实现（PHASE 2/PHASE 7）**。本节按**代码**写就（PHASE 14）：路由在
> `apps/api/src/careerforge_api/routers/ai.py`，请求/响应模型在 `schemas/ai.py`，面试引擎在
> `packages/ai/careerforge_ai/agents/interview/*` 与 `schemas/interview.py`。
> **此前本节写的是另一套东西**：路径写成 `/interview/*`（实际挂载在 `/ai/interview/*`）、
> 字段写成 camelCase（`interviewId` / `difficultyChange` / `message`）、请求体写成 `jobId` +
> `projectId`（实际是**已解析的 `JDAnalysis`**）。照着旧文档写客户端，一个字段都对不上。
> **这些端点是无状态的**：材料由调用方在请求体里给出，AI 层不去读未落地的表。因此
> `POST /ai/interview/start` 收的是 `GET /jobs/{id}` 的 `analysis`（不是 `/jobs/analyze` 的响应——
> 后者多一个 `warnings` 键，`extra="forbid"` 会直接 400）。
> 每个端点都真的跑生产 agent（`WorkflowExecutor`），每次运行都写 `agent_runs`，响应里的 `meta`
> 说明是哪个 provider 提供的答案、是否降级、`run_id` 是多少。
> **断言校验不在这里**：`POST /ai/validate/claim` 已于 PHASE 14 **删除**，唯一门禁路径是
> `POST /evidence/validate`（§2.5）。后者会为当前用户构建混合检索器并把候选人材料交给规则阶段，
> 而前者读 `app.state.retriever`（仓库里没有任何地方设置它）、材料只来自请求体，于是检索不到任何
> 证据、`sources` 恒为空、`confidence` 恒为 `0.0`，对候选人自己材料明确支持的句子也判 `unsupported`——
> `supported` 在那条路径上结构上不可达。
> **响应字段是 snake_case**（Pydantic 模型直接序列化，没有 `by_alias`），`meta` 里的键同样是
> snake_case。面试会话保存在**进程内**（`GET /ai/capabilities` 的 `session_store: "in-process"`）：
> 多进程部署下，另一个 worker 看不到本进程创建的会话。

| 方法   | 路径                                | 说明                                                          |
| ------ | ----------------------------------- | ------------------------------------------------------------- |
| POST   | `/ai/analyze/jd`                    | `{ text }` → JD 解析结果 `analysis` + `meta`（同步，WF-03）   |
| POST   | `/ai/match`                         | `{ job, profile }` → 五维匹配分 + `why`（无状态版本，不落库） |
| GET    | `/ai/capabilities`                  | agent 清单、provider 链、本部署的限制与降级状态（需认证）     |
| POST   | `/ai/interview/start`               | `{ mode?, job?, profile?, difficulty? }` → 会话 + 计划 + 首题 |
| POST   | `/ai/interview/{session_id}/answer` | `{ answer }` → 评估、难度变化、下一题                         |
| POST   | `/ai/interview/{session_id}/finish` | 收尾并生成七维 Scorecard                                      |
| GET    | `/ai/interview/{session_id}`        | 会话详情（刷新页面后恢复用）                                  |
| DELETE | `/ai/interview/{session_id}`        | 丢弃会话 → `204`，无响应体                                    |

```jsonc
// GET /ai/capabilities → 200（需认证）
{
  "success": true,
  "data": {
    "agents": [
      {
        "agent": "validator",
        "workflow": "claim_validate",
        "status": "ready",
        "purpose": "断言验证与防幻觉门禁",
      } /* …共 9 个… */,
    ],
    "provider": "heuristic",
    "provider_chain": ["heuristic"],
    "degraded": true, // 零密钥部署：主 provider 是确定性启发式实现
    "retrieval_available": false, // 进程级检索器未配置（AI 端点不用它，见 limitations）
    "session_store": "in-process",
    "active_interview_sessions": 0,
    "limitations": [
      "进程级检索器未配置：AI 端点（analyze/match/interview）为无状态实现，材料来自请求体；断言门禁 POST /evidence/validate 不受影响，它每次请求都会用当前用户的 evidence 表构建混合检索器（BM25 + 向量 + RRF）",
      "当前使用 SQLite 与进程内队列，数据不跨进程共享",
      "AI 端点为无状态实现：输入直接来自请求体（岗位用 JD 解析结果、画像由调用方提供），不读取未落地的表",
    ],
  },
}
```

```jsonc
// POST /ai/interview/start
// request：`extra="forbid"`；`job` 是 JD 解析结果本身（GET /jobs/{id} 的 analysis），
// 不是 jobId —— 存储 id 由服务端从别处取，无状态端点不需要它
{ "mode": "technical",
  "job": { "company": "某科技", "role": "嵌入式软件工程师", "education_requirement": "本科",
           "years_experience_min": 3.0,
           "required_skills": [ { "canonical_id": "stm32", "raw_text": "STM32",
                                  "requirement": "required", "jd_evidence": "熟悉 STM32" } ] },
  "profile": { "skills": [ /* CandidateProfile … */ ] },
  "difficulty": 1 }

// 200
{ "success": true, "data": {
    "session_id": "uuid-iv",
    "mode": "technical",
    "status": "in_progress",
    "current_level": "concept",
    "plan": [
      { "topic": "stm32", "label": "STM32", "target_level": "engineering",
        "reason": "岗位要求 STM32，且你有 8 条证据", "source": "evidence",
        "source_ids": ["uuid-e1", "uuid-e2"], "covered": true },
      { "topic": "can", "label": "CAN", "target_level": "concept",
        "reason": "岗位必备 CAN，但证据图谱中没有支撑，面试中很可能被追问", "source": "gap",
        "source_ids": [], "covered": false }
    ],
    "turns": [
      { "turn_index": 0, "role": "interviewer", "topic": "stm32", "level": "engineering",
        "score": null, "content": "你在 Balance Robot 里用了 STM32，为什么选择它而不是其它方案？" }
    ],
    "scorecard": null,
    "meta": { "provider": "heuristic", "model": "heuristic@1.0.0", "prompt_version": "interviewer@v1",
              "degraded": true, "degraded_reason": "no_api_key", "workflow": "interview_start",
              "run_id": "uuid-run", "latency_ms": 12, "cache_hit": false, "warnings": [] } } }

// POST /ai/interview/{session_id}/answer
{ "answer": "因为需要多任务并发，裸机前后台在时序上很难保证……" }

// 200
{ "success": true, "data": {
    "session_id": "uuid-iv",
    "status": "in_progress",
    "current_level": "debugging",                 // 难度阶梯：concept → engineering → debugging
    "evaluation": {
      "turn_index": 1, "score": 78.0,
      "technical_accuracy": 0.8, "depth": 0.6, "communication": 0.75,
      "problem_solving": 0.7, "engineering_thinking": 0.65, "confidence": 0.82,
      "missing_knowledge": ["优先级反转与互斥量优先级继承"],
      "feedback": "概念正确，但未涉及中断与任务的同步边界。",
      "strong_points": [], "follow_up_topics": [], "suggested_answer": "…" },
    "difficulty_change": { "from_level": "concept", "to_level": "debugging",
                           "reason": "回答得分 78，高于 75，进入更深一层追问" },
    "next_question": { "turn_index": 2, "content": "Task 与 ISR 之间你用什么方式通信？为什么不用全局变量？",
                       "topic": "can", "level": "debugging" },
    "meta": { /* … */ } } }

// POST /ai/interview/{session_id}/finish → 200（结构与 start 相同，status=completed）
// GET  /ai/interview/{session_id}      → 200（同一结构，用于刷新后恢复）
// DELETE /ai/interview/{session_id}    → 204（无响应体）
{ "success": true, "data": {
    "session_id": "uuid-iv", "mode": "technical", "status": "completed",
    "current_level": "debugging",
    "plan": [ /* 同上；`covered` 由**实际问过的题目**推导，不是计划时声明的 */ ],
    "turns": [ /* 面试官与候选人交替 */ ],
    "scorecard": {
      "interview_id": "uuid-iv", "mode": "technical",
      "overall_score": 78.0,
      "dimensions": [
        { "key": "technical_accuracy", "label": "技术准确性", "score": 82.0, "comment": "" },
        { "key": "communication", "label": "表达沟通", "score": 75.0, "comment": "" },
        { "key": "depth", "label": "技术深度", "score": 70.0, "comment": "" },
        { "key": "problem_solving", "label": "问题解决", "score": 80.0, "comment": "" },
        { "key": "engineering_thinking", "label": "工程思维", "score": 76.0, "comment": "" },
        { "key": "confidence", "label": "自信度", "score": 79.0, "comment": "" },
        { "key": "evidence_consistency", "label": "证据一致性", "score": 88.0,
          "comment": "口述内容与证据图谱一致" } ],
      "strengths": [], "weaknesses": [],
      "missing_knowledge": ["优先级反转与互斥量优先级继承"],
      "follow_up_topics": ["FreeRTOS 内存管理 heap_4", "中断延迟测量方法"],
      "evidence_conflicts": [
        { "statement": "熟悉 CAN 总线", "evidence_state": "你在回答中提到了这些技术，但证据图谱中没有支撑材料：can",
          "severity": "medium", "advice": "面试前补齐相关代码或文档，或调整表述范围，避免追问时无法举证" } ],
      "per_question": [
        { "turn_index": 0, "topic": "stm32", "level": "engineering", "verdict": "strong",
          "question": "…", "answer": "…", "suggested_answer": "…",
          "missing_knowledge": [], "follow_up_topics": [] } ],
      "difficulty_start": "engineering", "difficulty_end": "debugging",
      "duration_seconds": 942,          // started_at → completed_at；会话未结束时为 null
      "generated_at": "2026-09-25T18:40:00+00:00",
      "algorithm_version": "scorecard@1.0.0" },
    "meta": { "provider": "session", "workflow": "interview", "degraded": false, "warnings": [] } } }
```

### 2.9 投递看板 `/applications`

> **状态：已实现（PHASE 8b）**：下表 7 个端点全部实现，另加 `POST /jobs/{job_id}/applications`
> （FR-13.5「从 JD 分析结果一键加入投递」）。表见 `docs/DATABASE.md` §2.7（迁移 `0007`）。
> **看板是快照，不是实时视图**：卡片在创建时复制岗位的公司/角色/地点与**系统最近一次算出的匹配分**，
> 此后不随岗位变化。`matchScore` **不接受客户端传入**（`extra="forbid"`）——卡片上的分数是证据，不是声明；
> 岗位被删除时 `jobId` 置空而卡片保留（公司名仍显示），否则一次清理动作就等于删掉用户的求职历史。
> **每一次状态变更都写一条 `application_events`**（追加式，含 `fromStatus`），这是 PHASE 9 漏斗的数据源；
> 移到**同一状态**不写事件（列内拖拽是排序而非移动，否则一次投递会被漏斗数成好几次）。
> `appliedAt` 在首次离开 `wishlist` 时写入，且不被「拖回去」抹掉——倒退是纠正看板，不是否认投过。
> `offer` / `rejected` 会清空 `nextActionAt`：已结束的投递不该留着提醒。
> **不禁止任何方向的流转**：看板是拖拽的，候选人会拖错、会在面试后被拒后拖回、会几个月后重新考虑；
> 与其跟用户较劲，不如把每次移动都记下来——可审计的历史比状态机更值钱。
> 里程碑（投递 / 面试 / Offer / 被拒）另外写入 `career_events`，**同一状态只写一次**（拖来拖去不会把
> 时间线撑大）；中间态（`oa` / `final`）只留在事件表里。
> `GET /applications/board` 返回**全部七列，空列也返回**：空列本身是信息（说明还没到那一步），
> 缺 key 只会让客户端去猜，而猜出来的看板会在新增阶段的当天画错。
> `/applications/reorder` 与 `/applications/board` 在路由表中**声明在 `/{application_id}` 之前**：
> 反过来注册，字面量路径会被当成 id，端点对自己的文档路径回 404。
> **前端已实现（PHASE 8c）**：`/app/applications` 七列看板，指针拖拽与键盘拖拽（`Space` 拾起 →
> 方向键 → `Space` 放下）走同一个 `PATCH /applications/reorder`，乐观更新在服务端响应前生效、
> 失败回滚并提示；移动端为按状态分组的列表。契约守卫 `isApplicationBoard` 要求**七列齐全**，
> 少一列即报错而不是画出六列。

| 方法   | 路径                          | 说明                                                                  |
| ------ | ----------------------------- | --------------------------------------------------------------------- |
| GET    | `/applications`               | 列表（`?status=`、`?includeArchived=`）                               |
| GET    | `/applications/board`         | 看板：七列（按固定顺序）+ `counts` + `total` + `archived`             |
| POST   | `/applications`               | 新建（`{ jobId \| manual fields }`，`status` 默认 `wishlist`）        |
| PATCH  | `/applications/reorder`       | 拖拽落位 `{ items:[{id,status,position}] }`，位置由服务端重新推导     |
| POST   | `/jobs/{job_id}/applications` | 从 JD 分析结果加入看板（body 可省略，公司等取自岗位快照）             |
| GET    | `/applications/{id}`          | 详情（含事件历史，最新在前）                                          |
| PATCH  | `/applications/{id}`          | 更新字段/状态（状态变更自动写 `application_events`；`archived` 归档） |
| GET    | `/applications/{id}/events`   | 状态变更历史                                                          |
| DELETE | `/applications/{id}`          | 删除（硬删除，事件级联；归档请用 `PATCH archived`）                   |

```json
{
  "success": true,
  "error": null,
  "requestId": "req_01HQ…",
  "data": {
    "columns": [
      { "status": "wishlist", "items": [] },
      { "status": "applied", "items": [] },
      {
        "status": "oa",
        "items": [
          {
            "id": "uuid-a1",
            "jobId": "uuid-j1",
            "company": "智远科技",
            "role": "嵌入式软件工程师",
            "location": "苏州",
            "status": "oa",
            "matchScore": 20.0,
            "position": 0,
            "appliedAt": "2026-02-12T09:15:00+00:00",
            "nextActionAt": null,
            "salaryExpectation": "18k×15",
            "notes": "",
            "archivedAt": null
          }
        ]
      },
      { "status": "interview", "items": [] },
      { "status": "final", "items": [] },
      { "status": "offer", "items": [] },
      { "status": "rejected", "items": [] }
    ],
    "counts": {
      "wishlist": 0,
      "applied": 0,
      "oa": 1,
      "interview": 0,
      "final": 0,
      "offer": 0,
      "rejected": 0
    },
    "total": 1,
    "archived": 0
  }
}
```

### 2.10 简历与断言 `/resume` `/claims` ★

> **状态：已实现（PHASE 6b）**：`POST /resume/optimize`、`GET /resume/versions`、
> `GET /resume/versions/{id}`、`DELETE /resume/versions/{id}`，以及 §2.5 的
> `POST /evidence/validate` 与 `/evidence/validate/batch`（≤ 20 条）。表结构见
> `docs/DATABASE.md` §2.9（迁移 `0006`）。
> **门禁持有的不是徽章而是引用**：`claim_evidence` 记录「这句话靠哪条证据」，`resume_claims`
> 记录判定、置信度、触发的规则与降级改写；因此「为什么被改写」在几个月后仍可回答，且不依赖
> 当时是否配了模型。`resume_claims.resume_version_id` 可空，Validator 页因此能校验一句**尚未**
> 进入任何版本的草稿。
> **门禁需要检索器**：缺检索器时它不会降级，而是全盘拒绝——API 侧为每次校验构建当用户的混合
> 检索器（BM25 + 向量 + RRF），并把候选人材料作为规则阶段的输入传给引擎（协议规定持有材料的
> 调用方应当提供）。这条路径就是 `POST /evidence/validate`，**唯一**的门禁入口（PHASE 14 删除了
> 无状态的 `POST /ai/validate/claim`，理由见 §2.5）。检索失败时响应会给出 `degraded: true` 与
> `warnings`，运行轨迹里也有对应的一条 `agent_runs`。
> `integrity_score` 与 `claim_stats` 由**本次实际落库的 claim** 计算，不抄引擎字段，避免摘要与
> 内容互相矛盾。
> 剩余已知限制见 `docs/ROADMAP.md`「已知限制」：去掉度量动词后分句可能只剩名词短语（规则无法诚实
> 重建被删的谓词，保留分句交给候选人补完）。此前记录的「句中度量动词悬空」「`contradicted` 分类
> 偏重」「单来源降级缺理由」已在 PHASE 6c 修复，见 `CHANGELOG.md`。

| 方法   | 路径                         | 说明                                                  |
| ------ | ---------------------------- | ----------------------------------------------------- |
| POST   | `/resume/optimize`           | 按目标岗位改写要点，逐条过门禁 → 落库为版本           |
| GET    | `/resume/versions`           | 版本列表（含 `integrityScore` 与 `claimStats`）       |
| GET    | `/resume/versions/{id}`      | 版本详情：要点、逐条 claim（状态/依据/引用/降级改写） |
| DELETE | `/resume/versions/{id}`      | 删除版本（claims 与引用级联）                         |
| POST   | `/evidence/validate`         | Claim Validator 单条（可脱离版本存在）                |
| POST   | `/evidence/validate/batch`   | 批量校验（≤ 20 条，逐条落库）                         |
| GET    | `/resume/versions/{id}/diff` | 版本对比 — 未实现                                     |
| POST   | `/claims/{id}/dismiss`       | 忽略某条判定 — 未实现                                 |

### 2.11 分析 `/dashboard` `/analytics`

> **状态：`/dashboard` 已实现（PHASE 5，PHASE 8b 补齐投递指标），`/analytics/*` 已实现（PHASE 9）。**
> 有意**不缓存**（与本文档的「含缓存」不同）：这里的每个数字都由用户几秒前才可能改动的行
> 推导而来（上传简历、跑一次匹配），一个和上一页互相矛盾的缓存首页比多花 30ms 更糟。
> **分析页的每个数字都由事件流确定性算出，没有任何模型参与**（ADR-022 的同一原则：
> 模型可以叙述一个给定的数字，不能发明一个数字）。
>
> **两种时间窗口，各自写在响应里**：漏斗 / 比率 / 相关性 / 类别按**投递的创建时间**过滤
> （同期群：分母与分子来自同一批投递），`/analytics/timeline` 按**事件发生时间**过滤
> （「这段时间发生了什么」）。`meta.windowBasis` 明确写出用的是哪一种——否则同一个「30d」
> 会被读成两件事。`meta.fromAt/toAt/cohortSize/minimumSample` 随数字一起下发。
>
> **一个比率永远不单独出现**：每张比率卡都带 `numerator` / `denominator` / Wilson 95% 区间 /
> `sufficient`；分母小于 `minimumSample`（5）时界面显示「样本不足，仅供参考」。
> 分母为 0 时 `rate` 是 `null`（不是 0）——「没有投递」不等于「投递成功率为 0%」。
> 漏斗的 `stepRate` 在上一阶段为 0 时是 `null`：0 个终面里出 0 个 Offer 不是 100% 转化率。
>
> **漏斗数的是「到达过」，不是「现在在哪」**：投递→面试→被拒的卡片在看板上是 `rejected`，
> 在漏斗里**算作进过面试**（这也是 §2.11 中 `interviews` 快照口径与漏斗口径本就不同的原因）。
> 每个阶段都带 `basis` 字段说明自己的计数规则；`wishlist` 卡片不算投递。
> 技能的相关系数同时给出「要求它的岗位」与「未要求的岗位」两组，差异只有在两组都达到样本下限
> **且** 95% 区间不重叠时才标记 `notable`——小样本下任何两个比例都能排出高低。
> 岗位类别由岗位要求技能的词典分类加权得出，不是人工标签；无法归类记为 `unknown` 而不丢弃。
> `applications` / `interviews` / `offers` 自 PHASE 8b 起是**真实计数**（`meta.unavailable` 因此为空，
> 但机制保留：下一个「先上数字、后接数据源」的功能还要用它）。`interviews` 是**看板快照**——
> 当前处于 `interview`/`final`/`offer` 的卡片数；曾进面试但已结束的不计入，漏斗口径按事件流统计，
> 两者本就应该不同，所以口径随数字一起下发。
> `meta.definitions` 随数字一起给出每个指标实际使用的口径，前端优先使用它而不是本地副本，
> 避免标签与算法悄悄分叉。
> `skillsRadar[].market` 目前缺省：市场均值需要岗位语料，尚未收集；编造一条基线会把对比变成装饰。

| 方法 | 路径                           | 说明                                               |
| ---- | ------------------------------ | -------------------------------------------------- |
| GET  | `/dashboard`                   | 聚合首页数据（一次请求；每个指标附带口径与可用性） |
| GET  | `/analytics/funnel`            | 漏斗 `?range=7d\|30d\|90d\|all`（默认 30d）✅      |
| GET  | `/analytics/rates`             | Interview/Offer/Response Rate + 均分 ✅            |
| GET  | `/analytics/skill-correlation` | 技能 ↔ 面试成功率（两组样本量 + 显著性说明）✅     |
| GET  | `/analytics/categories`        | 岗位类别表现排行 ✅                                |
| GET  | `/analytics/timeline`          | Career Timeline 事件流 + 月度趋势 ✅               |

```jsonc
// GET /analytics/funnel?range=all → 200（真机实测：6 张卡片，其中 1 张仍是 wishlist）
{ "success": true, "data": {
    "meta": { "range": "all", "fromAt": null, "toAt": "2026-03-01T00:00:00Z",
              "cohortSize": 6, "minimumSample": 5, "windowBasis": "applications",
              "notes": ["range 过滤的是**投递的创建时间**（同期群）…"] },
    "stages": [
      {"key":"applications","label":"投递","count":5,"shareOfFirst":1.0,"stepRate":1.0,
       "basis":"曾离开 wishlist 的卡片（来自事件流，不是当前状态）"},
      {"key":"replies","label":"有回复","count":3,"shareOfFirst":0.6,"stepRate":0.6,
       "basis":"曾进入 oa/interview/final/offer，或投递后被拒（被拒也是回复）"},
      {"key":"interviews","label":"面试","count":2,"shareOfFirst":0.4,"stepRate":0.6667,
       "basis":"曾进入 interview/final/offer"},
      {"key":"finals","label":"终面","count":1,"shareOfFirst":0.2,"stepRate":0.5,
       "basis":"曾进入 final/offer"},
      {"key":"offers","label":"Offer","count":1,"shareOfFirst":0.2,"stepRate":1.0,
       "basis":"曾进入 offer"} ] } }

// GET /analytics/rates?range=all → 200（同上场景，注意 1/5 恰好达到样本下限）
{ "success": true, "data": { "meta": { "...": "同上" }, "cards": [
    {"key":"responseRate","label":"Response Rate","rate":0.6,"numerator":3,"denominator":5,
     "sufficient":true,"intervalLow":0.23,"intervalHigh":0.88,
     "definition":"有回复的投递 ÷ 全部投递（分母：本区间内投出 5 次）"},
    {"key":"interviewRate","label":"Interview Rate","rate":0.4,"numerator":2,"denominator":5,
     "sufficient":true,"intervalLow":0.12,"intervalHigh":0.77,"definition":"…"},
    {"key":"averageMatchScore","label":"Avg Match Score","rate":null,"numerator":0,"denominator":0,
     "sufficient":false,"intervalLow":0.0,"intervalHigh":0.0,
     "definition":"本区间内已评分卡片的平均匹配分 ÷ 100（分母：0 张有分数的卡片；未评分的卡片不计入，也不按 0 计）"} ] } }
```

```jsonc
// GET /dashboard → 200
{
  "success": true,
  "data": {
    "profileStrength": { "score": 82, "delta7d": 3 },
    "stats": {
      "evidenceCoverage": 0.72,
      "skillCoverage": 0.68,
      "resumeMatch": 0.84,
      "applications": 23,
      "interviews": 5,
      "offers": 1,
    },
    "skillsRadar": [
      { "skill": "C/C++", "user": 0.92, "market": 0.71 },
      { "skill": "Python", "user": 0.8, "market": 0.88 },
      { "skill": "Embedded", "user": 0.95, "market": 0.62 },
      { "skill": "Backend", "user": 0.58, "market": 0.74 },
      { "skill": "AI", "user": 0.62, "market": 0.8 },
      { "skill": "System Design", "user": 0.55, "market": 0.76 },
      { "skill": "DevOps", "user": 0.6, "market": 0.58 },
    ],
    "recentJobs": [
      {
        "jobId": "uuid-j1",
        "company": "某科技",
        "role": "Embedded Engineer",
        "matchScore": 87,
        "status": "interview",
      },
      {
        "jobId": "uuid-j2",
        "company": "某 AI 公司",
        "role": "AI Application Engineer",
        "matchScore": 81,
        "status": "applied",
      },
    ],
    "nextActions": [{ "type": "interview", "title": "某科技 二面", "at": "2026-02-14T09:00:00Z" }],
    "meta": {
      "cacheHit": false,
      "tookMs": 146,
      "unavailable": {},
      "definitions": {
        "applications": "投递看板中未归档的卡片总数（含 wishlist：想看但还没投的也算在跟）。",
        "interviews": "当前处于面试阶段的卡片数（interview + final + offer）——这是看板快照，不是「曾经进过面试」的漏斗口径；漏斗按事件流统计，见 PHASE 9 的 /analytics。",
        "offers": "当前状态为 offer 的卡片数。",
      },
    },
  },
}
```

### 2.12 AI 可观测性与成本 `/ai-runs` `/ai-costs`

> **状态：已实现（PHASE 11；前端页面为 PHASE 11b）** — 7 个端点，表见 `docs/DATABASE.md` §2.11。
> **在此之前 `llm_calls` 与 `ai_caches` 只有表、没有写入方**：`agent_runs` 由执行器写入，但单次模型
> 调用从未落库，`/cache/stats` 读的是一张空表。现在每次模型调用记一行，缓存事件在**拥有事务的那个
> 请求结束时**统一写入（`RunRecorder`）——不在代理深处另开连接，PHASE 2 的 `database is locked`
> 就是这么来的。
>
> **报量出来的数，不报估出来的数**：token 与成本取自 provider 自报的用量；延迟取「provider 上报值」
> 与「实测值」的较大者（heuristic 路径不上报延迟，实测 3ms 却写 0 就是让面板说谎）。
> 零 Key 的 heuristic 部署**真的不产生 token**：`/ai-costs` 因此返回 0，并在 `notes` 里说明原因，
> 而不是编一个看起来像支出的数字。
> **已知缺口（如实记录）**：多数 Agent 走 `structured_output`，其 provider 只返回解析后的 schema、
> 丢掉用量信封，因此那条路径**没有 token 可记**——这是核心接口自身的限制，不是计量漏了。该路径仍
> 记录延迟、provider 与 prompt 版本；`chat` 路径的 token/成本有测试覆盖。
>
> **两种缓存分开报告**：`agent_runs.cache_hit` 是执行器的**步骤缓存**；`/cache/stats` 的命中率是
> **provider 缓存**（进程级、跨请求共享）。任一种命中都会把 run 的 `cache_hit` 置真——面板说「未命中」
> 而缓存页说「命中」是自相矛盾的，读者会立刻停止相信两者。`ai_caches` 是持久层（重启后仍在），
> 进程计数器是当下状态，两者**并列**而非混算；`hitRate` 在尚无任何查询时是 `null`（空缓存没有命中率，
> 报 0.0 会被读成「缓存从来不帮忙」）。
>
> **预算护栏已接线**：`Budget(daily_usd=ai_daily_budget_usd)` 随 provider chain 在启动时构建；超支时
> `RoutedProvider` 抛 `BudgetExceededError`，由韧性层降级到链上的下一个 provider（绝不 500）。
> `/ai-costs` 回报同一个上限——护栏与看板读同一个数字。
> 没有 owner 的运行（种子、定时任务）也会列出：问「这台部署花了多少」的人需要全貌。

| 方法 | 路径                   | 说明                                                    |
| ---- | ---------------------- | ------------------------------------------------------- |
| GET  | `/ai-runs`             | 列表（`?agent=&workflow=&status=&sinceHours=`）✅       |
| GET  | `/ai-runs/{id}`        | 详情（步骤链 + 逐次模型调用；摘要是 digest 不是原文）✅ |
| GET  | `/ai-costs`            | 日 token 用量 / 成本 + 合计与预算上限 ✅                |
| GET  | `/ai-costs/by-agent`   | 每 Agent 成本、次数、平均延迟、缓存命中 ✅              |
| GET  | `/ai-costs/by-feature` | 每功能（JD 分析 / 简历优化 / 面试…）成本 ✅             |
| GET  | `/cache/stats`         | 三类缓存的条目与命中率（持久层 + 进程）✅               |
| GET  | `/prompts`             | Prompt Registry 列表（name/version/sha/isActive）✅     |

```jsonc
// GET /ai-runs?limit=1 → 200（真机实测：零 Key 路径）
{ "success": true, "data": { "items": [ {
    "id": "uuid-run", "workflow": "jd_analysis", "agent": "job", "status": "degraded",
    "provider": "heuristic", "model": null, "promptVersion": "jd_analysis@v1",
    "totalTokens": 0, "costUsd": 0.0, "latencyMs": 93, "cacheHit": false,
    "stepCount": 4 } ], "total": 2, "limit": 1, "offset": 0 } }

// GET /cache/stats → 200（两次相同请求之后：一次未命中、一次命中）
{ "success": true, "data": {
    "byKind": [ {"kind":"llm","entries":1,"hits":3,"bytes":824},
                {"kind":"embedding","entries":0,"hits":0,"bytes":0},
                {"kind":"tool","entries":0,"hits":0,"bytes":0} ],
    "persistedHits": 3,
    "process": { "processHits": 3, "processMisses": 2, "processEntries": 1,
                 "eventsFlushed": 6, "hitRate": 0.6 } } }
```

### 2.13 公开候选人页与分享 `/public`

> **状态：已实现（PHASE 10）** — 4 个端点，表见 `docs/DATABASE.md` §2.1（迁移 `0008`）。
> **两个无认证端点是有意为之**：招聘方打开一个分享链接不该先注册账号，需要登录的页面不是可分享的页面。
> 它们能返回的一切都已经在服务端过滤与脱敏 —— 端点里没有任何「仅所有者可见」的字段可以泄漏。
>
> **未知 slug 与未发布都返回 404**，不区分：区分它们等于告诉陌生人哪些 slug 存在。
> slug 由服务端生成（`候选人名-<不透明后缀>`）；后缀不是装饰，它是防止「按名字枚举候选人」的唯一屏障。
> 已存在的 slug 会保留（分享链接不能变），种子账号的 `alex` 即属此类。
>
> **隐私开关在读取时套用，不在发布时**：候选人关掉某个板块后，**下一次打开就是新状态**，
> 不需要重新发布 —— 「我刚关掉」与「它真的关掉了」之间的窗口正是泄漏会发生的地方。
> 默认关闭 `contact` 与 `resume_file`：公开证据与公开电话号码是两件事。
>
> **PII 扫描跑两遍**：RecruiterAgent 构建时脱敏一次，服务端在**即将返回的响应上**再扫一次。
> 两次的理由是不对称：漏一次就是把候选人的手机号公开发布，误报一次只是多一个掩码。
> 发布时扫到的内容记录在 `pii_findings` 里并回给候选人本人（`GET /public/settings`）——
> 悄悄删掉一处电话与本来就没有电话，是两件不同的事。
>
> **公开页的每次访问不产生模型调用**：叙述部分（summary / highlights / interview topics）在
> 发布时生成并存入 `public_payload`，读取时只做确定性过滤。招聘方刷新页面不该让候选人付费。
> `storage_scope=local` 的账号**不能发布**（403）：公开 URL 与「数据不出本机」互相矛盾。
> 未被解析出技能、或来源是本地文件时，技能仍会显示但引用为空——页面会说明原因，而不是显示空白。

| 方法  | 路径                                          | 认证 | 说明                                          |
| ----- | --------------------------------------------- | ---- | --------------------------------------------- |
| GET   | `/public/candidate/{slug}`                    | —    | 公开画像（受 `sections` 控制，自动 PII 脱敏） |
| POST  | `/public/publish`                             | ✅   | 发布/取消发布（发布时重新生成叙述）           |
| GET   | `/public/settings`                            | ✅   | 发布状态、分享链接、逐项开关、已脱敏清单      |
| PATCH | `/public/settings`                            | ✅   | 逐项可见性 + 逐技能隐藏列表                   |
| GET   | `/public/candidate/{slug}/evidence/{skillId}` | —    | 某技能的公开证据（Recruiter View 点击展开）   |

```jsonc
// GET /public/candidate/alex → 200（真机实测：简历里带邮箱，公开页里没有）
{
  "success": true,
  "data": {
    "displayName": "Alex Chen",
    "headline": "Embedded firmware engineer",
    "skills": [
      {
        "canonicalId": "stm32",
        "displayName": "STM32",
        "category": "embedded",
        "confidence": 0.9,
        "evidenceCount": 3,
        "corroboration": 2,
        "evidence": [],
      },
    ],
    "projects": [],
    "highlights": [],
    "interviewTopics": [],
    "contact": {},
    "meta": {
      "slug": "alex",
      "evidenceCoverage": 1.0,
      "profileStrength": 41.0,
      "hiddenSections": ["contact", "resume_file"],
      "redactions": [],
      "viewCount": 4,
    },
  },
}
```

### 2.14 系统与搜索 `/system` `/search` `/tasks`

| 方法 | 路径                 | 说明                                                                 |
| ---- | -------------------- | -------------------------------------------------------------------- |
| GET  | `/system/health`     | API / DB / Redis / Vector / LLM provider 状态                        |
| GET  | `/system/info`       | 版本、构建时间、commit hash、Python/Node 版本、provider 配置（脱敏） |
| GET  | `/search?q=FreeRTOS` | 全局搜索：分组返回 skills / projects / evidence / jobs / interviews  |
| GET  | `/tasks/{id}`        | 异步任务状态                                                         |
| GET  | `/tasks/{id}/stream` | 任务进度 SSE                                                         |
| POST | `/tasks/{id}/cancel` | 取消任务                                                             |

```jsonc
// GET /search?q=FreeRTOS → 200
{
  "success": true,
  "data": {
    "query": "FreeRTOS",
    "groups": [
      {
        "type": "skill",
        "items": [{ "id": "uuid-s", "label": "FreeRTOS", "evidenceCount": 9, "confidence": 0.94 }],
      },
      {
        "type": "project",
        "items": [{ "id": "uuid-p", "label": "Balance Robot", "matchScore": 0.91 }],
      },
      {
        "type": "evidence",
        "items": [
          { "id": "uuid-e", "label": "freertos.c", "kind": "repo_file", "relevance": 0.94 },
        ],
      },
      {
        "type": "job",
        "items": [{ "id": "uuid-j", "label": "Embedded Engineer @ 某科技", "mentions": 2 }],
      },
    ],
    "total": 14,
    "meta": { "tookMs": 38 },
  },
}
```

---

## 3. 契约与代码生成

| 项           | 做法                                                                             |
| ------------ | -------------------------------------------------------------------------------- |
| 单一事实来源 | Pydantic Schema → OpenAPI 3.1 → 前端类型自动生成                                 |
| 生成命令     | `pnpm gen:api`（`openapi-typescript` + 轻量 fetch 客户端封装）                   |
| CI 校验      | `pnpm gen:api && git diff --exit-code` —— 契约漂移即失败                         |
| 版本兼容     | `/api/v1` 路径版本；破坏性变更升 `/v2`；`meta.algorithmVersion` 标记评分算法版本 |
| 前端校验     | 关键响应用 zod 二次校验（防后端异常返回导致 UI 崩溃）                            |

---

## 4. 示例：完整调用链（面试演示）

```bash
# 1) Demo 登录
curl -s -X POST localhost:8000/api/v1/auth/demo | jq -r .data.accessToken

# 2) 分析 JD
curl -s -X POST localhost:8000/api/v1/jobs/analyze \
  -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"text":"Embedded Software Engineer ... 熟悉 STM32/FreeRTOS/CAN ..."}' | jq .data.id

# 3) 匹配
curl -s -X POST localhost:8000/api/v1/jobs/$JOB/match -H "Authorization: Bearer $T" | jq .data.score

# 4) 验证一句可能有问题的简历描述（唯一门禁路径，见 §2.5）
curl -s -X POST localhost:8000/api/v1/evidence/validate \
  -H "Authorization: Bearer $T" -H 'Content-Type: application/json' \
  -d '{"text":"优化系统性能，提升 70%"}' | jq '.data.claim.status, .data.claim.safeRewrite.text, .data.degraded'

# 5) 打开证据图谱（stm32 子图）
curl -s "localhost:8000/api/v1/evidence-graph?focus=skill:stm32&depth=2" \
  -H "Authorization: Bearer $T" | jq '.data.meta'
```

---

**下一篇**：[UI.md](./UI.md)
