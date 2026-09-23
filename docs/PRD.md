# CareerForge AI · 产品需求文档（PRD）

| 字段         | 值                                                                                                                                                                        |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 文档版本     | v1.0                                                                                                                                                                      |
| 阶段         | PHASE 0（产品设计）                                                                                                                                                       |
| 状态         | ✅ Frozen for v1.0.0                                                                                                                                                      |
| 对应代码版本 | `v1.0.0`                                                                                                                                                                  |
| 关联文档     | [ARCHITECTURE.md](./ARCHITECTURE.md) · [DATABASE.md](./DATABASE.md) · [API.md](./API.md) · [UI.md](./UI.md) · [ROADMAP.md](./ROADMAP.md) · [DECISIONS.md](./DECISIONS.md) |

---

## 1. 一句话定位

> **CareerForge AI 是一个 Evidence-Driven（证据驱动）的 AI 求职操作系统：把散落在简历、GitHub、项目代码、文档与面试记录里的真实经历，锻造为可追溯、可验证、可复用的求职证据资产。**

中文副标题：**把经历变成证据，把证据变成竞争力。**
英文副标题：_Turn your experience into verifiable career evidence._

品牌核心句（Landing Page 彩蛋位）：

> Most resumes describe what you **claim** to know.
> CareerForge shows the **evidence**.
>
> 大多数简历告诉别人你会什么，CareerForge 告诉别人你凭什么这么写。

---

## 2. 问题定义（Why this exists）

### 2.1 求职者的真实痛点

| #   | 痛点                  | 现状                                                                     | 后果                                                     |
| --- | --------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------- |
| P1  | **经历碎片化**        | 简历在 Word、项目在 GitHub、文档在网盘、实习记录在邮箱、面试复盘在备忘录 | 每次投递都要从零重组，信息大量丢失                       |
| P2  | **不会"翻译"经历**    | 知道"我做过电机控制"，不知道如何写成 JD 看得懂的话                       | 简历通过率低，且无法解释自己做了什么                     |
| P3  | **AI 简历工具会胡编** | 主流工具直接让 LLM 生成"熟练掌握 Redis / 性能提升 50%"                   | 面试一问就穿帮，属于**负资产**：伪造简历在背调中直接出局 |
| P4  | **匹配度是黑盒**      | 工具输出"匹配度 90%"，无法解释依据                                       | 用户无法据此行动，只能继续海投                           |
| P5  | **缺少闭环**          | 简历工具、面试题库、投递看板、技能学习分散在不同 App                     | 面试失败的原因无法回溯，同样的坑反复踩                   |
| P6  | **无法证明**          | 简历说"熟悉 STM32"，招聘方无从验证                                       | 校招/社招中"看起来一样"的候选人之间无法区分              |

### 2.2 核心洞察

**LLM 让"写得漂亮"变成了零成本，于是"能否证明"成了唯一的稀缺资源。**

因此产品护城河不是 Prompt，而是**证据基础设施**：

- 把候选人的真实材料（代码、提交、文档、经历）沉淀为**结构化证据**
- 让每一句简历描述都能回溯到具体证据
- 让匹配、优化、面试推荐都建立在同一份证据地基上

### 2.3 竞品对比

| 维度               | 传统简历工具（Rezi / Kickresume / 各类 AI 简历） | 通用 LLM Chatbot | **CareerForge AI**                                          |
| ------------------ | ------------------------------------------------ | ---------------- | ----------------------------------------------------------- |
| 生成简历           | ✅                                               | ✅               | ✅                                                          |
| 生成内容可追溯     | ❌                                               | ❌               | ✅ **Claim → Evidence 逐条溯源**                            |
| 事实性防御         | ❌ 会直接编造                                    | ❌               | ✅ **Claim Validator + Confidence 门禁**                    |
| 匹配度可解释       | ❌ 单一百分比                                    | ⚠️ 口头解释      | ✅ **5 维加权评分 + "Why 86?" 展开**                        |
| 读取真实代码证据   | ❌                                               | ⚠️ 手动粘贴      | ✅ **GitHub Intelligence（文件级/commit 级）**              |
| 模拟面试个性化     | ❌ 通用题库                                      | ⚠️ 无记忆        | ✅ **基于 JD + 证据图谱的自适应难度面试**                   |
| 求职数据分析       | ❌                                               | ❌               | ✅ **Funnel/Sankey + 技能-面试率相关性**                    |
| 关掉 AI 是否还能用 | ⚠️ 完全不可用                                    | ❌ 完全不可用    | ✅ **Profile / Graph / Tracker / Analytics 均为纯软件能力** |

---

## 3. 目标用户

### 3.1 主要画像（Primary）

| 画像                      | 描述                                              | 关键诉求                                     |
| ------------------------- | ------------------------------------------------- | -------------------------------------------- |
| **U1 校招应届生（核心）** | 计算机/电子/自动化本科硕，有 2–5 个项目、1 段实习 | "我做了很多，但不知道怎么讲，也不知道差在哪" |
| **U2 嵌入式/硬件工程师**  | STM32 / FreeRTOS / 驱动 / 机器人 / 无人机方向     | 技术深但简历表达弱；需要项目深挖与证据化表达 |
| **U3 AI / 后端工程师**    | 有 GitHub 活跃度，但项目零散                      | 需要把仓库自动变成绩效化的能力证明           |
| **U4 转行者**             | 非科班转码，经历与岗位错位                        | 需要技能缺口矩阵与 30 天补强路径             |

### 3.2 次要画像（Secondary）

- **U5 面试官 / 招聘方**：通过 `Recruiter View` 公开候选人页查看**可点击验证**的交互式简历（P6 的解法）。
- **U6 求职教练 / 学校就业中心**：只读查看学员画像与投递漏斗。

### 3.3 JTBD（Jobs To Be Done）

| 场景   | 用户想要的进展                             | CareerForge 的交付                                     |
| ------ | ------------------------------------------ | ------------------------------------------------------ |
| JTBD-1 | "我想把散落的经历一次性整理成结构化的自己" | 上传简历/文档 + 绑定 GitHub → Candidate Knowledge Base |
| JTBD-2 | "我想知道这个岗位我到底行不行，为什么"     | JD 分析 → 可解释匹配评分 → Strengths / Gaps / Unknown  |
| JTBD-3 | "我想让简历针对这个岗位变强，但绝不想编造" | Resume Copilot + Evidence Validator 门禁               |
| JTBD-4 | "我想在没有真实面试前先被打一遍"           | 自适应模拟面试 + 七维 Scorecard                        |
| JTBD-5 | "我想知道面试为什么挂了，下次怎么改"       | 复盘记录 + Career Analytics + AI Career Memory         |
| JTBD-6 | "我想让招聘方相信我写的东西是真的"         | Share Profile → 公开证据页（Interactive Resume）       |

---

## 4. 核心创新：Career Evidence Graph（求职证据图谱）

### 4.1 定义

**Evidence Graph 是一张以"候选人能力断言"为中心的有向异构图**：左侧是用户的真实材料（Source），右侧是简历上的每一句能力断言（Claim），中间由证据节点与置信度连接。

```mermaid
graph LR
  C[Candidate] -->|has| E1[Experience: 实习 @ 某公司]
  C -->|has| P1[Project: Balance Robot]
  C -->|has| P2[Project: UAV Control System]
  C -->|owns| R1[Repository: stm32-balance-car]
  R1 -->|contains| F1["motor_control.c"]
  R1 -->|contains| F2["freertos.c"]
  R1 -->|produces| CM1["commit #abc123"]
  P1 -->|evidenced_by| F1
  P1 -->|evidenced_by| F2
  P1 -->|evidenced_by| CM1
  P1 -->|demonstrates| S1[Skill: STM32]
  P1 -->|demonstrates| S2[Skill: FreeRTOS]
  E1 -->|demonstrates| S1
  S1 -->|supports| CL1["Claim: 基于 STM32+FreeRTOS 开发实时控制系统"]
  CL1 -->|confidence| SC["0.92"]
```

### 4.2 节点与边（v1.0）

| 节点类型      | 说明                           | 主要来源                  |
| ------------- | ------------------------------ | ------------------------- |
| `candidate`   | 候选人根节点                   | 用户                      |
| `education`   | 教育经历                       | 简历解析                  |
| `experience`  | 实习/工作经历                  | 简历解析                  |
| `project`     | 项目                           | 简历 / 文档 / GitHub      |
| `achievement` | 获奖、比赛、证书               | 简历解析                  |
| `repository`  | GitHub 仓库                    | GitHub API                |
| `repo_file`   | 仓库文件（文件级证据）         | GitHub API                |
| `commit`      | 提交记录                       | GitHub API                |
| `document`    | 上传文档（简历/项目说明/面经） | 上传                      |
| `skill`       | 技能（规范化的 skill_id）      | 抽取 + 归一化             |
| `claim`       | 简历断言（一句话描述）         | Resume Copilot / 用户手写 |
| `job`         | 岗位 JD                        | JD 分析                   |
| `interview`   | 面试场次                       | 面试模拟/复盘             |

| 边类型         | 语义                | 示例                                      |
| -------------- | ------------------- | ----------------------------------------- |
| `HAS`          | 候选人 → 实体       | `Candidate -HAS-> Project`                |
| `DEMONSTRATES` | 实体 → 技能         | `Project -DEMONSTRATES-> STM32`           |
| `EVIDENCED_BY` | 实体/断言 → 证据源  | `Project -EVIDENCED_BY-> motor_control.c` |
| `SUPPORTS`     | 证据 → 断言         | `freertos.c -SUPPORTS-> Claim`            |
| `REQUIRES`     | 岗位 → 技能         | `Job -REQUIRES-> CAN`                     |
| `MATCHES`      | 技能 → 岗位技能     | `Skill:STM32 -MATCHES-> Job.required#3`   |
| `GAP`          | 岗位技能 → 缺失技能 | `Job -GAP-> AUTOSAR`                      |
| `DERIVED_FROM` | 派生溯源            | `Claim -DERIVED_FROM-> Document#p12`      |

### 4.3 Evidence Confidence（置信度算法，**确定性、可复现、非 LLM 拍脑袋**）

```
confidence = 0.30·source_authority
           + 0.15·recency
           + 0.20·specificity
           + 0.20·corroboration
           + 0.15·extraction_quality
```

| 子项                 | 取值范围 | 计算规则                                                                                       |
| -------------------- | -------- | ---------------------------------------------------------------------------------------------- |
| `source_authority`   | 0–1      | `commit/file = 1.00`，`README = 0.85`，`上传文档 = 0.80`，`简历自述 = 0.55`，`LLM 推断 = 0.35` |
| `recency`            | 0–1      | `exp(-age_days / 540)`，540 天半衰尺度；无时间信息取 0.6                                       |
| `specificity`        | 0–1      | 行级/文件级 = 1.00，仓库级 = 0.75，段落级 = 0.6，整篇文档级 = 0.45                             |
| `corroboration`      | 0–1      | `min(1.0, 0.4 + 0.2 × 独立来源数)`                                                             |
| `extraction_quality` | 0–1      | 确定性解析器 = 1.00，LLM 结构化抽取 = 0.70，正则/启发式 = 0.50                                 |

**为什么重要**：这是产品可信度的地基。它让"AI 说 92% 可信"变成**可审计的加权公式**，而不是模型随口给的数字 —— 面试官可以直接读代码复现。

### 4.4 Claim 判定分级

| 判定                  | 条件                                              | 系统行为                                                    |
| --------------------- | ------------------------------------------------- | ----------------------------------------------------------- |
| `SUPPORTED`           | confidence ≥ 0.75 且 ≥ 2 个独立来源               | ✅ 允许写入简历，展示证据徽章                               |
| `PARTIALLY_SUPPORTED` | 0.45 ≤ confidence < 0.75 或仅 1 个来源            | ⚠️ 显示 **Weak Evidence**，给出更保守表述建议               |
| `UNSUPPORTED`         | confidence < 0.45 或零证据                        | ⛔ **Rejected Claim**，禁止写入简历，给出"如何补证据"的指引 |
| `CONTRADICTED`        | 证据与断言冲突（如声称 70% 提升但无任何性能数据） | ⛔ 拒绝 + 标记风险，写入 `claim_validations` 供复盘         |

---

## 5. 功能需求（Functional Requirements）

> 优先级：**P0 = v1.0 必须交付**，**P1 = v1.x**，**P2 = 加分项**

### FR-1 认证与 Demo 体验（P0）

| ID     | 需求                       | 验收标准                                                                                        |
| ------ | -------------------------- | ----------------------------------------------------------------------------------------------- |
| FR-1.1 | JWT 认证（注册/登录/刷新） | bcrypt 哈希；access token 30min，refresh 7d；401/403 语义正确                                   |
| FR-1.2 | 一键 Demo 登录             | `demo@careerforge.ai` 免密进入，进入即为**完整种子数据**，任何页面都不得为空状态                |
| FR-1.3 | 数据隔离                   | 所有查询强制 `user_id` 作用域；跨用户访问返回 404 而非 403（不泄露存在性）                      |
| FR-1.4 | Local Mode（隐私优先）     | 用户可开启；开启后简历原文不出本机（仅存储解析结果与向量），API 响应标注 `storage_scope: local` |

### FR-2 AI Career Profile / Candidate Knowledge Base（P0）

| ID     | 需求       | 验收标准                                                                                                          |
| ------ | ---------- | ----------------------------------------------------------------------------------------------------------------- |
| FR-2.1 | 多格式导入 | 支持 PDF / DOCX / MD / TXT；单文件 ≤ 10MB；MIME 与魔数双重校验                                                    |
| FR-2.2 | 结构化抽取 | 输出 `CandidateProfile{ education[], experience[], project[], skill[], achievement[] }`，**全部经 Pydantic 校验** |
| FR-2.3 | 实体归一化 | 技能归一化到规范 id（`stm32`、`freertos`、`c`、`can`…），别名表驱动（`STM32F407`→`stm32`）                        |
| FR-2.4 | 导入进度   | 长任务必须流式反馈阶段（`parsing → extracting → normalizing → embedding → graphing`），禁止裸 Spinner             |
| FR-2.5 | 可编辑     | 抽取结果逐条可编辑；用户修改标记 `origin=user_corrected`，权重高于 LLM 抽取                                       |

### FR-3 GitHub Intelligence（P0）

| ID     | 需求             | 验收标准                                                                                                         |
| ------ | ---------------- | ---------------------------------------------------------------------------------------------------------------- |
| FR-3.1 | 仓库拉取         | 输入 username → 仓库列表、star、语言占比、topics、README、提交活动                                               |
| FR-3.2 | 技术栈画像       | 输出语言占比 + `EngineeringProfile`（如 Embedded Systems / Backend / AI Applications）+ 置信度                   |
| FR-3.3 | 项目亮点自动识别 | 从 README + 文件树识别技术要素（FreeRTOS / PID / UART DMA / IMU / Encoder…）并生成 `Project Intelligence Report` |
| FR-3.4 | 文件级证据       | 关键文件与 commit 成为 `repo_file`/`commit` 证据节点，进入 Evidence Graph                                        |
| FR-3.5 | 降级可用         | 无 GitHub Token 时使用匿名 API + 限流退避；完全离线时可用**内置快照 fixture** 跑通全流程                         |
| FR-3.6 | 速率与缓存       | 结果按 `username + etag` 缓存 ≥ 6h；`GitHubRateLimitError` 明确提示剩余额度与重置时间                            |

### FR-4 Evidence Graph 可视化（P0，项目视觉核心）

| ID     | 需求         | 验收标准                                                                                    |
| ------ | ------------ | ------------------------------------------------------------------------------------------- |
| FR-4.1 | 交互式图谱   | React Flow 渲染；支持缩放/拖拽/框选/布局切换（层次 / 力导向）                               |
| FR-4.2 | 节点下钻     | 点击任意节点 → 右侧 Drawer 显示 Evidence / Confidence / Source / Last Updated / AI Analysis |
| FR-4.3 | 断言溯源路径 | 选择 Claim → 高亮其全部支持路径（Source → Evidence → Claim）                                |
| FR-4.4 | 过滤与搜索   | 按节点类型、技能、项目、时间范围过滤；全局搜索直达节点                                      |
| FR-4.5 | 性能         | 1000 节点 / 2000 边以内首屏 ≤ 2s；超出时服务端预聚合 + 分页加载                             |
| FR-4.6 | 可分享       | 支持导出 PNG；生成只读深度链接 `/app/evidence-graph?focus=skill:stm32`                      |

### FR-5 JD Intelligence（P0）

| ID     | 需求          | 验收标准                                                                                                                                                                |
| ------ | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-5.1 | JD 结构化解析 | 输出 `JDAnalysis{ company, role, level, location, education, required_skills[], preferred_skills[], bonus_skills[], responsibilities[], keywords[], years_experience }` |
| FR-5.2 | 三种输入      | 粘贴文本 / 上传文件 / 岗位链接（链接模式为 P1）                                                                                                                         |
| FR-5.3 | JD Skill Tree | 前端展示 Required / Preferred / Bonus 三层技能树，每项标注 JD 原文出处句                                                                                                |
| FR-5.4 | 解析稳健性    | 缺字段不崩；脏输入（含 HTML、超长行、乱码）有明确降级；解析失败回退启发式关键词抽取                                                                                     |
| FR-5.5 | 基准可测      | 内置 100+ 条标注 JD 数据集，可一键跑准确率基准（见 FR-14）                                                                                                              |

### FR-6 可解释 Job Match Score（P0）

| ID     | 需求         | 验收标准                                                                                                    |
| ------ | ------------ | ----------------------------------------------------------------------------------------------------------- |
| FR-6.1 | 5 维加权评分 | `Skill 40% + Experience 25% + Project 20% + Education 5% + Evidence Strength 10%`，权重可配置且写入配置中心 |
| FR-6.2 | 确定性可复现 | 同一输入两次运行评分完全一致（LLM 仅参与软性叙述，不参与数值）                                              |
| FR-6.3 | 依据可展开   | "Why 86?" 展开显示每维得分、公式、贡献证据 id 与缺口清单                                                    |
| FR-6.4 | 分级输出     | 输出 `strengths[]`（已具备且证据充分）、`gaps[]`（岗位要求但缺失）、`unknown[]`（无法判定，需用户确认）     |
| FR-6.5 | 三态语义     | `unknown` 必须与 `gap` 区分，避免把"简历没写"误判为"不会"                                                   |

### FR-7 Resume Copilot（P0）

| ID     | 需求       | 验收标准                                                                     |
| ------ | ---------- | ---------------------------------------------------------------------------- |
| FR-7.1 | 简历 Diff  | 左右并排展示 Original / Optimized，逐条 bullet 级 diff，支持接受/拒绝单条    |
| FR-7.2 | 生成即验证 | 每条生成内容**必须**经过 Claim Validator；未通过不得进入可接受区             |
| FR-7.3 | 状态徽章   | `Supported` / `Weak Evidence` / `Rejected Claim` 三态徽章 + 悬浮显示证据来源 |
| FR-7.4 | 版本管理   | 每次优化生成 `resume_version`，可对比、可回滚、可标注投递用途（关联 job）    |
| FR-7.5 | 安全改写   | 对 Unsupported 断言，给出**降级到有证据支撑**的改写建议，而非简单拒绝        |
| FR-7.6 | 导出       | 导出 Markdown / PDF（PDF 为 P1），导出内容与页面状态一致                     |

### FR-8 AI Resume Claim Validator（P0）

| ID     | 需求     | 验收标准                                                                                     |
| ------ | -------- | -------------------------------------------------------------------------------------------- |
| FR-8.1 | 单句验证 | 输入一句话 → 返回判定 + Confidence + Sources + 安全改写建议                                  |
| FR-8.2 | 全图检索 | 检索范围覆盖 Project / GitHub / Documents / Evidence Graph                                   |
| FR-8.3 | 数字防御 | 断言含量化数字（`70%`、`3 倍`）但证据中无任何量化支撑 → 直接 `CONTRADICTED` 或 `UNSUPPORTED` |
| FR-8.4 | 独立页面 | `/app/validator` 提供自由试玩，面试官可现场输入进行对抗测试                                  |
| FR-8.5 | 可解释   | 展示命中的证据片段、检索分数、检索通道（semantic / keyword / metadata）                      |

### FR-9 Skill Gap Analysis & 30 天计划（P0）

| ID     | 需求       | 验收标准                                                                    |
| ------ | ---------- | --------------------------------------------------------------------------- |
| FR-9.1 | 缺口矩阵   | `Required Skill                                                             | User Level | Evidence | Gap Level`，Level 由证据驱动（Strong/Moderate/Basic/None） |
| FR-9.2 | 计划生成   | 输出 4 周计划，每周有目标、资源类型、产出物、验收方式                       |
| FR-9.3 | 补简历项目 | **每个缺口技能必须给出一个 Mini Project**（可写进简历的产出），而非教程链接 |
| FR-9.4 | 缺口优先级 | 优先级由"岗位出现频次 × 缺口严重度"决定，并展示依据（哪些 job 要求它）      |

### FR-10 Interview Simulator（P0）

| ID      | 需求       | 验收标准                                                                                  |
| ------- | ---------- | ----------------------------------------------------------------------------------------- |
| FR-10.1 | 六种模式   | HR / Technical / Project / Stress / Behavioral / System Design                            |
| FR-10.2 | 个性化出题 | 题目基于 JD + Resume + GitHub + Project + Evidence Graph 动态生成，禁止纯通用题库         |
| FR-10.3 | 自适应难度 | L1 概念 → L2 工程 → L3 Debugging/权衡；答对升级，答错降级并追问                           |
| FR-10.4 | 流式交互   | 出题与评分流式输出（SSE），首 token ≤ 1.5s（有 Key）/ 即时（heuristic provider）          |
| FR-10.5 | 追问链     | 每个技术主题支持 ≥ 3 层追问（为什么用 → Task/ISR 通信 → Queue vs Semaphore → 优先级反转） |
| FR-10.6 | 场景题     | 支持"给定逻辑分析仪波形/日志，判断问题"类工程场景题                                       |

### FR-11 Interview Scorecard（P0）

| ID      | 需求        | 验收标准                                                                                                                |
| ------- | ----------- | ----------------------------------------------------------------------------------------------------------------------- |
| FR-11.1 | 七维评分    | Technical Accuracy / Communication / Depth / Problem Solving / Engineering Thinking / Confidence / Evidence Consistency |
| FR-11.2 | Radar Chart | 七维雷达图 + 与历史场次对比                                                                                             |
| FR-11.3 | 逐题复盘    | 每题标注 Strong Answer / Weak Answer / Missing Knowledge / Suggested Answer / Follow-up Topics                          |
| FR-11.4 | 证据一致性  | `Evidence Consistency` 检测"面试口述内容与简历/证据图谱冲突"，冲突项单独列出（**独家能力**）                            |
| FR-11.5 | 报告导出    | 导出 Markdown 面试报告                                                                                                  |

### FR-12 Project Deep Dive Mode（P0）

| ID      | 需求     | 验收标准                                                                                                            |
| ------- | -------- | ------------------------------------------------------------------------------------------------------------------- |
| FR-12.1 | 项目档案 | 选择一个项目 → 生成 Architecture / Timeline / Key Challenges / Technical Decisions / Debugging Stories / Trade-offs |
| FR-12.2 | 架构图   | 自动生成 Mermaid 架构图（Sensor → MCU → Control → Comm → Upper Computer）                                           |
| FR-12.3 | 面试题库 | 按项目生成可能被问的问题 + 参考答题骨架（基于证据，不虚构细节）                                                     |
| FR-12.4 | 缺口提示 | 标注"项目中无法从证据确认的细节"，提醒用户面试前补齐（诚信保护）                                                    |

### FR-13 Application Tracker（P0）

| ID      | 需求     | 验收标准                                                                        |
| ------- | -------- | ------------------------------------------------------------------------------- |
| FR-13.1 | 看板     | Wishlist / Applied / OA / Interview / Final / Offer / Rejected 七列，拖拽改状态 |
| FR-13.2 | 乐观更新 | 拖拽立即生效 + 失败回滚 + Toast 提示                                            |
| FR-13.3 | 卡片信息 | Company / Role / Location / Salary / Status / Match Score / Date / Notes        |
| FR-13.4 | 时间线   | 每个岗位记录状态变更历史（`application_events`）                                |
| FR-13.5 | 一键关联 | 从 JD 分析结果直接"加入投递"                                                    |

### FR-14 Career Analytics（P0）

| ID      | 需求         | 验收标准                                                                              |
| ------- | ------------ | ------------------------------------------------------------------------------------- |
| FR-14.1 | 漏斗图       | Applications → Replies → Interviews → Finals → Offers（Funnel/Sankey）                |
| FR-14.2 | 核心比率     | Interview Rate / Offer Rate / Response Rate / Average Match Score                     |
| FR-14.3 | 相关性分析   | 技能 → 面试成功率关联（含样本量与显著性说明，样本不足时明确标注"样本不足，仅供参考"） |
| FR-14.4 | 最佳岗位类别 | 按岗位类别/技术栈分组统计表现                                                         |
| FR-14.5 | 时间维度     | 支持 7d / 30d / 90d / all 切换                                                        |

### FR-15 AI Observability & Cost Control（P0）

| ID      | 需求         | 验收标准                                                                                      |
| ------- | ------------ | --------------------------------------------------------------------------------------------- |
| FR-15.1 | AI Runs 页面 | 展示 Agent / Model / Tokens / Latency / Cost / Status / Prompt Version，可按 Agent 与时间过滤 |
| FR-15.2 | Trace 下钻   | 单次 run 展开完整步骤链（每步输入摘要、输出摘要、耗时、token）                                |
| FR-15.3 | 成本看板     | 日 token 用量、每 Agent 成本、每功能成本、缓存命中率                                          |
| FR-15.4 | 三级缓存     | Prompt 结果缓存 / Embedding 缓存 / Tool 结果缓存，命中率可见可测                              |
| FR-15.5 | 成本护栏     | 单用户日预算与单次请求 token 上限；超限降级到 heuristic provider 并明确提示                   |

### FR-16 Recruiter View / Shareable Career Profile（P0，第二亮点）

| ID      | 需求     | 验收标准                                                |
| ------- | -------- | ------------------------------------------------------- |
| FR-16.1 | 公开页   | `/candidate/{slug}` 无需登录可访问                      |
| FR-16.2 | 证据交互 | 点击技能 → 展开证据（仓库、文件、commit、项目）         |
| FR-16.3 | 隐私开关 | 用户逐项控制公开内容；邮箱/电话/原始简历默认**不公开**  |
| FR-16.4 | 隐私脱敏 | 导出与公开页均经过 PII 扫描（邮箱、手机号、身份证形串） |
| FR-16.5 | 分享     | 一键复制链接 + 生成分享卡片                             |

### FR-17 全局能力（P0）

| ID      | 需求            | 验收标准                                                                                             |
| ------- | --------------- | ---------------------------------------------------------------------------------------------------- |
| FR-17.1 | Command Palette | `Ctrl/Cmd + K`：Analyze JD / Add Job / Start Interview / Upload Resume / Search Skill / 跳转任意页面 |
| FR-17.2 | Global Search   | 一次搜索返回 Skills / Projects / Evidence / Jobs / Interviews 分组结果；键盘可导航；300ms 防抖       |
| FR-17.3 | 主题            | Dark（默认，精心雕琢）/ Light / System；无 FOUC                                                      |
| FR-17.4 | 空/错/载状态    | 每个数据视图必须实现 Skeleton / Empty / Error+Retry 三态                                             |
| FR-17.5 | Error Boundary  | 页面级 + 组件级降级，不白屏                                                                          |

### FR-18 平台与工程（P0）

| ID      | 需求               | 验收标准                                                                                                      |
| ------- | ------------------ | ------------------------------------------------------------------------------------------------------------- |
| FR-18.1 | 一键启动           | `docker compose up` 启动 web/api/postgres/redis/worker 五服务                                                 |
| FR-18.2 | 零 Docker 本地路径 | SQLite + 进程内队列 + heuristic provider，`pnpm dev` + `uvicorn` 可完整跑通                                   |
| FR-18.3 | 种子数据           | `make seed` 生成完整候选人（Alex Chen，含 3 项目 / 9 技能 / 15+ 投递 / 5 面试）                               |
| FR-18.4 | 架构页             | `/architecture` 展示系统架构、Agent 工作流、数据流（面试官专用）                                              |
| FR-18.5 | 系统健康           | `/system` 展示 API / DB / Redis / Vector / LLM provider 状态、版本、commit hash                               |
| FR-18.6 | 评测框架           | `python evals/run.py` 输出 `reports/eval-report.json`，覆盖 JD 抽取 / 断言验证 / 检索 Recall@5 / 面试题相关性 |

### FR-19 加分能力（P2）

| ID      | 需求                                                           |
| ------- | -------------------------------------------------------------- |
| FR-19.1 | Browser Extension：Boss/LinkedIn 一键 Analyze with CareerForge |
| FR-19.2 | VS Code Extension：扫描本地项目自动建立 Project Evidence       |
| FR-19.3 | GitHub App：新 commit 自动更新 Evidence Graph                  |
| FR-19.4 | Career Timeline：2024 项目 → 2025 实习 → 2026 求职 → Offer     |
| FR-19.5 | AI Career Memory：跨场次记忆面试反馈与失败原因                 |

---

## 6. 非功能需求（NFR）

| 类别         | 要求                                                                                                            |
| ------------ | --------------------------------------------------------------------------------------------------------------- |
| **性能**     | 非 AI 页面 P95 API ≤ 300ms；AI 流式首 token ≤ 1.5s；Dashboard 首屏 ≤ 1.5s（LCP）；Evidence Graph 1000 节点 ≤ 2s |
| **可靠性**   | 外部依赖（GitHub / LLM / Redis）全部有超时、重试（指数退避）、熔断与降级路径；任一外部服务不可用不得导致 500    |
| **可观测**   | 每次 AI 调用落库 `llm_calls`；每个工作流落库 `agent_runs` + 步骤链；请求带 `request_id` 贯穿前后端日志          |
| **安全**     | 见 [SECURITY 章节](#9-安全与隐私需求)                                                                           |
| **可访问性** | 键盘可达（含图谱与看板）、焦点可见、ARIA label、对比度 ≥ 4.5:1（正文）、支持 `prefers-reduced-motion`           |
| **响应式**   | 1440 / 1024 / 768 / 375 四档必须验证；图谱页在移动端降级为列表视图                                              |
| **代码质量** | TypeScript `strict`；Python 全量 type hint + mypy；单文件 ≤ 500 行；Ruff + ESLint + Prettier；pre-commit        |
| **可维护**   | Prompt 外置 versioned registry；配置全部环境变量化；ADR 记录关键决策                                            |
| **可测试**   | 后端单测 + 集成测；前端 Vitest；E2E Playwright 覆盖 5 条主链路                                                  |

---

## 7. 关键用户流程（面试演示剧本，3–5 分钟）

| 步  | 页面                  | 动作                               | 期望效果                                                      |
| --- | --------------------- | ---------------------------------- | ------------------------------------------------------------- |
| 1   | `/app/dashboard`      | Demo 登录后落地                    | Profile Strength 82/100、6 个统计卡、技能雷达、高匹配岗位列表 |
| 2   | `/app/jobs/new`       | 粘贴 Embedded Software Engineer JD | 5 阶段进度流式展示 → JD Skill Tree 三层树                     |
| 3   | `/app/jobs/{id}`      | 查看匹配结果                       | Match 86/100，5 维拆解，"Why 86?" 可展开                      |
| 4   | 同页                  | 点击 `STM32`                       | 展开证据：Balance Robot / motor_control.c / commit            |
| 5   | `/app/evidence-graph` | 进入图谱                           | 高亮 Claim → Evidence 溯源路径                                |
| 6   | Drawer                | 查看 GitHub 证据                   | 文件路径、commit hash、最后更新时间、置信度                   |
| 7   | `/app/resume`         | 生成优化                           | Diff 视图，1 条 Rejected Claim（含数字无证据）被拦截          |
| 8   | `/app/validator`      | 现场输入 "提升性能 70%"            | 立刻 Unsupported + 安全改写建议                               |
| 9   | `/app/interview`      | 启动 Technical 面试                | L1 → L2 → L3 自适应追问，答完后 Scorecard 七维雷达            |
| 10  | `/candidate/alex`     | 打开 Recruiter View                | 招聘方视角点击技能看证据                                      |

**剧本设计原则**：第 4、5、6 步是"哇点"（可验证性），第 7、8 步是"别人做不到的点"（防幻觉），第 9 步是"AI 深度"，第 10 步是"产品价值"。

---

## 8. 成功指标

### 8.1 产品指标（Demo 语境下的可测量替代）

| 指标              | 目标                              | 测量方式                                  |
| ----------------- | --------------------------------- | ----------------------------------------- |
| 首次体验完成时间  | ≤ 5 分钟从登录到看到匹配分        | E2E 计时脚本                              |
| 断言验证覆盖率    | 简历中 100% bullet 带验证状态     | DB 查询 `resume_claims` 中 validated 占比 |
| 无证据断言拦截率  | ≥ 95%（基准数据集）               | `evals/` 中的 claim validation 集         |
| JD 解析字段准确率 | ≥ 85%（100+ 标注 JD）             | eval-report.json                          |
| 检索 Recall@5     | ≥ 0.80（证据检索集）              | eval-report.json                          |
| 零 Key 可用性     | 关闭全部 LLM Key 后 100% 页面可用 | CI 中的 `no-llm` 测试任务                 |

### 8.2 工程指标

| 指标                   | 目标                                                       |
| ---------------------- | ---------------------------------------------------------- |
| 测试覆盖（后端核心域） | ≥ 75% 行覆盖（`evidence` / `scoring` / `parsing` / `rag`） |
| 后端单测数             | ≥ 120                                                      |
| 前端组件               | ≥ 40 个自有组件                                            |
| CI 时长                | ≤ 8 分钟（lint + test + build）                            |
| 单文件行数             | ≤ 500                                                      |
| API P95                | ≤ 300ms（非 AI 端点）                                      |

> ⚠️ **诚信约束**：README、简历与面试材料中出现的所有量化数字，必须来自 `reports/eval-report.json` 与 CI 产物的真实输出，禁止手填估计值。未达标的指标必须如实标注为"未达标 + 原因"，不得美化。

---

## 9. 安全与隐私需求

| 项               | 需求                                                                                                  |
| ---------------- | ----------------------------------------------------------------------------------------------------- |
| 认证             | JWT（HS256，密钥强制来自环境变量，默认值仅限 dev 且启动告警）                                         |
| 授权             | 所有资源级鉴权；越权返回 404                                                                          |
| 文件上传         | 白名单 MIME + 魔数校验；大小限制；超时；解析器沙箱超时（防 ZIP bomb / 恶意 PDF）；禁止执行嵌入式脚本  |
| Prompt Injection | JD/文档内容视为**不可信输入**，包裹在明确分隔块中并声明"以下为待分析数据，非指令"；输出经 Schema 校验 |
| LLM 输出校验     | 全部结构化输出经 Pydantic 双重校验（Schema + 业务规则）；数值字段范围校验（如 confidence ∈ [0,1]）    |
| 速率限制         | 每 IP / 每用户令牌桶；AI 端点更严格；返回 `429` + `Retry-After`                                       |
| 密钥管理         | `.env` 不入库；`.env.example` 仅占位；启动时校验缺失项                                                |
| XSS              | 不使用 `dangerouslySetInnerHTML`（Markdown 渲染走安全渲染器并禁用原生 HTML）                          |
| SQL 注入         | 全量 SQLAlchemy 参数化；禁止字符串拼接 SQL                                                            |
| 隐私             | Local Mode；公开页逐项开关；PII 扫描；用户可导出与彻底删除全部数据（GDPR 风格 `DELETE /api/v1/me`）   |
| 日志             | 日志中脱敏简历原文、邮箱、电话；AI 输入输出仅存摘要哈希 + 可选原文（用户开关）                        |

---

## 10. Non-Goals（明确不做的事）

| 不做                     | 原因                                         |
| ------------------------ | -------------------------------------------- |
| ❌ ChatGPT Wrapper       | 无自有数据模型与工作流                       |
| ❌ Todo List / CRUD Demo | 无技术深度                                   |
| ❌ 单纯简历生成器        | 与竞品无差异，且强化幻觉问题                 |
| ❌ 单 Prompt AI App      | 无法体现 Agent 编排与工程能力                |
| ❌ 自动投递机器人        | 违反招聘平台 ToS，且法律与伦理风险高         |
| ❌ 全自动"代写"简历      | 与产品价值观（Evidence > Hallucination）冲突 |
| ❌ 收费/支付系统         | 与作品集目标无关                             |
| ❌ 移动 App              | Web 响应式已足够覆盖演示需求                 |
| ❌ 自训模型 / 微调       | 成本与收益不匹配，且偏离工程重点             |

---

## 11. 风险与对策

| 风险                         | 影响                   | 对策                                                            |
| ---------------------------- | ---------------------- | --------------------------------------------------------------- |
| LLM 输出不稳定导致评分漂移   | 演示翻车、评测不可复现 | 数值评分**确定性算法**化，LLM 只做叙述；全结构化输出 + 校验重试 |
| 无 API Key 时无法演示        | 面试环境不可控         | `heuristic` provider 完整实现，零 Key 全功能可跑（FR-18.2）     |
| GitHub 限流                  | GitHub 模块不可用      | 缓存 + 退避 + 内置快照 fixture                                  |
| 无 Docker 环境               | 一键启动失败           | 双路径：Docker 生产路径 + 零依赖本地路径（ADR-004 / ADR-010）   |
| 项目范围过大                 | 半成品                 | 严格 Phase 门禁，每个 Phase 必须可运行 + 可测试 + 可提交        |
| 证据不足导致简历"没东西可写" | 用户体验差             | 提供"补证据"闭环（FR-9.3 Mini Project）+ 安全改写降级           |
| 隐私顾虑                     | 用户不敢上传           | Local Mode + 明文不落库选项 + 公开页逐项开关                    |
| 图谱性能                     | 页面卡顿               | 服务端预聚合 + 虚拟化 + 上限节点数 + 移动端降级列表             |

---

## 12. 术语表

| 术语                     | 含义                                                         |
| ------------------------ | ------------------------------------------------------------ |
| **Evidence（证据）**     | 一条可定位的原始材料片段（文件、commit、文档段落、经历条目） |
| **Claim（断言）**        | 简历/面试中的一句能力描述，需要被证据支持                    |
| **Evidence Graph**       | 候选人 → 实体 → 技能 → 断言 的证据异构图                     |
| **Confidence（置信度）** | 证据支持某断言的可信程度，由 4.3 的确定性公式计算            |
| **Source Authority**     | 证据来源的权威等级（代码 > README > 文档 > 自述 > 推断）     |
| **Corroboration**        | 同一断言被多少个独立来源支持                                 |
| **Hallucination Gate**   | 生成内容必须通过 Claim Validator 才能进入简历的门禁机制      |
| **Heuristic Provider**   | 零 API Key 的确定性降级 provider，保证离线可运行             |
| **Store Port**           | 存储抽象端口（Vector / Queue / LLM），本地与生产可互换实现   |
| **Agent Run**            | 一次完整的工作流执行记录（含步骤链、token、耗时、成本）      |
| **ICP**                  | Ideal Candidate Profile，岗位的理想候选人画像                |

---

## 13. 交付物清单（v1.0.0）

| #   | 交付物                               | 位置                                  |
| --- | ------------------------------------ | ------------------------------------- |
| 1   | 可运行全栈应用                       | `apps/web` + `apps/api`               |
| 2   | AI 核心库（Agent/RAG/Graph/Scoring） | `packages/ai`                         |
| 3   | Prompt Registry（versioned）         | `prompts/`                            |
| 4   | 评测框架 + 报告                      | `evals/` + `reports/eval-report.json` |
| 5   | 测试套件（unit / integration / e2e） | `tests/` + `apps/*/…/tests`           |
| 6   | 一键部署                             | `docker-compose.yml` + `infra/`       |
| 7   | 完整文档（8 篇）                     | `docs/`                               |
| 8   | 面试材料包                           | `docs/INTERVIEW.md`                   |
| 9   | README（含截图/GIF/架构图）          | `README.md` + `docs/assets/`          |
| 10  | CI/CD                                | `.github/workflows/`                  |

---

**下一步**：见 [ROADMAP.md](./ROADMAP.md) 的 PHASE 1。
