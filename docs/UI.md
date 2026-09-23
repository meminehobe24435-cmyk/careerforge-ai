# CareerForge AI · UI / UX 设计规范

| 字段     | 值                                                                                                                              |
| -------- | ------------------------------------------------------------------------------------------------------------------------------- |
| 文档版本 | v1.0                                                                                                                            |
| 技术栈   | Next.js 15（App Router）· React 19 · TypeScript strict · Tailwind CSS v4 · Radix/shadcn · Framer Motion · Recharts · React Flow |
| 关联     | [PRD.md](./PRD.md) · [API.md](./API.md) · [ARCHITECTURE.md](./ARCHITECTURE.md)                                                  |

---

## 1. 设计立场

### 1.1 气质目标

> **"这是一个工程师真正做出来的 SaaS 产品"，而不是"大学生课程设计"。**

参考坐标：**Linear / Vercel / Raycast / Stripe Dashboard / Notion / GitHub**。

| 要                                     | 不要                          |
| -------------------------------------- | ----------------------------- |
| 深色为第一公民，精心雕琢               | ❌ 廉价 AI 紫色渐变           |
| 细边框、网格、mono 字体、数据密集型    | ❌ 满屏 🤖 AI Assistant 气泡  |
| 克制的品牌色，只在"证据"与"风险"上点睛 | ❌ ChatGPT 克隆版布局         |
| 卡片 + 表格 + 图表 + 代码块混排        | ❌ 大圆角 + 大色块 + 大 emoji |
| 信息密度高但层次清晰                   | ❌ 一个功能一屏的营销式堆叠   |
| 动效轻、快、有目的（120–240ms）        | ❌ 弹跳、旋转、长时间装饰动画 |

### 1.2 品牌识别（差异化关键）

**"Forge（锻造）"的隐喻 → 熔炉橙；"Evidence（证据）"的隐喻 → 可信绿；风险 → 危险红。**

| 语义                   | 色值（Dark）               | 用途                                               |
| ---------------------- | -------------------------- | -------------------------------------------------- |
| **Forge（品牌主色）**  | `#F59E0B` → `#FB923C` 渐变 | 主 CTA、Hero 强调、Profile Strength 环             |
| **Evidence / 已证实**  | `#34D399`                  | `Supported` 徽章、证据节点、置信度 ≥ 0.75          |
| **Weak / 待补强**      | `#FBBF24`                  | `Partially Supported`、Weak Evidence 警告          |
| **Reject / 风险**      | `#F87171`                  | `Rejected Claim`、Contradicted、缺口 severity=high |
| **Signal（中性强调）** | `#60A5FA`                  | 链接、选中态、图表第二序列                         |

> 品牌主色刻意**避开紫/蓝紫**（AI 产品烂大街），选用与"Forge 锻造"语义强绑定的暖橙，在深色底上极具辨识度，且与"证据绿"形成清晰的语义对照。

### 1.3 信息架构原则

1. **证据随处可达**：任何出现技能/断言的地方（Dashboard、Job 详情、简历 Diff、面试报告）都能**一次点击**跳到证据。
2. **分数必须可展开**：任何分数旁边都有 `Why?`，点击展开公式与依据（Explainability > Black Box）。
3. **诚实标注**：降级（`degraded: true`）、样本不足、置信度低、AI 推断 —— 一律显式标注，绝不假装确定。
4. **零空状态**：Demo 账号进入任何页面都有真实数据；新用户有引导式空状态（含"一键载入示例数据"）。

---

## 2. Design Tokens

### 2.1 色彩（CSS 变量，`styles/tokens.css`）

```css
:root {
  /* 中性色阶（Dark 为默认主题） */
  --bg-base: #08090a; /* 页面底 */
  --bg-surface: #0d0e10; /* 卡片 */
  --bg-elevated: #141518; /* 弹层 / Drawer */
  --bg-hover: #1a1c1f;
  --bg-active: #212429;

  --border-subtle: rgba(255, 255, 255, 0.06);
  --border-default: rgba(255, 255, 255, 0.1);
  --border-strong: rgba(255, 255, 255, 0.18);

  --text-primary: #edeef0;
  --text-secondary: #a1a1aa;
  --text-tertiary: #71717a;
  --text-inverse: #08090a;

  /* 品牌与语义 */
  --brand: #f59e0b;
  --brand-strong: #fb923c;
  --brand-fg: #0a0a0a;
  --evidence: #34d399;
  --weak: #fbbf24;
  --danger: #f87171;
  --signal: #60a5fa;

  /* 图表序列（色盲友好，深色底对比度已校验） */
  --chart-1: #f59e0b;
  --chart-2: #60a5fa;
  --chart-3: #34d399;
  --chart-4: #a78bfa;
  --chart-5: #f472b6;
  --chart-6: #38bdf8;

  /* 网格背景（技术感来源） */
  --grid-line: rgba(255, 255, 255, 0.035);
}

[data-theme='light'] {
  --bg-base: #ffffff;
  --bg-surface: #fafafa;
  --bg-elevated: #ffffff;
  --bg-hover: #f4f4f5;
  --bg-active: #e4e4e7;
  --border-subtle: rgba(9, 9, 11, 0.06);
  --border-default: rgba(9, 9, 11, 0.1);
  --border-strong: rgba(9, 9, 11, 0.18);
  --text-primary: #09090b;
  --text-secondary: #52525b;
  --text-tertiary: #a1a1aa;
  --brand: #d97706;
  --brand-strong: #ea580c;
  --evidence: #059669;
  --weak: #b45309;
  --danger: #dc2626;
  --signal: #2563eb;
  --grid-line: rgba(9, 9, 11, 0.04);
}
```

**约束**：所有颜色必须走变量，**禁止组件内硬编码色值**（CI 用 lint 规则检查 `#[0-9a-f]{6}` 出现在组件文件中）。

### 2.2 字体

| 用途                      | 字体                                     | 规格                                          |
| ------------------------- | ---------------------------------------- | --------------------------------------------- |
| UI 正文                   | **Geist Sans**（回退 Inter / system-ui） | 14px/1.5 基准；`-apple-system` 栈             |
| 代码 / 路径 / hash / 数字 | **Geist Mono**（回退 JetBrains Mono）    | 12–13px；`font-variant-numeric: tabular-nums` |
| 大标题                    | Geist Sans                               | `tracking-tight`，weight 600                  |

**Mono 的使用规则（技术感的关键）**：commit hash、文件路径、技能 id、置信度百分比、分数、URL、命令 —— 一律 mono + `tabular-nums`。

### 2.3 尺度

| Token                            | 值                                                                                                                                 |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 圆角                             | `--radius-sm: 6px`（徽章/输入）、`--radius-md: 10px`（按钮/卡片）、`--radius-lg: 14px`（面板/Modal）、`--radius-full`（头像/药丸） |
| 间距                             | 4px 基准：`4 / 8 / 12 / 16 / 24 / 32 / 48 / 64`                                                                                    |
| 阴影（暗色以边框为主，阴影为辅） | `--shadow-sm: 0 1px 2px rgba(0,0,0,.35)`、`--shadow-md: 0 4px 16px rgba(0,0,0,.45)`、`--shadow-lg: 0 12px 40px rgba(0,0,0,.55)`    |
| 层级                             | `--z-drawer:50`、`--z-modal:60`、`--z-palette:70`、`--z-toast:80`                                                                  |
| 动效                             | `--dur-fast:120ms`、`--dur-base:180ms`、`--dur-slow:240ms`；`--ease-out: cubic-bezier(.16,1,.3,1)`                                 |

---

## 3. 组件清单（54 个）

### 3.1 基础原子（`packages/ui`）

`Button`（primary/secondary/ghost/danger × sm/md/lg）· `IconButton` · `Input` · `Textarea` · `Select` · `Combobox`（技能多选）· `Checkbox` · `Switch` · `RadioGroup` · `Slider` · `Badge` · `Tag` · `Avatar` · `Tooltip` · `Popover` · `DropdownMenu` · `Separator` · `Skeleton` · `Spinner` · `Progress` · `Tabs` · `Accordion` · `ScrollArea` · `Sheet/Drawer` · `Dialog/Modal` · `AlertDialog` · `Toast/Sonner` · `Breadcrumb` · `Pagination` · `EmptyState` · `ErrorState` · `CopyButton` · `CodeBlock`（带语言与复制）· `Kbd`

### 3.2 领域组件（`apps/web/src/components`）

| 组件                                         | 说明                                                                           |
| -------------------------------------------- | ------------------------------------------------------------------------------ |
| `AppShell`                                   | 侧边栏 + 顶栏 + 内容区骨架                                                     |
| `SidebarNav`                                 | 分组导航（Overview / Career / Intelligence / Interview / Ops），含活动指示条   |
| `TopBar`                                     | 面包屑 + 全局搜索入口 + 主题切换 + 用户菜单                                    |
| `CommandPalette`                             | `Ctrl/Cmd+K`，见 §7                                                            |
| `GlobalSearchDialog`                         | 分组搜索结果（键盘导航）                                                       |
| `StatCard`                                   | 指标卡（值 + 环比 + 迷你 sparkline + 悬停解释）                                |
| `ProfileStrengthRing`                        | 环形进度 + 五维拆解 Popover                                                    |
| `SkillRadarChart`                            | 7 维雷达（用户 vs 市场基准双序列）                                             |
| `EvidenceGraphCanvas`                        | React Flow 画布（核心页面）                                                    |
| `GraphNodeCard` / `GraphEdgeLabel`           | 自定义节点/边渲染                                                              |
| `GraphFilterBar`                             | 节点类型/技能/时间过滤 + 布局切换                                              |
| `EvidenceDrawer`                             | 右侧抽屉：Evidence / Confidence / Source / Last Updated / AI Analysis          |
| `ConfidenceMeter`                            | 置信度可视化（分档 + 子项拆解条）                                              |
| `EvidenceBadge`                              | `Supported` / `Weak Evidence` / `Rejected Claim` 三态徽章                      |
| `ClaimCard`                                  | 断言卡（原文、状态、原因、安全改写、接受/拒绝）                                |
| `ResumeDiffView`                             | 左右 diff（逐 bullet，含接受/拒绝与状态徽章）                                  |
| `JDSkillTree`                                | Required / Preferred / Bonus 三层树，节点带 JD 原文出处                        |
| `MatchScorePanel`                            | 总分 + 五维条形 + `Why?` 展开（公式与依据）                                    |
| `WhyBreakdown`                               | 评分拆解表格（维度/权重/得分/公式/证据 id）                                    |
| `StrengthsGapsList`                          | 三栏：Strengths / Gaps / Unknown（unknown 可一键确认）                         |
| `SkillGapMatrix`                             | 缺口矩阵表（可排序、可筛选、含"补证据"入口）                                   |
| `LearningPlanTimeline`                       | 4 周计划时间线 + Mini Project 卡                                               |
| `ChatTranscript`                             | 面试对话流（含题目层级标记、打字机流式）                                       |
| `InterviewScorecard`                         | 七维雷达 + 逐题复盘 + 证据冲突警示                                             |
| `KanbanBoard`                                | 投递看板（dnd-kit 拖拽 + 乐观更新）                                            |
| `ApplicationCard`                            | 岗位卡（公司/角色/匹配分/日期/备注）                                           |
| `FunnelChart`                                | 漏斗图（自定义 SVG，非图表库默认样式）                                         |
| `SkillCorrelationChart`                      | 技能 ↔ 面试率散点/条形（含样本量提示）                                         |
| `CareerTimeline`                             | 职业时间线（横向 + 纵向自适应）                                                |
| `AiRunsTable`                                | AI Runs 数据表（排序/筛选/分页/行展开）                                        |
| `CostByAgentChart`                           | 每 Agent 成本堆叠柱 + 缓存命中率                                               |
| `TaskProgressStream`                         | 阶段式进度（`parsing → extracting → …`，SSE 驱动）                             |
| `ArchitectureDiagram`                        | `/architecture` 的自定义架构图（非 Mermaid 渲染，纯 SVG/CSS 以获得更高控制力） |
| `HealthStatusGrid`                           | `/system` 的服务健康网格                                                       |
| `PublicProfileHero` / `EvidenceBackedSkills` | Recruiter View 组件                                                            |

---

## 4. 站点地图

```
/                                Landing（公开）
/login                           登录 / Demo 入口

/app                             AppShell 布局（需认证）
├── /app/dashboard               总览
├── /app/profile                 Career Profile（导入、编辑、Strength）
├── /app/github                  GitHub Intelligence
├── /app/evidence-graph          ★ Evidence Graph（视觉核心）
├── /app/evidence                证据列表与检索
├── /app/validator               ★ Claim Validator（自由试玩）
├── /app/jobs                    岗位列表
├── /app/jobs/new                JD 分析
├── /app/jobs/[id]               岗位详情（Skill Tree + Match + Gaps）
├── /app/resume                  Resume Copilot（Diff）
├── /app/resume/versions         版本历史
├── /app/interview               面试列表 + 启动
├── /app/interview/[id]          面试会话
├── /app/interview/[id]/report   Scorecard 报告
├── /app/applications            投递看板
├── /app/analytics               Career Analytics
├── /app/ai-runs                 AI Observability
├── /app/costs                   AI Cost Dashboard
├── /app/settings                设置（隐私 / AI / 公开页）
└── /app/projects/[id]           Project Deep Dive

/architecture                    系统架构（公开，面试官专用）
/system                          系统健康（公开只读）
/candidate/[slug]                ★ Recruiter View / Shareable Profile（公开无登录）
```

---

## 5. 页面规格

> 每页规格包含：目的 / 布局 / 区块 / 数据来源 / 状态 / 响应式 / 关键交互。
> 标注 ★ 的页面为面试演示重点。

### 5.1 `/` Landing

| 项                             | 内容                                                                                                                                                                                                                                                                                              |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **目的**                       | 30 秒内建立"这不是普通学生项目"的认知                                                                                                                                                                                                                                                             |
| **Hero**                       | 网格背景 + 顶部径向暖光（`--brand` 20% 透明）；H1 `Your career deserves better infrastructure.`；副标题 `Build a verifiable career profile from your resume, GitHub, projects and experience.`；三按钮 `Start Building`（主）/ `View Demo` / `GitHub`；下方 mono 小字：`Evidence > Hallucination` |
| **信任条**                     | mono 徽章行：`Claim → Evidence Traceability` · `Explainable Match Score` · `Hybrid RAG + pgvector` · `Works without API keys`                                                                                                                                                                     |
| **产品 Mockup**                | 真实截图（Dashboard）置于浏览器窗框内，带轻微透视与辉光；右侧浮动一张 `EvidenceDrawer` 小卡（视觉钩子）                                                                                                                                                                                           |
| **能力区（6 块，编号 01–06）** | `01 Evidence Graph` / `02 JD Intelligence` / `03 AI Resume Copilot` / `04 Interview Simulator` / `05 Career Analytics` / `06 Application Pipeline`；每块：编号 + 标题 + 一句价值 + 该功能的真实截图（交错左右布局）                                                                               |
| **"为什么不一样"对照区**       | 两列对照：`Typical AI resume tool`（会编造 "提升 50%"）vs `CareerForge`（Rejected Claim + 证据指引）；此区必须有**真实截图**而非插画                                                                                                                                                              |
| **技术区**                     | 架构简图 + 技术徽章（Next.js / FastAPI / PostgreSQL+pgvector / Redis / Docker / TypeScript / Python）                                                                                                                                                                                             |
| **彩蛋句**                     | 底部大字：`Most resumes describe what you claim to know. CareerForge shows the evidence.` + 中文副句                                                                                                                                                                                              |
| **Footer**                     | 文档链接（Architecture / API / Interview Guide）、GitHub、License                                                                                                                                                                                                                                 |
| **响应式**                     | 1440 三栏 mockup 交错；1024 收窄；768 单列堆叠；375 Hero 字号降至 `32px`，按钮纵向堆叠                                                                                                                                                                                                            |

### 5.2 `/login`

左侧品牌面板（渲染中截取的 Evidence Graph 缩略图）+ 右侧表单。**主 CTA 为 `Enter Demo`（一键登录）**，副 CTA 为邮箱登录/注册。Demo 按钮下 mono 小字：`demo@careerforge.ai · 已预置完整候选人数据`。

### 5.3 `/app/dashboard` ★

| 区块                 | 规格                                                                                                                                                |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **顶部**             | 问候 + 目标角色 chips + `Next action` 提醒卡（含倒计时）                                                                                            |
| **Profile Strength** | 大号环形 `82/100`（品牌橙渐变），右侧五维拆解条 + 2 条改进建议（可点击直达修复入口）                                                                |
| **指标卡 ×6**        | Evidence Coverage 72% / Skill Coverage 68% / Resume Match 84% / Applications 23 / Interviews 5 / Offers 1（每卡带 7 日迷你趋势 + Tooltip 说明口径） |
| **技能雷达**         | 7 维双序列（用户 vs 市场基准），图例可切换；点击维度跳 `/app/evidence-graph?focus=skill:{id}`                                                       |
| **岗位匹配列表**     | 表格：Company / Role / Match（带 `Why?`）/ Status / 更新时间；行点击进详情                                                                          |
| **证据增长**         | 折线：近 30 天证据数与平均置信度                                                                                                                    |
| **投递漏斗缩略**     | 迷你漏斗 + `查看完整分析 →`                                                                                                                         |
| **状态**             | Skeleton（骨架与真实布局同构）/ Error + Retry / 空态（引导载入 Demo 数据）                                                                          |
| **响应式**           | 1440：指标卡 6 列；1024：3 列；768：2 列；375：1 列 + 雷达图高度自适应 240px                                                                        |

### 5.4 `/app/profile`

三段式：**资料来源区**（拖拽上传、GitHub 绑定、导入历史）+ **结构化画像区**（Education / Experience / Project / Achievement 卡片，可内联编辑，`origin` 标记 LLM 抽取 vs 用户修正）+ **技能矩阵区**（技能 × level × 证据数 × 证据强度，点击进图谱）。右上 `Profile Strength` 常驻迷你环。

**导入过程**：`TaskProgressStream` 展示 5 阶段（`parsing → extracting → normalizing → embedding → graphing`），每阶段含实时计数（如 `识别 12 个项目经历`）。完成后展示"本次新增 N 条证据 / M 个技能"，附 `查看图谱` CTA。

### 5.5 `/app/github`

顶部：用户名输入 + 分析按钮 + 限额状态。中部：语言占比（横向堆叠条）+ `EngineeringProfile` 卡片（方向 + 得分 + 信号 chips）+ 贡献活动（可选热力图）。下部：仓库卡片网格，每卡显示 stars / 语言 / topics / `Project Intelligence Report` 摘要（识别到的技术要素 chips：`FreeRTOS` `PID` `UART DMA` `IMU` `Encoder`）+ `查看证据` 按钮。含 `degraded` 徽章（无 Token 时）。

### 5.6 `/app/evidence-graph` ★★（视觉核心）

```
┌──────────────────────────────────────────────────────────────┐
│ 顶栏: [搜索节点] [类型过滤▾] [技能过滤▾] [时间范围▾] [布局▾] [导出PNG] │
├───────────────────────────────────────────┬──────────────────┤
│                                           │  Evidence Drawer │
│            React Flow Canvas              │  ───────────────  │
│   (网格背景 + 自定义节点 + 贝塞尔边)          │  motor_control.c │
│                                           │  repo_file       │
│   candidate → project → skill → claim     │  Confidence 0.97 │
│         ↳ repo_file ↳ commit              │  ──子项拆解条──    │
│                                           │  authority 1.00  │
│                                           │  recency   0.88  │
│                                           │  specificity 1.00│
│                                           │  corroboration .8│
│                                           │  extraction 1.00 │
│                                           │  ───────────────  │
│                                           │  Source: GitHub  │
│                                           │  Core/Src/...:42 │
│                                           │  Last updated 3d │
│                                           │  AI Analysis: …  │
│                                           │  [在 GitHub 打开] │
└───────────────────────────────────────────┴──────────────────┘
```

| 交互            | 行为                                                                                               |
| --------------- | -------------------------------------------------------------------------------------------------- |
| 点击节点        | 右侧 Drawer 打开；节点高亮 + 相关边加粗，无关节点降至 25% 不透明度                                 |
| 选择 Claim 节点 | 高亮完整溯源路径（Source → Evidence → Claim），其他元素淡出                                        |
| 双击技能节点    | 以该技能为中心重新布局（`focus=skill:{id}`，写入 URL，可分享）                                     |
| 悬停边          | 显示 relation 名称与 confidence tooltip                                                            |
| 布局切换        | `层次（默认，自上而下）` / `力导向` / `径向（以 Claim 为中心）`                                    |
| 过滤            | 类型多选、最小置信度滑块、时间范围、仅显示有证据节点                                               |
| 性能            | > 300 节点自动合并同类证据为"聚合节点（+12）"，点击展开                                            |
| 移动端          | 检测 < 768px → **降级为分层列表视图**（Candidate → Skill → Evidence 折叠列表），保留全部信息与交互 |

**为什么这是核心页面**：它是唯一一个把"产品价值观"变成可交互视觉的地方。README 与简历的第一张图应当是它。

### 5.7 `/app/jobs/new` — JD 分析

左侧大文本框（mono，支持粘贴/拖入文件），右侧实时提示（识别到的公司/角色/技能数预估）。提交后右侧变为**流式 Skill Tree 构建过程**：三层树逐步填充（每层带进度计数），完成后出现 `立即匹配` 按钮。

### 5.8 `/app/jobs/[id]` ★ — 岗位详情

| 区块                 | 规格                                                                                                                                |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 头部                 | Company / Role / Location / Salary / 状态徽章 / `加入投递`                                                                          |
| **Match Score 面板** | 大号 `86/100` + 五维横向条（权重标注）+ `Why 86?` 展开 → `WhyBreakdown` 表格（维度 / 权重 / 原始分 / 加权分 / 公式 / 证据 id 链接） |
| **三栏结论**         | Strengths（绿）/ Gaps（红，带 severity）/ Unknown（灰，可一键"我会，请记录"）                                                       |
| **JD Skill Tree**    | 三层树；每个技能行显示 `用户 level` + `证据数` + `置信度` + 悬停显示 JD 原文出处                                                    |
| 岗位原文             | 可折叠，技能在原文中高亮（点击高亮词 → 滚动到树中对应节点）                                                                         |
| 关联动作             | `优化简历` / `技能缺口` / `开始模拟面试` / `加入投递`                                                                               |
| **状态**             | 匹配计算中显示分维度进度（非 Spinner）；解析失败显示 `heuristic_fallback` 徽章与重试                                                |

### 5.9 `/app/validator` ★ — Claim Validator

极简直觉设计：**一个大输入框 + 一个验证按钮**，下方实时结果卡。

示例占位符轮换：

- `基于 FreeRTOS 开发多任务实时控制系统，任务调度周期 1ms`
- `优化算法性能，提升 70%`
- `熟练使用 Redis 与 Kafka 构建高并发架构`

结果卡包含：状态徽章 + 置信度环 + 证据来源列表（可点击）+ 触发规则说明 + **安全改写建议（带复制按钮）** + `为什么会这样判定?` 折叠区（显示检索通道、RRF 分数、命中片段）。

> 这一页是面试中最好的"对抗测试"入口：面试官可以现场输入任何一句话看系统如何拒绝。

### 5.10 `/app/resume` ★ — Resume Copilot

顶部：选择目标岗位 + 简历版本 + `生成优化`。主体为 **`ResumeDiffView`**：

- 左栏 `Original`（灰调，删除内容加删除线）
- 右栏 `Optimized`（正常色，新增内容带 `--evidence` 左侧色条）
- 每条 bullet 右上角状态徽章；`Rejected Claim` 行以 `--danger` 边框 + 说明卡呈现，**且提供安全改写版本供选择**
- 底部工具栏：`全部接受` / `全部拒绝` / `仅接受 Supported`（默认推荐）+ 实时 `Integrity Score`（有证据支撑的 bullet 占比）
- 右侧摘要：`11 Supported · 3 Weak · 1 Rejected`；导出 MD/PDF

### 5.11 `/app/interview/[id]`

上半部对话流（`ChatTranscript`）：面试官消息左侧、候选人消息右侧；每条面试官消息显示**题目层级徽章**（`L1 概念` / `L2 工程` / `L3 Debug`）与主题标签（`FreeRTOS`）—— 让"自适应"变得可见。侧栏常驻：`当前难度`、`已覆盖主题`、`进行中计时`。

输入区支持 Enter 发送、Shift+Enter 换行、流式打字机渲染。答完后每题内联显示评分与缺失知识点（不打断作答节奏）。

### 5.12 `/app/interview/[id]/report`

七维雷达（大号）+ 总分 + `Strong / Weak / Missing` 三栏 + 逐题复盘手风琴（含建议答案与追问方向）+ **证据一致性警示区**（口述与图谱冲突项）+ 导出 Markdown。

### 5.13 `/app/applications`

看板 7 列（Wishlist / Applied / OA / Interview / Final / Offer / Rejected），列头显示计数与转化率。卡片拖拽（dnd-kit，键盘可操作：聚焦卡片 → `Space` 拾起 → 方向键移动 → `Space` 放下）。列宽 280px，横向滚动；移动端切换为**按状态分组的列表视图**。

> **状态：已实现（PHASE 8c）** — `components/applications/*`，路由 `/app/applications`。
> 与本节规格的两处差异，均为有意为之：
> ① **列头只有计数，没有转化率**：转化率是漏斗口径（「曾经进入过这一阶段」），必须由
> `application_events` 事件流算出；看板持有的是当前状态快照，用快照算「转化率」会把「面试后被拒」
> 算成「没进过面试」。它属于 PHASE 9 的 `/analytics/funnel`，在那里算才是对的。
> ② 拖拽预览用 `DragOverlay`（卡片跟随指针）而非原地重排：原地重排会在一手势中途改变列表顺序，
> 卡片落到与用户瞄准处相邻的位置；现在只在放下时重排一次，而那次重排已经等于服务端将要返回的结果。
> **键盘路径不是装饰**：dnd-kit 自带的 `sortableKeyboardCoordinates` 只在起始列内游走，用它时
> 卡片**永远无法换列**——恰好看板存在的意义。因此本项目自写坐标解析（`lib/keyboard-coordinates.ts`），
> 由 `kanban-keyboard.test.tsx` 断言「→ 一列 / →→ 两列 / ↓ 列内换位」。
> 指针拖拽在 jsdom 中无法真实验证（无布局、无 PointerEvent），因此它由 PHASE 13 的真实浏览器检查覆盖；
> 当前由组件测试覆盖的是键盘路径与卡片菜单路径（两者都走同一个 mutation）。

### 5.14 `/app/analytics`

| 图         | 规格                                                                                         |
| ---------- | -------------------------------------------------------------------------------------------- |
| 漏斗       | Applications → Replies → Interviews → Finals → Offers，自定义 SVG，含阶段转化率标注          |
| 核心比率   | 4 张卡：Interview Rate / Offer Rate / Response Rate / Avg Match Score（含 7/30/90/all 切换） |
| 技能相关性 | 横条：各技能对应的面试转化率；**必须有样本量标注**，`n < 5` 时显示"样本不足"灰化处理         |
| 类别表现   | 岗位类别 × 匹配分/面试率 散点或表格                                                          |
| 时间趋势   | 投递量 vs 面试量双轴折线                                                                     |

### 5.15 `/app/ai-runs` & `/app/costs`

`AiRunsTable`：Agent / Workflow / Model / Tokens / Latency / Cost / Status / Cache / 时间；行展开显示步骤链（每步名称、耗时、token、状态）。`/app/costs`：日 token 折线 + 每 Agent 堆叠柱 + 每功能饼图 + 缓存命中率仪表 + 预算护栏配置（当前用量进度条，超限阈值标记）。

### 5.16 `/candidate/[slug]` ★ — Recruiter View

顶部大字姓名 + headline + `Verified by evidence` 徽章 + GitHub/Resume 链接。下方：

- **Evidence-backed Skills**：技能 chips，点击就地展开证据面板（不跳转、不登录）
- **Projects**：项目卡 + 架构图 + 关键文件链接（可跳 GitHub）
- **Engineering Highlights**：RecruiterAgent 生成的 3–5 条（每条绑定证据）
- **Interview Topics**：可以深入讨论的话题（帮助面试官提问）
- 底部：`分享` / `下载摘要 PDF`（P1）

**隐私**：受 `public_profiles.sections` 控制；无邮箱/电话；`本地模式` 用户默认不可发布。

### 5.17 `/architecture` & `/system`

`/architecture`：一张自绘架构图（Frontend → API → AI Core → Ports → Infra）+ Agent 工作流图 + 数据流图 + "为什么这样设计"的三条要点（链接到 ADR）。带 `查看 DECISIONS.md` CTA。

`/system`：服务健康网格（API / PostgreSQL / Redis / Vector Store / LLM Provider）+ 版本信息（app version / git sha / build time / Python / Node）+ provider 配置（脱敏）+ 迁移版本。异常服务显示红色与错误摘要。

---

## 6. 状态设计

### 6.1 三态强制

| 态          | 规格                                                                                                 |
| ----------- | ---------------------------------------------------------------------------------------------------- |
| **Loading** | Skeleton **与真实布局同构**（不是通用灰块）；AI 长任务用 `TaskProgressStream` 阶段进度；表格用行骨架 |
| **Empty**   | 图标 + 一句解释 + 一个明确动作（如"载入示例数据" / "上传简历"）+（Demo 用户永不出现）                |
| **Error**   | 错误码 + 人话解释 + `重试` 按钮 + `requestId`（可复制，便于排查）+ `查看状态页` 链接                 |

### 6.2 降级与诚实标注

| 场景                          | UI 表现                                                                                 |
| ----------------------------- | --------------------------------------------------------------------------------------- |
| AI provider 降级（heuristic） | 顶部条 `AI 服务降级中：当前使用本地规则引擎，结果可能较保守` + 卡片角落 `degraded` 徽章 |
| 缓存命中                      | 徽章 `cached`（Tooltip：本结果来自缓存，0 成本）                                        |
| 样本不足                      | 图表显示 `n=3 · 样本不足，仅供参考` 并降低饱和度                                        |
| 置信度低                      | 数值旁 `⚠` + Tooltip 解释子项哪个拖低了分数                                             |
| GitHub 限流                   | 页面级提示 + 重置时间倒计时 + `使用缓存快照` 按钮                                       |

---

## 7. Command Palette（`Ctrl/Cmd + K`）

```
┌─────────────────────────────────────────────┐
│  🔍  输入命令或搜索…                    esc │
├─────────────────────────────────────────────┤
│  动作                                        │
│  ⚡  分析 JD            ⌘⏎   Analyze a job   │
│  ➕  添加投递                 Add application │
│  🎤  开始模拟面试             Start interview │
│  📄  上传简历                 Upload resume   │
│  🔗  绑定 GitHub              Analyze GitHub  │
│  导航                                        │
│  ◫  总览 Dashboard        g d                │
│  ◈  证据图谱 Evidence Graph g e              │
│  ◇  岗位 Jobs             g j                │
│  搜索 "freertos"                             │
│  ◆  技能 FreeRTOS         9 evidence         │
│  ▣  项目 Balance Robot    match 0.91         │
│  ▤  证据 freertos.c       repo_file 0.94     │
└─────────────────────────────────────────────┘
```

- 键盘全可用（↑↓ 选择、Enter 执行、Esc 关闭、Tab 切分组）
- 支持模糊匹配 + 拼音首字母（中文场景）
- 最近使用记录（localStorage）
- 无结果时提供 `用 "xxx" 分析 JD` 兜底动作

---

## 8. 动效规范

| 场景             | 规格                                                                        |
| ---------------- | --------------------------------------------------------------------------- |
| 页面/区块进入    | `opacity 0→1` + `translateY 8px→0`，180ms `--ease-out`；列表项 stagger 20ms |
| Drawer / Modal   | 从右侧 `translateX(100%)→0`，240ms；背景遮罩淡入 120ms                      |
| 数字变化（分数） | 计数动画 400ms（`prefers-reduced-motion` 下直接跳变）                       |
| 图谱节点         | 布局过渡 300ms；高亮/淡出 150ms                                             |
| 徽章出现         | 轻微 scale 0.96→1 + 淡入，120ms                                             |
| 流式文本         | 打字机效果（按真实 token 到达渲染）                                         |
| 图表绘制         | 首次进入 500ms 绘制动画（仅一次）                                           |
| 拖拽             | 无缩放变形，仅阴影加深 + 轻微倾斜（1deg 以内）                              |

**禁止**：无限循环动画（除 loading）、弹跳（bounce）、超过 400ms 的过场、导致布局位移（CLS）的动画。全局遵守 `prefers-reduced-motion: reduce`。

---

## 9. 可访问性（A11y）

| 项       | 要求                                                                                                         |
| -------- | ------------------------------------------------------------------------------------------------------------ |
| 语义     | 正确的 landmark（`nav`/`main`/`aside`）、标题层级不跳级                                                      |
| 键盘     | 全部交互可达；图谱支持 `Tab` 遍历节点 + `Enter` 打开 Drawer；看板支持键盘拖拽                                |
| 焦点     | 2px 品牌色 focus ring（`outline-offset: 2px`），不依赖 `:hover`                                              |
| ARIA     | 图标按钮必须有 `aria-label`；状态徽章 `role="status"`；图表提供 `aria-label` + 数据表替代（`sr-only` table） |
| 对比度   | 正文 ≥ 4.5:1；大字号 ≥ 3:1；图表序列色已校验                                                                 |
| 表单     | `<label>` 关联；错误用 `aria-describedby` + `aria-invalid`                                                   |
| 动效     | 尊重 `prefers-reduced-motion`                                                                                |
| 图表可读 | 不单靠颜色区分（同时用形状/标签/图案）                                                                       |

---

## 10. 响应式矩阵

| 断点          | 布局                                                                                                        |
| ------------- | ----------------------------------------------------------------------------------------------------------- |
| **≥1440**     | 侧边栏展开 240px；Dashboard 指标卡 6 列；图谱全屏三栏；Diff 左右并排                                        |
| **1024–1439** | 侧边栏展开 240px；指标卡 3 列；图谱保持画布 + Drawer 覆盖式；Diff 并排                                      |
| **768–1023**  | 侧边栏折叠为图标 64px；指标卡 2 列；图谱 Drawer 变为底部 Sheet；Diff 上下堆叠                               |
| **375–767**   | 侧边栏改为底部/抽屉导航；指标卡 1 列；**图谱降级为分层列表**；看板切列表视图；表格改卡片流；触摸目标 ≥ 44px |

**每页验收**：必须实际在 1440 / 1024 / 768 / 375 四档检查（无横向滚动、无文字截断、无重叠、无不可点击元素）。

---

## 11. i18n 与文案

| 项         | 约定                                                                                                     |
| ---------- | -------------------------------------------------------------------------------------------------------- |
| 语言       | v1.0 中文为主界面语言，技术名词与专业术语保留英文（`Evidence Graph`、`Match Score`、`FreeRTOS`）         |
| 文案基调   | 直接、专业、不用感叹号、不卖萌、不夸大                                                                   |
| 错误文案   | 说清"发生了什么 + 你能做什么"（例：`无法解析该 PDF（可能为扫描件）。请上传文字版 PDF 或直接粘贴内容。`） |
| 术语一致性 | 全文统一使用 PRD 术语表词汇（evidence / claim / confidence / match score）                               |
| i18n 结构  | 文案集中在 `lib/i18n/zh-CN.ts` + `en.ts`，为后续国际化预留（v1.1）                                       |

---

## 12. 截图与 GIF 交付清单（README 使用）

| 文件                 | 内容                                        | 用途                                |
| -------------------- | ------------------------------------------- | ----------------------------------- |
| `dashboard.png`      | Dashboard 全貌（1440）                      | README 首图                         |
| `evidence-graph.gif` | 点击 Skill → 展开 Evidence → 展示置信度拆解 | README 核心演示（**最关键的一张**） |
| `evidence-graph.png` | 图谱静态大图                                | README 功能章节                     |
| `job-analysis.png`   | JD Skill Tree + Match Score + Why 展开      | 功能章节                            |
| `validator.png`      | Claim Validator 拒绝 "提升 70%"             | **差异化章节**                      |
| `resume-copilot.png` | Diff 视图含 Rejected Claim                  | 功能章节                            |
| `interview.png`      | 面试会话 + Scorecard 雷达                   | 功能章节                            |
| `analytics.png`      | 漏斗 + 技能相关性                           | 功能章节                            |
| `recruiter-view.png` | 公开候选人页含证据展开                      | 产品价值章节                        |
| `architecture.png`   | 架构页截图                                  | 架构章节                            |

**制作要求**：深色主题、真实数据（Demo 账号）、1440×900 或 1600×1000、无浏览器书签栏、GIF ≤ 6s 且 ≤ 3MB。

---

**下一篇**：[ROADMAP.md](./ROADMAP.md)
