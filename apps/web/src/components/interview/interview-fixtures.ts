/**
 * Test fixtures — not imported by the page.
 *
 * The payloads below are trimmed copies of real responses captured from the running stack
 * (`.tmp/p13-interview-probe.json`, driven by `.tmp/p13_interview_probe.py`), field names, ASCII
 * difficulty values and Chinese copy included. Copying the live shape rather than inventing one is
 * the point: the guards and the components exist to survive *this* payload, so a fixture that
 * drifts from it would test a system nobody runs.
 */

import type {
  AiMeta,
  DifficultyChange,
  InterviewScorecard,
  InterviewSession,
  InterviewTurnResponse,
  TurnEvaluation,
} from '@/lib/interview-api';
import type {
  InterviewCapabilities,
  JobDetail,
  JobList,
  SkillTree,
} from '@/lib/interview-target-api';

export const QUESTION_ONE = 'Python 里可变默认参数会带来什么问题？你在代码里怎么避免？';
export const QUESTION_TWO = 'FastAPI 的依赖注入是怎么工作的？你用它解决了什么问题？';
export const QUESTION_THREE = 'RAG 流程里，检索和生成各自负责什么？';
export const FEEDBACK =
  '回答长度 220 字，覆盖了 4/7 个期望要点。（本地规则引擎评估，仅反映要点覆盖度，不代表技术正确性）';
export const SESSION_ID = '410779af-735a-45d8-ba0e-c1d69fb48ba6';
export const JOB_ID = '069a144b-4438-49da-a3e9-1b4086fb7281';

export function meta(overrides: Partial<AiMeta> = {}): AiMeta {
  return {
    provider: 'heuristic',
    model: null,
    promptVersion: 'interviewer@v1',
    degraded: true,
    degradedReason: 'no_api_key',
    workflow: 'interview_start',
    runId: '5e7ff964-9f00-426f-93fb-49285fa87b36',
    latencyMs: 2,
    cacheHit: false,
    warnings: ['面试已降级运行（原因：no_api_key）', '执行 question 步骤时未提供输出'],
    ...overrides,
  };
}

/** The evaluation the live stack returned for a 220-character answer. */
export function evaluation(overrides: Partial<TurnEvaluation> = {}): TurnEvaluation {
  return {
    turnIndex: 2,
    score: 68.58,
    technicalAccuracy: 0.657,
    depth: 0.657,
    communication: 0.9,
    problemSolving: 0.624,
    engineeringThinking: 0.591,
    confidence: 0.91,
    missingKnowledge: ['未提及「cost」', '未提及「trade」', '未提及「所以」'],
    feedback: FEEDBACK,
    strongPoints: ['覆盖了「为什么」', '覆盖了「因为」', '覆盖了「权衡」'],
    followUpTopics: ['cost', 'trade', '所以'],
    suggestedAnswer: '',
    ...overrides,
  };
}

export function promoted(): DifficultyChange {
  return {
    fromLevel: 'concept',
    toLevel: 'engineering',
    reason: '回答得分 83，高于 75，进入更深一层追问',
  };
}

export function demoted(): DifficultyChange {
  return {
    fromLevel: 'engineering',
    toLevel: 'concept',
    reason: '回答得分 41，低于 45，退回上一层确认基础',
  };
}

/** What `_adapt` returns when the rung does not move — the case the notice must stay quiet for. */
export function held(): DifficultyChange {
  return { fromLevel: 'concept', toLevel: 'concept', reason: '回答得分 69，保持当前难度' };
}

export function session(overrides: Partial<InterviewSession> = {}): InterviewSession {
  return {
    sessionId: SESSION_ID,
    mode: 'technical',
    status: 'in_progress',
    currentLevel: 'concept',
    plan: [
      {
        topic: 'python',
        label: 'Python',
        targetLevel: 'concept',
        reason: '岗位必备 Python，但证据图谱中没有支撑，面试中很可能被追问',
        source: 'gap',
        sourceIds: [],
      },
      {
        topic: 'fastapi',
        label: 'FastAPI',
        targetLevel: 'concept',
        reason: '岗位必备 FastAPI，但证据图谱中没有支撑，面试中很可能被追问',
        source: 'gap',
        sourceIds: [],
      },
      {
        topic: 'kubernetes',
        label: 'Kubernetes',
        targetLevel: 'concept',
        reason: '岗位提到 Kubernetes',
        source: 'jd_requirement',
        sourceIds: [],
      },
    ],
    turns: [
      {
        turnIndex: 0,
        role: 'interviewer',
        content: QUESTION_ONE,
        topic: 'python',
        level: 'concept',
        score: null,
      },
    ],
    scorecard: null,
    meta: meta(),
    ...overrides,
  };
}

export function turnResponse(
  overrides: Partial<InterviewTurnResponse> = {},
): InterviewTurnResponse {
  return {
    sessionId: SESSION_ID,
    status: 'in_progress',
    currentLevel: 'concept',
    evaluation: evaluation(),
    difficultyChange: held(),
    nextQuestion: { turnIndex: 2, content: QUESTION_TWO, topic: 'fastapi', level: 'concept' },
    meta: meta({ workflow: 'interview_turn' }),
    ...overrides,
  };
}

export function scorecard(overrides: Partial<InterviewScorecard> = {}): InterviewScorecard {
  return {
    interviewId: SESSION_ID,
    mode: 'technical',
    overallScore: 66.9,
    dimensions: [
      { key: 'technical_accuracy', label: '技术准确性', score: 49.9, comment: '' },
      { key: 'communication', label: '表达沟通', score: 71.4, comment: '' },
      { key: 'depth', label: '技术深度', score: 45.7, comment: '' },
      { key: 'problem_solving', label: '问题解决', score: 47.4, comment: '' },
      { key: 'engineering_thinking', label: '工程思维', score: 44.9, comment: '' },
      { key: 'confidence', label: '自信度', score: 55.1, comment: '' },
      {
        key: 'evidence_consistency',
        label: '证据一致性',
        score: 100,
        comment: '口述内容与证据图谱一致',
      },
    ],
    strengths: ['覆盖了「为什么」', '覆盖了「因为」'],
    weaknesses: [
      '回答长度 24 字，覆盖了 0/7 个期望要点。（本地规则引擎评估，仅反映要点覆盖度，不代表技术正确性）',
    ],
    missingKnowledge: ['未提及「cost」', '未提及「trade」'],
    followUpTopics: ['cost', 'trade'],
    evidenceConflicts: [],
    perQuestion: [
      {
        turnIndex: 0,
        topic: 'python',
        level: 'concept',
        verdict: 'strong',
        question: QUESTION_ONE,
        answer:
          '可变默认参数的问题在于函数定义时就求值，默认参数只创建一次，所以多次调用会共享同一个引用。',
        suggestedAnswer: '',
        missingKnowledge: ['未提及「cost」'],
        followUpTopics: ['cost'],
      },
      {
        // The last question is never answered, and `_scorecard` still reports verdict=mixed for it.
        turnIndex: 2,
        topic: 'fastapi',
        level: 'concept',
        verdict: 'mixed',
        question: QUESTION_TWO,
        answer: '',
        suggestedAnswer: '',
        missingKnowledge: [],
        followUpTopics: [],
      },
    ],
    difficultyStart: 'concept',
    difficultyEnd: 'concept',
    /** Hard-coded by the backend: "not measured", not "0 seconds". */
    durationSeconds: 0,
    algorithmVersion: 'scorecard@1.0.0',
    ...overrides,
  };
}

export function jobList(): JobList {
  return {
    items: [
      {
        id: JOB_ID,
        role: '高级后端工程师（AI 应用方向）',
        company: null,
        parseStatus: 'heuristic_fallback',
        parseConfidence: 0.85,
        matchScore: null,
        requiredCount: 7,
        preferredCount: 2,
        bonusCount: 0,
        createdAt: '2026-09-25T16:28:40.145934Z',
      },
    ],
    total: 1,
  };
}

export function jobDetail(): JobDetail {
  return {
    ...jobList().items[0]!,
    // The stored analysis: exactly what `StartInterviewRequest.job` accepts. No `warnings` key —
    // that one only exists on the `POST /jobs/analyze` response.
    analysis: {
      role: '高级后端工程师（AI 应用方向）',
      required_skills: [
        { raw_text: 'Python', requirement: 'required', canonical_id: 'python' },
        { raw_text: 'FastAPI', requirement: 'required', canonical_id: 'fastapi' },
      ],
      parse_status: 'heuristic_fallback',
      parser_version: 'jd@1.0.0',
    },
    skills: [
      { canonicalId: 'python', rawText: 'Python', requirement: 'required' },
      { canonicalId: 'fastapi', rawText: 'FastAPI', requirement: 'required' },
    ],
  };
}

export function skillTree(): SkillTree {
  return {
    jobId: JOB_ID,
    role: '高级后端工程师（AI 应用方向）',
    required: [
      { canonicalId: 'python', rawText: 'Python', requirement: 'required' },
      { canonicalId: 'fastapi', rawText: 'FastAPI', requirement: 'required' },
    ],
    preferred: [{ canonicalId: 'kubernetes', rawText: 'Kubernetes', requirement: 'preferred' }],
    bonus: [],
    unmatchedCount: 0,
  };
}

export function capabilities(
  overrides: Partial<InterviewCapabilities> = {},
): InterviewCapabilities {
  return {
    provider: 'heuristic',
    providerChain: ['heuristic'],
    degraded: true,
    retrievalAvailable: false,
    sessionStore: 'in-process',
    activeInterviewSessions: 0,
    limitations: ['AI 端点为无状态实现：输入直接来自请求体，尚未与 jobs/evidence 表持久化打通'],
    ...overrides,
  };
}
