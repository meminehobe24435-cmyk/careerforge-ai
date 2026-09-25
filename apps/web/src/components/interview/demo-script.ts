/**
 * The Demo session script.
 *
 * Three answers submitted through `POST /ai/interview/{id}/answer` — the same endpoint the
 * manual path uses, with the same evaluation, difficulty transition and scorecard. Nothing here
 * is replayed or faked; the only thing that is scripted is the *text* of the answers, which is
 * what makes the whole loop observable in about a minute.
 *
 * The three answers are shaped to exercise the three states of the difficulty rule
 * (`careerforge_ai/agents/interview/plan.py`): promote at ≥ 75, demote at ≤ 45, otherwise hold.
 * Verified against the live stack: 83.46 concept→engineering, 41.36 engineering→concept,
 * 57.88 no change.
 *
 * They are written to hit the terms the zero-key evaluator measures — `_BASE_TERMS`
 * (因为 / 所以 / 考虑 / 权衡 / trade / cost / 为什么) plus length — because that evaluator scores
 * *coverage*, not correctness, and says so in its own feedback. With a model-backed provider the
 * same text is judged semantically; the script does not depend on which one is running.
 */

/** A sample posting, parsed live by `POST /jobs/analyze` on every demo run. */
export const DEMO_JOB_TEXT = `高级后端工程师（AI 应用方向）

岗位职责：
1. 负责 AI 应用服务的后端设计与开发，使用 Python 与 FastAPI 构建对外接口；
2. 负责检索增强生成（RAG）链路的工程化落地，包括文档切分、向量检索与引用；
3. 负责 PostgreSQL 数据建模与查询优化，并引入 Redis 缓存热点数据；
4. 参与线上问题的定位与性能优化，保障接口的可用性与可观测性。

任职要求：
1. 本科及以上学历，3 年以上后端开发经验；
2. 精通 Python，熟悉 FastAPI 或同类异步框架；
3. 熟悉 PostgreSQL，具备索引与执行计划调优经验（必备）；
4. 熟悉 RAG 与向量检索，理解大模型幻觉控制手段；
5. 熟悉 Redis 缓存与一致性设计；
6. 有 Kubernetes 与 CI/CD 经验者优先。
`;

/** Turn 1 — a substantive answer, expected to push the difficulty up one rung. */
export const DEMO_ANSWER_STRONG = `可变默认参数的问题在于函数定义时就求值，默认参数只创建一次，所以多次调用会共享同一个引用，往列表里追加元素后下一个调用者会看到上一次的数据。我在模块里用 None 作为默认值并在函数体内新建对象，或者直接用不可变类型；因为可变对象引发的 bug 往往表现为内存里悄悄变大的容器，排查成本（cost）远高于改一行代码。另一个考虑是显式判断 None 会让签名变啰嗦，这里的 trade-off 是签名干净还是语义明确，权衡之后我选择语义优先。异常路径上我在初始化失败时抛出异常，而不是返回半成品；至于为什么不用 default_factory，因为它只覆盖一部分场景，依赖注入和测试替身仍然需要显式构造。`;

/** Turn 2 — a thin, hedged answer, expected to pull the difficulty back down. */
export const DEMO_ANSWER_WEAK = '这块我平时接触不多，可能要回去查一下文档再补充。';

/** Turn 3 — a partial answer: enough to hold the level, not enough to move it. */
export const DEMO_ANSWER_HOLD = `检索与生成的分工是：检索负责把候选缩小到可核查的范围，所以生成只在给定材料内组织语言，引用必须来自检索结果。我在分块时保留标题路径，因为太碎的块会丢上下文；召回和排序分开看，先确认命中再调排序。权衡的点是成本（cost）：候选越多生成越贵，我倾向先保召回再压数量。`;

export interface DemoScript {
  jobText: string;
  steps: number;
  answerFor: (step: number, topic: string | null) => string;
  /** Shown in the UI so the script is described, not hidden. */
  outline: string[];
}

const ANSWERS = [DEMO_ANSWER_STRONG, DEMO_ANSWER_WEAK, DEMO_ANSWER_HOLD];

export const demoSession: DemoScript = {
  jobText: DEMO_JOB_TEXT,
  steps: ANSWERS.length,
  answerFor: (step: number) => ANSWERS[step] ?? DEMO_ANSWER_HOLD,
  outline: [
    '第 1 轮：一段完整回答 → 预期难度提升一层（API 判定）',
    '第 2 轮：一段很薄的回答 → 预期难度回退一层（API 判定）',
    '第 3 轮：一段部分回答 → 保持当前难度，不显示提示',
    '随后调用 finish，生成七维评分卡',
  ],
};
