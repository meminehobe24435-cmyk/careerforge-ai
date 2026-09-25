import type {
  AiCosts,
  AiRun,
  AiRunDetail,
  AiRunList,
  AiStep,
  CacheStats,
  CostByAgent,
  CostByFeature,
  DailyCost,
  LlmCall,
  PromptVersion,
} from '@careerforge/shared';

/**
 * One valid payload per observability guard, shared by the two guard test files.
 *
 * They live here rather than inside a `*.test.ts` for two reasons. The mechanical one is the
 * 500-line guard: the run guards and the cache/prompt guards were one 541-line file. The better one
 * is that **a positive case must not drift between the files that assert it**: if `isAiRunList` and
 * `isAiRunDetail` disagree about what a valid run looks like, one of them is testing a payload the
 * API cannot produce, and a second copy of the fixture is how that happens.
 *
 * Every fixture is typed with the frozen contract type, so a change to `packages/shared` breaks the
 * fixtures at compile time instead of letting the guards quietly pass on a stale shape.
 */

/** Remove a key entirely, so a negative case is a *missing* field and not an `undefined` one. */
export function without<T extends object>(value: T, key: keyof T): Record<string, unknown> {
  // The cast is the point of the helper: the caller asks for a *missing* key, so the result is
  // deliberately no longer the guarded type.
  const copy: Record<string, unknown> = { ...(value as Record<string, unknown>) };
  delete copy[key as string];
  return copy;
}

export function run(overrides: Partial<AiRun> = {}): AiRun {
  return {
    id: 'run-1',
    userId: 'user-1',
    workflow: 'jd_analysis',
    agent: 'job',
    status: 'succeeded',
    trigger: 'api',
    provider: 'scripted',
    model: null,
    promptVersion: 'jd_analysis@v1',
    promptTokens: 120,
    completionTokens: 30,
    totalTokens: 150,
    cachedTokens: 0,
    costUsd: 0.0012,
    costCny: 0.0086,
    usageStatus: 'reported',
    latencyMs: 42,
    cacheHit: false,
    requestId: 'req_01',
    error: null,
    errorCode: null,
    stepCount: 4,
    startedAt: '2026-01-01T00:00:00Z',
    finishedAt: '2026-01-01T00:00:01Z',
    ...overrides,
  };
}

/** A run whose provider never reported usage: every count is `null`, not `0` (PHASE 13). */
export function unavailableRun(overrides: Partial<AiRun> = {}): AiRun {
  return run({
    provider: 'heuristic',
    promptTokens: null,
    completionTokens: null,
    totalTokens: null,
    cachedTokens: null,
    costUsd: null,
    costCny: null,
    usageStatus: 'unavailable',
    ...overrides,
  });
}

export function step(overrides: Partial<AiStep> = {}): AiStep {
  return {
    name: 'extract',
    status: 'ok',
    latencyMs: 40,
    provider: 'scripted',
    model: null,
    promptVersion: 'jd_analysis@v1',
    attempts: 1,
    cacheHit: false,
    tokens: 150,
    costUsd: 0.0012,
    usageStatus: 'reported',
    inputDigest: 'abcd1234',
    outputDigest: 'ef567890',
    errorCode: null,
    errorMessage: null,
    startedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export function call(overrides: Partial<LlmCall> = {}): LlmCall {
  return {
    id: 'call-1',
    agent: 'job',
    provider: 'scripted',
    model: '',
    operation: 'structured',
    promptVersion: null,
    promptTokens: 120,
    completionTokens: 30,
    totalTokens: 150,
    cachedTokens: 0,
    costUsd: 0.0012,
    costCny: 0.0086,
    usageStatus: 'reported',
    latencyMs: 41,
    status: 'ok',
    requestId: null,
    createdAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

export const RUN_LIST: AiRunList = { items: [run()], total: 1, limit: 50, offset: 0 };

export const RUN_DETAIL: AiRunDetail = {
  ...run(),
  steps: [step()],
  calls: [call()],
  inputRef: { role: '嵌入式软件工程师' },
  outputRef: { required: 5 },
};

export const DAY: DailyCost = {
  day: '2026-01-01',
  runs: 1,
  tokens: 150,
  costUsd: 0.0012,
  costCny: 0.0086,
};

export const COSTS: AiCosts = {
  range: '7d',
  days: [DAY],
  totals: { runs: 1, modelCalls: 1, tokens: 150, costUsd: 0.0012, costCny: 0.0086, latencyMs: 42 },
  dailyBudgetUsd: 5,
  unaccountedRuns: 0,
  notes: ['token 与成本来自 provider 自报的用量'],
};

export const AGENT_ROW: CostByAgent = {
  agent: 'job',
  runs: 2,
  tokens: 300,
  costUsd: 0.0024,
  costCny: 0.0172,
  avgLatencyMs: 41.5,
  cacheHits: 0,
};

export const FEATURE_ROW: CostByFeature = {
  feature: 'JD 分析',
  workflows: ['jd_analysis'],
  runs: 2,
  tokens: 300,
  costUsd: 0.0024,
  costCny: 0.0172,
};

export const CACHE_STATS: CacheStats = {
  byKind: [
    { kind: 'llm', entries: 1, hits: 2, bytes: 208 },
    { kind: 'embedding', entries: 0, hits: 0, bytes: 0 },
    { kind: 'tool', entries: 0, hits: 0, bytes: 0 },
  ],
  persistedHits: 2,
  process: {
    processHits: 2,
    processMisses: 1,
    processEntries: 1,
    eventsFlushed: 3,
    hitRate: 0.6667,
  },
};

export const PROMPT_ROW: PromptVersion = {
  name: 'jd_analysis',
  version: 1,
  sha256: 'abcdef0123456789',
  isActive: true,
  updatedAt: '2026-01-01T00:00:00Z',
};
