import { ApiError } from '@careerforge/shared';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { interviewApi, parseSession, parseTurnResponse } from '@/lib/interview-api';

import { QUESTION_ONE, SESSION_ID } from '@/components/interview/interview-fixtures';

/**
 * The guards, against the payload the live stack actually returns.
 *
 * These fixtures are **wire-shaped** (snake_case, `difficulty_change`, `turn_index`), captured from
 * the running API — not the camelCase domain objects the components take. The distinction is the
 * whole point of this file: `docs/API.md` §2.8 documents camelCase `/interview/*` endpoints with an
 * `interviewId`, and the mounted API speaks snake_case `/ai/interview/*`. A guard tested against
 * the documented shape would pass while the page failed.
 *
 * Two different failures are being defended here:
 *
 * 1. **A shape change must be loud.** The turn response is the only place the page learns the
 *    evaluation and the difficulty transition; if `difficulty_change` were renamed, a silent UI
 *    would show a session that never adapts. The guard throws `INVALID_RESPONSE` naming the field.
 * 2. **A `null` must stay a `null`.** Interviewer turns carry `score: null` and sessions carry
 *    `scorecard: null`; both mean "not measured". Coercing either to `0` would put a fabricated
 *    zero on screen, which this project's product rules forbid outright.
 */

const ANSWER_PATH = 'POST /ai/interview/{id}/answer';
const SESSION_PATH = 'GET /ai/interview/{id}';

function wireMeta(overrides: Record<string, unknown> = {}) {
  return {
    provider: 'heuristic',
    model: null,
    prompt_version: 'interviewer@v1',
    degraded: true,
    degraded_reason: 'no_api_key',
    workflow: 'interview_start',
    run_id: '5e7ff964-9f00-426f-93fb-49285fa87b36',
    latency_ms: 2,
    cache_hit: false,
    warnings: ['面试已降级运行（原因：no_api_key）'],
    ...overrides,
  };
}

function wireEvaluation(overrides: Record<string, unknown> = {}) {
  return {
    turn_index: 2,
    score: 68.58,
    technical_accuracy: 0.657,
    depth: 0.657,
    communication: 0.9,
    problem_solving: 0.624,
    engineering_thinking: 0.591,
    confidence: 0.91,
    missing_knowledge: ['未提及「cost」', '未提及「trade」'],
    feedback: '回答长度 220 字，覆盖了 4/7 个期望要点。',
    strong_points: ['覆盖了「为什么」'],
    follow_up_topics: ['cost'],
    suggested_answer: '',
    ...overrides,
  };
}

function wireTurn(overrides: Record<string, unknown> = {}) {
  return {
    session_id: SESSION_ID,
    status: 'in_progress',
    current_level: 'concept',
    evaluation: wireEvaluation(),
    difficulty_change: {
      from_level: 'concept',
      to_level: 'concept',
      reason: '回答得分 69，保持当前难度',
    },
    next_question: {
      turn_index: 2,
      content: 'FastAPI 的依赖注入是怎么工作的？你用它解决了什么问题？',
      topic: 'fastapi',
      level: 'concept',
    },
    meta: wireMeta(),
    ...overrides,
  };
}

function wireSession(overrides: Record<string, unknown> = {}) {
  return {
    session_id: SESSION_ID,
    mode: 'technical',
    status: 'in_progress',
    current_level: 'concept',
    plan: [
      {
        topic: 'python',
        label: 'Python',
        target_level: 'concept',
        reason: '岗位必备 Python，但证据图谱中没有支撑，面试中很可能被追问',
        source: 'gap',
        source_ids: [],
        covered: false,
      },
    ],
    turns: [
      {
        turn_index: 0,
        role: 'interviewer',
        content: QUESTION_ONE,
        topic: 'python',
        level: 'concept',
        score: null,
      },
      {
        turn_index: 1,
        role: 'candidate',
        content: '我用 None 作为默认值，避免共享可变对象。',
        topic: 'python',
        level: null,
        score: 72.5,
      },
    ],
    scorecard: null,
    meta: wireMeta(),
    ...overrides,
  };
}

function stubFetch(payload: unknown, status = 200) {
  const body = JSON.stringify({ success: true, data: payload, error: null, requestId: 'req_test' });
  const fetchMock = vi.fn(async () => ({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null },
    text: async () => body,
  }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('parseTurnResponse', () => {
  it('accepts the live turn shape and maps it to the domain names', () => {
    const parsed = parseTurnResponse(wireTurn(), ANSWER_PATH);
    expect(parsed.evaluation?.score).toBe(68.58);
    expect(parsed.evaluation?.technicalAccuracy).toBe(0.657);
    expect(parsed.evaluation?.missingKnowledge).toEqual(['未提及「cost」', '未提及「trade」']);
    expect(parsed.difficultyChange?.fromLevel).toBe('concept');
    expect(parsed.difficultyChange?.reason).toBe('回答得分 69，保持当前难度');
    expect(parsed.nextQuestion?.topic).toBe('fastapi');
    expect(parsed.currentLevel).toBe('concept');
    expect(parsed.meta.degraded).toBe(true);
  });

  it('accepts null evaluation / change / question (all three are legal)', () => {
    const parsed = parseTurnResponse(
      wireTurn({ evaluation: null, difficulty_change: null, next_question: null }),
      ANSWER_PATH,
    );
    expect(parsed.evaluation).toBeNull();
    expect(parsed.difficultyChange).toBeNull();
    expect(parsed.nextQuestion).toBeNull();
  });

  it('reports an unusable level as null rather than inventing one', () => {
    const parsed = parseTurnResponse(wireTurn({ current_level: 2 }), ANSWER_PATH);
    expect(parsed.currentLevel).toBeNull();
  });

  it('names the field it expected, one at a time', () => {
    expect(() => parseTurnResponse(wireTurn({ session_id: undefined }), ANSWER_PATH)).toThrow(
      /session_id/,
    );
    expect(() => parseTurnResponse(wireTurn({ status: 200 }), ANSWER_PATH)).toThrow(/status/);

    const noScore = wireTurn({ evaluation: wireEvaluation({ score: undefined }) });
    expect(() => parseTurnResponse(noScore, ANSWER_PATH)).toThrow(/evaluation\.score/);

    // A string where the list belongs is a rejected shape, not a silently wrapped one.
    const notAList = wireTurn({
      evaluation: wireEvaluation({ missing_knowledge: '未提及「cost」' }),
    });
    expect(() => parseTurnResponse(notAList, ANSWER_PATH)).toThrow(/evaluation\.missing_knowledge/);

    const noReason = wireTurn({
      difficulty_change: { from_level: 'concept', to_level: 'engineering' },
    });
    expect(() => parseTurnResponse(noReason, ANSWER_PATH)).toThrow(/difficulty_change\.reason/);
  });

  it('reports the code the UI keys off, and carries the raw body', () => {
    try {
      parseTurnResponse({ session_id: SESSION_ID }, ANSWER_PATH);
      expect.unreachable('the guard should have thrown');
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      const apiError = error as ApiError;
      expect(apiError.code).toBe('INVALID_RESPONSE');
      expect(apiError.message).toContain(ANSWER_PATH);
      expect(apiError.message).toContain('apps/api/src/careerforge_api/schemas/ai.py');
      expect(apiError.status).toBe(200);
    }
  });
});

describe('parseSession', () => {
  it('accepts the live session shape and keeps unscored turns null', () => {
    const parsed = parseSession(wireSession(), SESSION_PATH);
    expect(parsed.turns[0]?.score).toBeNull();
    expect(parsed.turns[1]?.score).toBe(72.5);
    expect(parsed.scorecard).toBeNull();
    expect(parsed.plan[0]?.source).toBe('gap');
    // `covered` is dropped on purpose: the backend never writes it, so the UI derives coverage
    // from the turns instead of reading a field that is always false.
    expect('covered' in (parsed.plan[0] as object)).toBe(false);
  });

  it('rejects an unknown turn role', () => {
    const payload = wireSession({
      turns: [
        { turn_index: 0, role: 'judge', content: 'x', topic: null, level: null, score: null },
      ],
    });
    expect(() => parseSession(payload, SESSION_PATH)).toThrow(/turns\[\]\.role/);
  });

  it('keeps an unknown difficulty string instead of mapping it to a known level', () => {
    const parsed = parseSession(wireSession({ current_level: 'architect' }), SESSION_PATH);
    expect(parsed.currentLevel).toBe('architect');
  });

  it('parses the finished session scorecard the API actually sends', () => {
    const parsed = parseSession(
      wireSession({
        status: 'completed',
        scorecard: {
          interview_id: SESSION_ID,
          mode: 'technical',
          overall_score: 66.9,
          dimensions: [
            { key: 'technical_accuracy', label: '技术准确性', score: 49.9, comment: '' },
            {
              key: 'evidence_consistency',
              label: '证据一致性',
              score: 100,
              comment: '口述内容与证据图谱一致',
            },
          ],
          strengths: ['覆盖了「为什么」'],
          weaknesses: [],
          missing_knowledge: ['未提及「cost」'],
          follow_up_topics: ['cost'],
          evidence_conflicts: [],
          per_question: [
            {
              turn_index: 0,
              topic: 'python',
              level: 'concept',
              verdict: 'strong',
              question: QUESTION_ONE,
              answer: '…',
              suggested_answer: '',
              missing_knowledge: [],
              follow_up_topics: [],
            },
          ],
          difficulty_start: 'concept',
          difficulty_end: 'engineering',
          duration_seconds: 0,
          algorithm_version: 'scorecard@1.0.0',
        },
      }),
      SESSION_PATH,
    );

    expect(parsed.status).toBe('completed');
    expect(parsed.scorecard?.overallScore).toBe(66.9);
    expect(parsed.scorecard?.dimensions.map((dimension) => dimension.key)).toEqual([
      'technical_accuracy',
      'evidence_consistency',
    ]);
    expect(parsed.scorecard?.durationSeconds).toBe(0);
    expect(parsed.scorecard?.perQuestion[0]?.verdict).toBe('strong');
  });
});

describe('interviewApi endpoints', () => {
  it('posts the parsed job (not an id) to /ai/interview/start', async () => {
    const fetchMock = stubFetch(wireSession());
    const job = { role: '高级后端工程师', required_skills: [] };
    const started = await interviewApi.startSession({ mode: 'technical', job, difficulty: 2 });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain('/ai/interview/start');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ mode: 'technical', job, difficulty: 2 });
    expect(started.sessionId).toBe(SESSION_ID);
  });

  it('sends the answer text and reads the turn response', async () => {
    const fetchMock = stubFetch(wireTurn());
    const result = await interviewApi.answer(SESSION_ID, '我的回答');
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain(`/ai/interview/${SESSION_ID}/answer`);
    expect(JSON.parse(String(init.body))).toEqual({ answer: '我的回答' });
    expect(result.evaluation?.score).toBe(68.58);
  });

  it('finishes with an empty POST and reads the scorecard back', async () => {
    const fetchMock = stubFetch(wireSession({ status: 'completed' }));
    const finished = await interviewApi.finish(SESSION_ID);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain(`/ai/interview/${SESSION_ID}/finish`);
    expect(init.method).toBe('POST');
    expect(finished.status).toBe('completed');
  });

  it('reads a session by id, and deletes through the shared client', async () => {
    const fetchMock = stubFetch(wireSession({ status: 'completed' }));
    const resumed = await interviewApi.session(SESSION_ID);
    expect(resumed.status).toBe('completed');

    fetchMock.mockResolvedValueOnce({
      ok: true,
      status: 204,
      headers: { get: () => null },
      text: async () => '',
    });
    await interviewApi.abandon(SESSION_ID);
    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toContain(`/ai/interview/${SESSION_ID}`);
    expect(init.method).toBe('DELETE');
  });
});
