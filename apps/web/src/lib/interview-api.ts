import { ApiError } from '@careerforge/shared';

import { api } from './api';

/**
 * `/ai/interview/*` — the Interview Simulator's wire contract, verified against a live stack.
 *
 * **The contract is `apps/api/src/careerforge_api/schemas/ai.py`, not `docs/API.md` §2.8.**
 * That section describes a planned `/interview/*` API with `{ success, data }` envelopes,
 * camelCase (`interviewId`, `difficultyChange`) and a `jobId` parameter. What is mounted is
 * `/ai/interview/*`, snake_case, no `jobId` — the job arrives as the parsed `JDAnalysis` object
 * in the body. This module follows the code, and every guard names the field it expected, so a
 * drift in either direction fails loudly instead of rendering blanks.
 *
 * The envelope is applied by `EnvelopeMiddleware` and unwrapped by `@careerforge/shared`'s
 * client, which `./api` already configures — so these functions see `data`, not the envelope.
 */

/* ── domain types (mirrors careerforge_api.schemas.ai) ─────────────────────── */

/** The modes `InterviewMode` defines. `mixed` does not exist, so it is not offered. */
export const INTERVIEW_MODES = [
  'technical',
  'project',
  'behavioral',
  'system_design',
  'hr',
] as const;
export type InterviewModeValue = (typeof INTERVIEW_MODES)[number];

export const DIFFICULTY_LEVELS = ['concept', 'engineering', 'debugging'] as const;
export type DifficultyValue = (typeof DIFFICULTY_LEVELS)[number];

export type InterviewRole = 'interviewer' | 'candidate' | 'system';

export interface AiMeta {
  provider: string;
  model: string | null;
  promptVersion: string | null;
  /** `true` for every run without a key — the UI is required to say so. */
  degraded: boolean;
  degradedReason: string | null;
  workflow: string | null;
  runId: string | null;
  latencyMs: number | null;
  cacheHit: boolean;
  warnings: string[];
}

export interface PlanItem {
  topic: string;
  label: string;
  targetLevel: DifficultyValue | null;
  reason: string;
  /** `evidence | gap | jd_requirement | resume` — why this topic is in the plan. */
  source: string;
  sourceIds: string[];
}

export interface TurnEvaluation {
  turnIndex: number;
  score: number;
  technicalAccuracy: number;
  depth: number;
  communication: number;
  problemSolving: number;
  engineeringThinking: number;
  confidence: number;
  missingKnowledge: string[];
  feedback: string;
  strongPoints: string[];
  followUpTopics: string[];
  suggestedAnswer: string;
}

export interface DifficultyChange {
  fromLevel: DifficultyValue | null;
  toLevel: DifficultyValue | null;
  reason: string;
}

export interface SessionTurn {
  turnIndex: number;
  role: InterviewRole;
  content: string;
  topic: string | null;
  level: DifficultyValue | null;
  /** Per-answer score. `null` on interviewer turns, and on turns that were never scored. */
  score: number | null;
  /**
   * The full evaluation, attached client-side by the turn mutation.
   *
   * `GET /ai/interview/{id}` returns only `score` per turn (see `_session_payload`), so this is
   * present for the turn just answered in this tab and absent after a reload. The UI says so
   * rather than showing an empty panel.
   */
  evaluation?: TurnEvaluation | null;
  /**
   * The difficulty transition that followed this answer, also attached client-side.
   *
   * The API reports one per turn response — including "no change" turns, with a reason. Keeping
   * it on the turn is what lets the notice render only where `fromLevel !== toLevel`.
   */
  difficultyChange?: DifficultyChange | null;
}

export interface InterviewQuestion {
  turnIndex: number;
  content: string;
  topic: string | null;
  level: DifficultyValue | null;
}

export interface ScorecardDimension {
  key: string;
  label: string;
  score: number;
  comment: string;
}

export interface QuestionReview {
  turnIndex: number;
  topic: string;
  level: DifficultyValue | null;
  verdict: string;
  question: string;
  answer: string;
  suggestedAnswer: string;
  missingKnowledge: string[];
  followUpTopics: string[];
}

export interface EvidenceConflict {
  statement: string;
  evidenceState: string;
  severity: string;
  advice: string;
}

export interface InterviewScorecard {
  interviewId: string | null;
  mode: string;
  overallScore: number;
  dimensions: ScorecardDimension[];
  strengths: string[];
  weaknesses: string[];
  missingKnowledge: string[];
  followUpTopics: string[];
  evidenceConflicts: EvidenceConflict[];
  perQuestion: QuestionReview[];
  difficultyStart: DifficultyValue | null;
  difficultyEnd: DifficultyValue | null;
  /** Hard-coded `0` by `_scorecard` — never a measurement, so the UI does not print "0s". */
  durationSeconds: number | null;
  algorithmVersion: string;
}

export interface InterviewSession {
  sessionId: string;
  mode: string;
  status: string;
  currentLevel: DifficultyValue | null;
  plan: PlanItem[];
  turns: SessionTurn[];
  scorecard: InterviewScorecard | null;
  meta: AiMeta;
}

export interface InterviewTurnResponse {
  sessionId: string;
  status: string;
  currentLevel: DifficultyValue | null;
  evaluation: TurnEvaluation | null;
  difficultyChange: DifficultyChange | null;
  nextQuestion: InterviewQuestion | null;
  meta: AiMeta;
}

export interface StartInterviewInput {
  mode: InterviewModeValue;
  /** The parsed `JDAnalysis`, exactly as `GET /jobs/{id}` returns it in `analysis`. */
  job: Record<string, unknown> | null;
  /** 1–3, mirroring `DifficultyLevel.from_level`. */
  difficulty: number;
}

/* ── primitive readers (shared with ./interview-target-api) ────────────────── */

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** A field the API may legitimately report as `null`. Missing counts as `null`, never as `0`. */
export function nullableNum(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function nullableStr(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

/** A difficulty the UI has not seen before is passed through, not coerced to a known one. */
export function nullableLevel(value: unknown): DifficultyValue | null {
  return typeof value === 'string' && value ? (value as DifficultyValue) : null;
}

export interface Reader {
  str(field: string, value: unknown): string;
  num(field: string, value: unknown): number;
  bool(field: string, value: unknown): boolean;
  obj(field: string, value: unknown): Record<string, unknown>;
  arr(field: string, value: unknown): unknown[];
  strs(field: string, value: unknown): string[];
}

/**
 * Bind the expected-field message to one response body.
 *
 * `GET /ai/interview/{id}` and the turn response are the only place a type error can enter the
 * page, so the failure has to say *which* field disagreed — a generic "invalid response" turns a
 * contract drift into a blank screen with no lead.
 */
export function reader(path: string, body: unknown): Reader {
  const bad = (field: string): never => {
    throw new ApiError({
      code: 'INVALID_RESPONSE',
      message: `${path} 的响应缺少或类型错误的字段「${field}」，与 apps/api/src/careerforge_api/schemas/ai.py 不一致`,
      requestId: null,
      status: 200,
      body,
    });
  };
  return {
    str: (field, value) => (typeof value === 'string' ? value : bad(field)),
    num: (field, value) =>
      typeof value === 'number' && Number.isFinite(value) ? value : bad(field),
    bool: (field, value) => (typeof value === 'boolean' ? value : bad(field)),
    obj: (field, value) => (isRecord(value) ? value : bad(field)),
    arr: (field, value) => (Array.isArray(value) ? value : bad(field)),
    strs: (field, value) =>
      Array.isArray(value)
        ? value.map((item) => (typeof item === 'string' ? item : JSON.stringify(item)))
        : bad(field),
  };
}

/* ── parsers ───────────────────────────────────────────────────────────────── */

export function parseMeta(value: unknown, path: string, body: unknown): AiMeta {
  const r = reader(path, body);
  const meta = r.obj('meta', value);
  return {
    provider: r.str('meta.provider', meta['provider']),
    model: nullableStr(meta['model']),
    promptVersion: nullableStr(meta['prompt_version']),
    degraded: typeof meta['degraded'] === 'boolean' ? meta['degraded'] : false,
    degradedReason: nullableStr(meta['degraded_reason']),
    workflow: nullableStr(meta['workflow']),
    runId: nullableStr(meta['run_id']),
    latencyMs: nullableNum(meta['latency_ms']),
    cacheHit: meta['cache_hit'] === true,
    warnings: Array.isArray(meta['warnings'])
      ? meta['warnings'].filter((item): item is string => typeof item === 'string')
      : [],
  };
}

function parsePlanItem(value: unknown, path: string, body: unknown): PlanItem {
  const r = reader(path, body);
  const item = r.obj('plan[]', value);
  return {
    topic: r.str('plan[].topic', item['topic']),
    label: nullableStr(item['label']) ?? '',
    targetLevel: nullableLevel(item['target_level']),
    reason: nullableStr(item['reason']) ?? '',
    source: nullableStr(item['source']) ?? 'unknown',
    sourceIds: Array.isArray(item['source_ids'])
      ? item['source_ids'].filter((id): id is string => typeof id === 'string')
      : [],
  };
}

function parseTurn(value: unknown, path: string, body: unknown): SessionTurn {
  const r = reader(path, body);
  const turn = r.obj('turns[]', value);
  const role = r.str('turns[].role', turn['role']);
  if (role !== 'interviewer' && role !== 'candidate' && role !== 'system') {
    r.str('turns[].role (interviewer | candidate | system)', undefined);
  }
  return {
    turnIndex: r.num('turns[].turn_index', turn['turn_index']),
    role: role as InterviewRole,
    content: r.str('turns[].content', turn['content']),
    topic: nullableStr(turn['topic']),
    level: nullableLevel(turn['level']),
    score: nullableNum(turn['score']),
  };
}

function parseEvaluation(value: unknown, path: string, body: unknown): TurnEvaluation {
  const r = reader(path, body);
  const item = r.obj('evaluation', value);
  return {
    turnIndex: r.num('evaluation.turn_index', item['turn_index']),
    score: r.num('evaluation.score', item['score']),
    technicalAccuracy: r.num('evaluation.technical_accuracy', item['technical_accuracy']),
    depth: r.num('evaluation.depth', item['depth']),
    communication: r.num('evaluation.communication', item['communication']),
    problemSolving: r.num('evaluation.problem_solving', item['problem_solving']),
    engineeringThinking: r.num('evaluation.engineering_thinking', item['engineering_thinking']),
    confidence: r.num('evaluation.confidence', item['confidence']),
    missingKnowledge: r.strs('evaluation.missing_knowledge', item['missing_knowledge']),
    feedback: nullableStr(item['feedback']) ?? '',
    strongPoints: r.strs('evaluation.strong_points', item['strong_points']),
    followUpTopics: r.strs('evaluation.follow_up_topics', item['follow_up_topics']),
    suggestedAnswer: nullableStr(item['suggested_answer']) ?? '',
  };
}

function parseDifficultyChange(value: unknown, path: string, body: unknown): DifficultyChange {
  const r = reader(path, body);
  const change = r.obj('difficulty_change', value);
  return {
    fromLevel: nullableLevel(change['from_level']),
    toLevel: nullableLevel(change['to_level']),
    reason: r.str('difficulty_change.reason', change['reason']),
  };
}

function parseQuestion(value: unknown, path: string, body: unknown): InterviewQuestion {
  const r = reader(path, body);
  const question = r.obj('next_question', value);
  return {
    turnIndex: r.num('next_question.turn_index', question['turn_index']),
    content: r.str('next_question.content', question['content']),
    topic: nullableStr(question['topic']),
    level: nullableLevel(question['level']),
  };
}

function parseDimension(value: unknown, path: string, body: unknown): ScorecardDimension {
  const r = reader(path, body);
  const item = r.obj('scorecard.dimensions[]', value);
  return {
    key: r.str('scorecard.dimensions[].key', item['key']),
    label: nullableStr(item['label']) ?? '',
    score: r.num('scorecard.dimensions[].score', item['score']),
    comment: nullableStr(item['comment']) ?? '',
  };
}

function parseReview(value: unknown, path: string, body: unknown): QuestionReview {
  const r = reader(path, body);
  const item = r.obj('scorecard.per_question[]', value);
  return {
    turnIndex: r.num('scorecard.per_question[].turn_index', item['turn_index']),
    topic: nullableStr(item['topic']) ?? '',
    level: nullableLevel(item['level']),
    verdict: nullableStr(item['verdict']) ?? '',
    question: nullableStr(item['question']) ?? '',
    answer: nullableStr(item['answer']) ?? '',
    suggestedAnswer: nullableStr(item['suggested_answer']) ?? '',
    missingKnowledge: r.strs(
      'scorecard.per_question[].missing_knowledge',
      item['missing_knowledge'],
    ),
    followUpTopics: r.strs('scorecard.per_question[].follow_up_topics', item['follow_up_topics']),
  };
}

function parseConflict(value: unknown, path: string, body: unknown): EvidenceConflict {
  const r = reader(path, body);
  const item = r.obj('scorecard.evidence_conflicts[]', value);
  return {
    statement: nullableStr(item['statement']) ?? '',
    evidenceState: nullableStr(item['evidence_state']) ?? '',
    severity: nullableStr(item['severity']) ?? 'medium',
    advice: nullableStr(item['advice']) ?? '',
  };
}

function parseScorecard(value: unknown, path: string, body: unknown): InterviewScorecard {
  const r = reader(path, body);
  const card = r.obj('scorecard', value);
  return {
    interviewId: nullableStr(card['interview_id']),
    mode: nullableStr(card['mode']) ?? '',
    overallScore: r.num('scorecard.overall_score', card['overall_score']),
    dimensions: r
      .arr('scorecard.dimensions', card['dimensions'])
      .map((item) => parseDimension(item, path, body)),
    strengths: r.strs('scorecard.strengths', card['strengths']),
    weaknesses: r.strs('scorecard.weaknesses', card['weaknesses']),
    missingKnowledge: r.strs('scorecard.missing_knowledge', card['missing_knowledge']),
    followUpTopics: r.strs('scorecard.follow_up_topics', card['follow_up_topics']),
    evidenceConflicts: r
      .arr('scorecard.evidence_conflicts', card['evidence_conflicts'])
      .map((item) => parseConflict(item, path, body)),
    perQuestion: r
      .arr('scorecard.per_question', card['per_question'])
      .map((item) => parseReview(item, path, body)),
    difficultyStart: nullableLevel(card['difficulty_start']),
    difficultyEnd: nullableLevel(card['difficulty_end']),
    // `duration_seconds` is hard-coded to 0 by the scorecard builder: a 0 that means
    // "not measured" must not be rendered as "0 seconds".
    durationSeconds: nullableNum(card['duration_seconds']),
    algorithmVersion: nullableStr(card['algorithm_version']) ?? '',
  };
}

export function parseSession(payload: unknown, path: string): InterviewSession {
  const r = reader(path, payload);
  const body = r.obj('session', payload);
  return {
    sessionId: r.str('session_id', body['session_id']),
    mode: r.str('mode', body['mode']),
    status: r.str('status', body['status']),
    currentLevel: nullableLevel(body['current_level']),
    plan: r.arr('plan', body['plan']).map((item) => parsePlanItem(item, path, body)),
    turns: r.arr('turns', body['turns']).map((turn) => parseTurn(turn, path, body)),
    scorecard:
      body['scorecard'] === null || body['scorecard'] === undefined
        ? null
        : parseScorecard(body['scorecard'], path, body),
    meta: parseMeta(body['meta'], path, body),
  };
}

export function parseTurnResponse(payload: unknown, path: string): InterviewTurnResponse {
  const r = reader(path, payload);
  const body = r.obj('turn', payload);
  return {
    sessionId: r.str('session_id', body['session_id']),
    status: r.str('status', body['status']),
    currentLevel: nullableLevel(body['current_level']),
    evaluation:
      body['evaluation'] === null || body['evaluation'] === undefined
        ? null
        : parseEvaluation(body['evaluation'], path, body),
    difficultyChange:
      body['difficulty_change'] === null || body['difficulty_change'] === undefined
        ? null
        : parseDifficultyChange(body['difficulty_change'], path, body),
    nextQuestion:
      body['next_question'] === null || body['next_question'] === undefined
        ? null
        : parseQuestion(body['next_question'], path, body),
    meta: parseMeta(body['meta'], path, body),
  };
}

/* ── endpoints ─────────────────────────────────────────────────────────────── */

const START = 'POST /ai/interview/start';
const ANSWER = 'POST /ai/interview/{id}/answer';
const FINISH = 'POST /ai/interview/{id}/finish';
const SESSION = 'GET /ai/interview/{id}';

export const interviewApi = {
  async startSession(input: StartInterviewInput): Promise<InterviewSession> {
    const data = await api.post<unknown>('/ai/interview/start', {
      mode: input.mode,
      job: input.job,
      difficulty: input.difficulty,
    });
    return parseSession(data, START);
  },

  async answer(sessionId: string, answer: string): Promise<InterviewTurnResponse> {
    const data = await api.post<unknown>(`/ai/interview/${sessionId}/answer`, { answer });
    return parseTurnResponse(data, ANSWER);
  },

  async finish(sessionId: string): Promise<InterviewSession> {
    const data = await api.post<unknown>(`/ai/interview/${sessionId}/finish`, undefined);
    return parseSession(data, FINISH);
  },

  async session(sessionId: string): Promise<InterviewSession> {
    const data = await api.get<unknown>(`/ai/interview/${sessionId}`);
    return parseSession(data, SESSION);
  },

  /** `DELETE` is not one of `./api`'s typed shortcuts, so it goes through `request`. */
  async abandon(sessionId: string): Promise<void> {
    await api.request<void>(`/ai/interview/${sessionId}`, { method: 'DELETE' });
  },
} as const;
