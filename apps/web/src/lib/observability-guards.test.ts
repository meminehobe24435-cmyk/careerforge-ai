import { describe, expect, it } from 'vitest';

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
import {
  isAiCosts,
  isAiRunDetail,
  isAiRunList,
  isCacheStats,
  isCostByAgentList,
  isCostByFeatureList,
  isPromptVersionList,
} from '@careerforge/shared';

/**
 * Negative tests for the seven observability guards (API.md §2.12).
 *
 * These are the guards that stand between a malformed payload and a page that renders a number
 * nobody measured. Each one is checked from both sides: a *valid* payload (typed with the frozen
 * contract type, so the positive case cannot drift away from the interface it guards) must pass,
 * and a payload that is genuinely different — a removed key, a string where a number belongs, a
 * status outside the enum, a negative count, `hitRate: 'x'` — must be rejected.
 *
 * Where a guard does **not** reject something the list above would suggest, that is asserted as
 * an accepted case and named in the test, rather than left for a reader to discover. The guards
 * are documented as being about "presence and type, not about totals", and the tests below pin
 * exactly which of the two jobs each one actually does.
 */

/** Remove a key entirely, so the negative case is a *missing* field and not an `undefined` one. */
function without<T extends object>(value: T, key: keyof T): Record<string, unknown> {
  // The cast is the point of the helper: the caller asks for a *missing* key, so the result is
  // deliberately no longer the guarded type.
  const copy: Record<string, unknown> = { ...(value as Record<string, unknown>) };
  delete copy[key as string];
  return copy;
}

function run(overrides: Partial<AiRun> = {}): AiRun {
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
    costUsd: 0.0012,
    costCny: 0.0086,
    latencyMs: 42,
    cacheHit: false,
    requestId: 'req_01',
    error: null,
    stepCount: 4,
    startedAt: '2026-01-01T00:00:00Z',
    finishedAt: '2026-01-01T00:00:01Z',
    ...overrides,
  };
}

function step(overrides: Partial<AiStep> = {}): AiStep {
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
    inputDigest: 'abcd1234',
    outputDigest: 'ef567890',
    errorCode: null,
    errorMessage: null,
    startedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function call(overrides: Partial<LlmCall> = {}): LlmCall {
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
    costUsd: 0.0012,
    costCny: 0.0086,
    latencyMs: 41,
    status: 'ok',
    createdAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

const RUN_LIST: AiRunList = { items: [run()], total: 1, limit: 50, offset: 0 };
const RUN_DETAIL: AiRunDetail = {
  ...run(),
  steps: [step()],
  calls: [call()],
  inputRef: { role: '嵌入式软件工程师' },
  outputRef: { required: 5 },
};
const DAY: DailyCost = {
  day: '2026-01-01',
  runs: 1,
  tokens: 150,
  costUsd: 0.0012,
  costCny: 0.0086,
};
const COSTS: AiCosts = {
  range: '7d',
  days: [DAY],
  totals: { runs: 1, modelCalls: 1, tokens: 150, costUsd: 0.0012, costCny: 0.0086, latencyMs: 42 },
  dailyBudgetUsd: 5,
  notes: ['token 与成本来自 provider 自报的用量'],
};
const AGENT_ROW: CostByAgent = {
  agent: 'job',
  runs: 2,
  tokens: 300,
  costUsd: 0.0024,
  costCny: 0.0172,
  avgLatencyMs: 41.5,
  cacheHits: 0,
};
const FEATURE_ROW: CostByFeature = {
  feature: 'JD 分析',
  workflows: ['jd_analysis'],
  runs: 2,
  tokens: 300,
  costUsd: 0.0024,
  costCny: 0.0172,
};
const CACHE_STATS: CacheStats = {
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
const PROMPT_ROW: PromptVersion = {
  name: 'jd_analysis',
  version: 1,
  sha256: 'abcdef0123456789',
  isActive: true,
  updatedAt: '2026-01-01T00:00:00Z',
};

describe('isAiRunList', () => {
  it('accepts a list the AI Runs page can render', () => {
    expect(isAiRunList(RUN_LIST)).toBe(true);
    // A brand-new deployment: an empty page is a valid page.
    expect(isAiRunList({ items: [], total: 0, limit: 50, offset: 0 })).toBe(true);
  });

  it('rejects a run missing a field the page prints', () => {
    expect(isAiRunList({ ...RUN_LIST, items: [without(run(), 'agent')] })).toBe(false);
    expect(isAiRunList({ ...RUN_LIST, items: [without(run(), 'workflow')] })).toBe(false);
    expect(isAiRunList({ ...RUN_LIST, items: [without(run(), 'id')] })).toBe(false);
  });

  it('rejects a token count and a page total that are not numbers', () => {
    expect(
      isAiRunList({ ...RUN_LIST, items: [run({ totalTokens: '150' as unknown as number })] }),
    ).toBe(false);
    expect(isAiRunList({ ...RUN_LIST, total: '1' as unknown as number })).toBe(false);
    // A boolean where a flag is expected, the other way round.
    expect(
      isAiRunList({ ...RUN_LIST, items: [run({ cacheHit: 'false' as unknown as boolean })] }),
    ).toBe(false);
  });

  it('rejects a non-finite number, which is the only numeric check the guard makes', () => {
    expect(isAiRunList({ ...RUN_LIST, items: [run({ totalTokens: Number.NaN })] })).toBe(false);
    expect(
      isAiRunList({ ...RUN_LIST, items: [run({ stepCount: Number.POSITIVE_INFINITY })] }),
    ).toBe(false);
  });

  it('rejects anything that is not a list of runs', () => {
    expect(isAiRunList(null)).toBe(false);
    expect(isAiRunList('nope')).toBe(false);
    expect(isAiRunList({ ...RUN_LIST, items: 'nope' })).toBe(false);
    expect(isAiRunList(without(RUN_LIST, 'items'))).toBe(false);
  });

  it('accepts a negative count and an unknown status — it checks presence and type only', () => {
    // Documented hole, asserted so it cannot be mistaken for coverage: `isNumber` accepts any
    // finite number, and `status` is typed `AiRunStatus | (string & {})` on purpose so a new
    // server-side status cannot blank the page. Neither is a rejection this guard claims to make.
    expect(isAiRunList({ ...RUN_LIST, items: [run({ totalTokens: -5 })] })).toBe(true);
    expect(isAiRunList({ ...RUN_LIST, items: [run({ status: 'exploded' })] })).toBe(true);
    expect(isAiRunList({ ...RUN_LIST, items: [run({ costUsd: -0.5 })] })).toBe(true);
  });
});

describe('isAiRunDetail', () => {
  it('accepts a run with its step chain and calls', () => {
    expect(isAiRunDetail(RUN_DETAIL)).toBe(true);
    // A run that made no call at all is still a readable detail.
    expect(isAiRunDetail({ ...RUN_DETAIL, steps: [], calls: [] })).toBe(true);
  });

  it('rejects a detail without its step chain', () => {
    expect(isAiRunDetail(without(RUN_DETAIL, 'steps'))).toBe(false);
    expect(isAiRunDetail({ ...RUN_DETAIL, steps: 'nope' as unknown as AiStep[] })).toBe(false);
    expect(isAiRunDetail({ ...RUN_DETAIL, steps: [without(step(), 'name')] })).toBe(false);
  });

  it('rejects a call without the provider that served it', () => {
    expect(isAiRunDetail({ ...RUN_DETAIL, calls: [without(call(), 'provider')] })).toBe(false);
    expect(isAiRunDetail(without(RUN_DETAIL, 'calls'))).toBe(false);
  });

  it('inherits the run checks, so a broken run is not rescued by a valid chain', () => {
    expect(isAiRunDetail({ ...RUN_DETAIL, agent: undefined })).toBe(false);
    expect(isAiRunDetail({ ...RUN_DETAIL, totalTokens: '150' })).toBe(false);
  });
});

describe('isAiCosts', () => {
  it('accepts a summary the Cost page can render', () => {
    expect(isAiCosts(COSTS)).toBe(true);
    // No spend yet: an empty series and zero totals are a valid payload.
    expect(
      isAiCosts({
        ...COSTS,
        days: [],
        totals: { runs: 0, modelCalls: 0, tokens: 0, costUsd: 0, costCny: 0, latencyMs: 0 },
      }),
    ).toBe(true);
  });

  it('rejects a payload without its totals or its budget', () => {
    expect(isAiCosts(without(COSTS, 'totals'))).toBe(false);
    expect(isAiCosts(without(COSTS, 'dailyBudgetUsd'))).toBe(false);
    expect(isAiCosts({ ...COSTS, dailyBudgetUsd: '5' as unknown as number })).toBe(false);
  });

  it('rejects a cost that arrived as a string and a run count that did', () => {
    expect(
      isAiCosts({ ...COSTS, totals: { ...COSTS.totals, costUsd: '0.0012' as unknown as number } }),
    ).toBe(false);
    expect(
      isAiCosts({ ...COSTS, totals: { ...COSTS.totals, runs: '1' as unknown as number } }),
    ).toBe(false);
  });

  it('rejects a daily series that is not a series', () => {
    expect(isAiCosts({ ...COSTS, days: 'nope' })).toBe(false);
    expect(isAiCosts({ ...COSTS, days: [without(DAY, 'day')] })).toBe(false);
    expect(isAiCosts({ ...COSTS, days: [without(DAY, 'costUsd')] })).toBe(false);
    expect(isAiCosts({ ...COSTS, days: [{ ...DAY, costUsd: 'x' }] })).toBe(false);
  });

  it('accepts a negative total — nothing here claims to reject one', () => {
    expect(isAiCosts({ ...COSTS, totals: { ...COSTS.totals, costUsd: -1 } })).toBe(true);
  });
});

describe('isCostByAgentList', () => {
  it('accepts a per-agent breakdown', () => {
    expect(isCostByAgentList([AGENT_ROW])).toBe(true);
    expect(isCostByAgentList([])).toBe(true);
  });

  it('rejects a row without the agent it is grouped by', () => {
    expect(isCostByAgentList([without(AGENT_ROW, 'agent')])).toBe(false);
    expect(isCostByAgentList([without(AGENT_ROW, 'runs')])).toBe(false);
  });

  it('rejects a count that is not a number', () => {
    expect(isCostByAgentList([{ ...AGENT_ROW, runs: '2' }])).toBe(false);
    expect(isCostByAgentList([{ ...AGENT_ROW, tokens: Number.NaN }])).toBe(false);
  });

  it('rejects anything that is not a list of rows', () => {
    expect(isCostByAgentList(null)).toBe(false);
    expect(isCostByAgentList({ agent: 'job' })).toBe(false);
    expect(isCostByAgentList(['job'])).toBe(false);
  });

  it('accepts negative tokens — the guard checks that a number is present, not its sign', () => {
    expect(isCostByAgentList([{ ...AGENT_ROW, tokens: -300 }])).toBe(true);
  });
});

describe('isCostByFeatureList', () => {
  it('accepts a per-feature breakdown', () => {
    expect(isCostByFeatureList([FEATURE_ROW])).toBe(true);
  });

  it('rejects a row without the feature name', () => {
    expect(isCostByFeatureList([without(FEATURE_ROW, 'feature')])).toBe(false);
    expect(isCostByFeatureList([without(FEATURE_ROW, 'tokens')])).toBe(false);
  });

  it('rejects a workflows field that is not a list', () => {
    // The one thing this guard requires beyond the agent row: the workflows behind the feature.
    expect(isCostByFeatureList([without(FEATURE_ROW, 'workflows')])).toBe(false);
    expect(isCostByFeatureList([{ ...FEATURE_ROW, workflows: 'jd_analysis' }])).toBe(false);
    expect(isCostByFeatureList([{ ...FEATURE_ROW, workflows: null }])).toBe(false);
  });

  it('rejects a run count that is not a finite number', () => {
    expect(isCostByFeatureList([{ ...FEATURE_ROW, runs: '2' }])).toBe(false);
    expect(isCostByFeatureList([{ ...FEATURE_ROW, runs: Number.POSITIVE_INFINITY }])).toBe(false);
  });

  it("accepts a negative run count — the sign of a number is not this guard's business", () => {
    expect(isCostByFeatureList([{ ...FEATURE_ROW, runs: -2 }])).toBe(true);
  });
});

describe('isCacheStats', () => {
  it('accepts a hit rate and accepts null for one that cannot be computed', () => {
    expect(isCacheStats(CACHE_STATS)).toBe(true);
    // The documented empty case: nothing served yet, so there is no rate — and `0` would read as
    // "the cache never helps", which is why `null` is a legal value here.
    expect(
      isCacheStats({ ...CACHE_STATS, process: { ...CACHE_STATS.process, hitRate: null } }),
    ).toBe(true);
  });

  it('rejects a hit rate that is not a number or null', () => {
    expect(
      isCacheStats({ ...CACHE_STATS, process: { ...CACHE_STATS.process, hitRate: 'x' } }),
    ).toBe(false);
    expect(isCacheStats({ ...CACHE_STATS, process: without(CACHE_STATS.process, 'hitRate') })).toBe(
      false,
    );
    expect(
      isCacheStats({ ...CACHE_STATS, process: { ...CACHE_STATS.process, hitRate: Number.NaN } }),
    ).toBe(false);
  });

  it('rejects a process block that is absent or whose counters are not numbers', () => {
    expect(isCacheStats(without(CACHE_STATS, 'process'))).toBe(false);
    expect(
      isCacheStats({ ...CACHE_STATS, process: { ...CACHE_STATS.process, processHits: '2' } }),
    ).toBe(false);
    expect(
      isCacheStats({ ...CACHE_STATS, process: { ...CACHE_STATS.process, processMisses: null } }),
    ).toBe(false);
  });

  it('rejects a by-kind series that is not a series of kinds', () => {
    expect(isCacheStats({ ...CACHE_STATS, byKind: 'nope' })).toBe(false);
    expect(isCacheStats({ ...CACHE_STATS, byKind: [{ entries: 1, hits: 0, bytes: 0 }] })).toBe(
      false,
    );
    expect(isCacheStats({ ...CACHE_STATS, byKind: [null] })).toBe(false);
  });

  it('accepts a payload with no persistedHits — this guard never looks at it', () => {
    // Documented hole: the page prints `persistedHits`, and the guard does not require it.
    expect(isCacheStats(without(CACHE_STATS, 'persistedHits'))).toBe(true);
  });
});

describe('isPromptVersionList', () => {
  it('accepts the prompt registry rows', () => {
    expect(isPromptVersionList([PROMPT_ROW])).toBe(true);
    expect(isPromptVersionList([])).toBe(true);
  });

  it('rejects a row without a name or without a version', () => {
    expect(isPromptVersionList([without(PROMPT_ROW, 'name')])).toBe(false);
    expect(isPromptVersionList([without(PROMPT_ROW, 'version')])).toBe(false);
  });

  it('rejects a version that is a string and a flag that is not a boolean', () => {
    expect(isPromptVersionList([{ ...PROMPT_ROW, version: '1' }])).toBe(false);
    expect(isPromptVersionList([{ ...PROMPT_ROW, isActive: 'yes' }])).toBe(false);
    expect(isPromptVersionList([{ ...PROMPT_ROW, isActive: 1 }])).toBe(false);
  });

  it('rejects anything that is not a list of prompt rows', () => {
    expect(isPromptVersionList(null)).toBe(false);
    expect(isPromptVersionList({ name: 'jd_analysis' })).toBe(false);
    expect(isPromptVersionList([['jd_analysis']])).toBe(false);
  });

  it('accepts a negative version — an impossible number is still a number to this guard', () => {
    expect(isPromptVersionList([{ ...PROMPT_ROW, version: -1 }])).toBe(true);
  });
});
