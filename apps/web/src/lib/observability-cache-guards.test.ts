import { describe, expect, it } from 'vitest';

import {
  isCacheStats,
  isCostByAgentList,
  isCostByFeatureList,
  isPromptVersionList,
} from '@careerforge/shared';

import {
  AGENT_ROW,
  CACHE_STATS,
  FEATURE_ROW,
  PROMPT_ROW,
  without,
} from '@/lib/observability-guard-fixtures';

/**
 * The cache, prompt and per-entity breakdown guards of API.md §2.12.
 *
 * Split out of `observability-guards.test.ts` (which keeps the run, detail and cost-summary guards)
 * because it crossed the 500-line file guard — and because these four have a different failure
 * mode. The run guards protect the numbers a reader believes; these protect the *panels*: a
 * breakdown whose grouping key went missing renders an unnamed row, and a hit rate that arrived as
 * a string would be printed as `NaN%` on a page whose whole job is arithmetic.
 *
 * The fixtures are shared with the other file on purpose — a valid `CacheStats` must mean the same
 * thing in both.
 */

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

  /**
   * The aggregates are sums, so `tokens: 0` on a row is a real zero that the page prints as `0`.
   * A *null* row total, by contrast, is not something this endpoint can produce: `SUM` over a
   * grouped set coalesces to 0, and the page's `—` rule applies to the per-run counts instead.
   */
  it('keeps accepting a measured zero aggregate', () => {
    expect(isCostByAgentList([{ ...AGENT_ROW, tokens: 0, costUsd: 0, costCny: 0 }])).toBe(true);
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
    // Documented hole: the page prints `persistedHits`, and the guard does not require it. The page
    // therefore prints an em dash for an absent one rather than a `0` nobody measured.
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
