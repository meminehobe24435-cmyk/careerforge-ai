import { describe, expect, it } from 'vitest';

import type { AiRun, CacheStats, DailyCost } from '@careerforge/shared';

import {
  activityWindowNote,
  budgetUsage,
  cacheHitReading,
  costShares,
  formatBytes,
  formatCount,
  formatCny,
  formatDuration,
  formatInstant,
  formatLatency,
  formatUsd,
  latestDay,
  parseApiInstant,
  shortDigest,
  spendSummary,
  statusBadge,
  unaccountedSummary,
  usageStatusCounts,
  usageStatusReading,
  USAGE_STATUS_GLOSSARY,
  zeroSpendSummary,
} from '@/lib/observability-format';

/**
 * The presentation rules the AI Runs and Cost pages depend on.
 *
 * These are not cosmetic tests. Each one pins a decision that would otherwise turn an honest
 * "not measurable" into a number a reader would believe: `null` latency rendering as `0 ms`, a
 * missing budget rendering as a full red bar, a naive-UTC timestamp silently read as local time.
 */

describe('null is not zero', () => {
  it('renders an unmeasurable latency as an em dash', () => {
    expect(formatLatency(null)).toBe('—');
    expect(formatLatency(undefined)).toBe('—');
    // …while a measured zero really is zero (a cache hit can be served in no measurable time).
    expect(formatLatency(0)).toBe('0 ms');
  });

  it('renders an unmeasurable rate as an em dash', () => {
    expect(formatCount(null)).toBe('—');
    expect(formatUsd(null)).toBe('—');
    expect(formatCny(undefined)).toBe('—');
  });

  it('keeps four decimals below a dollar, so a real charge never displays as free', () => {
    expect(formatUsd(0)).toBe('$0.0000');
    expect(formatUsd(0.0012)).toBe('$0.0012');
    expect(formatUsd(12.5)).toBe('$12.50');
  });

  it('groups digits without depending on the runner locale', () => {
    expect(formatCount(0)).toBe('0');
    expect(formatCount(1500)).toBe('1,500');
    expect(formatCount(1234567)).toBe('1,234,567');
  });

  it('scales latency to the magnitude', () => {
    expect(formatLatency(93)).toBe('93 ms');
    expect(formatLatency(1240)).toBe('1.24 s');
  });

  it('scales bytes to the magnitude', () => {
    expect(formatBytes(512)).toBe('512 B');
    expect(formatBytes(2048)).toBe('2.0 KiB');
  });

  it('truncates digests to a comparable prefix', () => {
    expect(shortDigest('abcdef0123456789')).toBe('abcdef012345…');
    expect(shortDigest('abc')).toBe('abc');
    expect(shortDigest('')).toBe('—');
  });
});

describe('timestamps are read on the clock they were written on', () => {
  it('treats a bare instant as the UTC it is', () => {
    // The API stores naive UTC (`utcnow()`); `new Date('2026-09-24T10:00:00')` in a UTC+8 browser
    // would parse this as 10:00 local and print 02:00 UTC — an eight-hour lie.
    expect(parseApiInstant('2026-09-24T10:00:00')?.toISOString()).toBe('2026-09-24T10:00:00.000Z');
  });

  it('leaves an instant that already carries a zone alone', () => {
    expect(parseApiInstant('2026-09-24T10:00:00Z')?.toISOString()).toBe('2026-09-24T10:00:00.000Z');
    expect(parseApiInstant('2026-09-24T18:00:00+08:00')?.toISOString()).toBe(
      '2026-09-24T10:00:00.000Z',
    );
  });

  it('formats an unparseable or missing instant as a dash instead of "Invalid Date"', () => {
    expect(formatInstant('not-a-date')).toBe('—');
    expect(formatInstant(null)).toBe('—');
    expect(formatInstant('2026-09-24T10:04:33')).toBe('2026-09-24 10:04');
  });

  it('measures the wall clock separately from the provider-reported latency', () => {
    expect(formatDuration('2026-09-24T10:00:00', '2026-09-24T10:00:00.093')).toBe('93 ms');
    // A run the reader waited on for two minutes reads as minutes, not as `120.00 s`.
    expect(formatDuration('2026-09-24T10:00:00', '2026-09-24T10:02:00')).toBe('2.0 min');
    expect(formatDuration('2026-09-24T10:00:00', '2026-09-24T10:00:12.5')).toBe('12.50 s');
    // Past an hour it stops pretending minutes are the useful unit.
    expect(formatDuration('2026-09-24T10:00:00', '2026-09-24T11:30:00')).toBe('1.5 h');
    // An unfinished run has no wall clock, which is not the same as a fast one.
    expect(formatDuration('2026-09-24T10:00:00', null)).toBe('—');
    // Nor is a clock that went backwards a negative duration.
    expect(formatDuration('2026-09-24T10:02:00', '2026-09-24T10:00:00')).toBe('—');
  });
});

describe('status vocabulary', () => {
  it('maps every status the executor can write', () => {
    expect(statusBadge('succeeded').label).toBe('成功');
    expect(statusBadge('degraded').label).toBe('降级');
    expect(statusBadge('failed').variant).toBe('danger');
    expect(statusBadge('running').label).toBe('运行中');
  });

  it('passes an unknown status through rather than mislabelling it', () => {
    expect(statusBadge('quarantined')).toEqual({ label: 'quarantined', variant: 'outline' });
    expect(statusBadge(null).label).toBe('未知');
  });
});

describe('the zero-key deployment is explained, not hidden', () => {
  const run = (
    provider: string | null,
    totalTokens: number | null,
  ): Pick<AiRun, 'provider' | 'totalTokens'> => ({
    provider,
    totalTokens,
  });

  it('names the heuristic provider when a whole page reports zero tokens', () => {
    const note = zeroSpendSummary([run('heuristic', 0), run('heuristic', 0)]);
    expect(note).toContain('零 Key 启发式');
    // The latency claim matters: the page must not imply nothing was measured.
    expect(note).toContain('延迟仍然被真实测量');
  });

  it('says nothing when the numbers speak for themselves', () => {
    expect(zeroSpendSummary([run('heuristic', 0), run('deepseek', 1500)])).toBeNull();
    expect(zeroSpendSummary([])).toBeNull();
    // One measured run among unreported ones is still enough for the column to be readable.
    expect(zeroSpendSummary([run('heuristic', null), run('deepseek', 1500)])).toBeNull();
  });

  it('does not blame the heuristic provider for a different one', () => {
    const note = zeroSpendSummary([run('deepseek', 0)]);
    expect(note).toContain('deepseek');
    expect(note).not.toContain('启发式');
  });

  it('admits when the provider was not recorded at all', () => {
    expect(zeroSpendSummary([run(null, 0)])).toContain('未记录');
  });

  /**
   * The PHASE 13 case, and the reason this function was rewritten: a page of `null`s is **not** a
   * page of zeros. Saying "these all reported 0 tokens" over `null` counters would re-tell the lie
   * the migration removed from the database.
   */
  it('distinguishes unreported usage from a measured zero', () => {
    const note = zeroSpendSummary([run('deepseek', null), run('deepseek', null)]);
    expect(note).toContain('provider 没有返回 usage metadata');
    expect(note).toContain('不是 0');
    expect(note).not.toContain('零 Key 启发式');
  });

  it('still explains a mixed page of measured zeros', () => {
    // Two providers reporting real zeros: not the zero-key story, and not the null one.
    const note = zeroSpendSummary([run('heuristic', 0), run('scripted', 0)]);
    expect(note).toContain('heuristic');
    expect(note).toContain('scripted');
    expect(note).toContain('均为 0');
  });
});

describe('the usage status vocabulary', () => {
  it('reads every status the API can send, including a row that predates the envelope', () => {
    expect(usageStatusReading('reported')?.label).toBe('Reported');
    expect(usageStatusReading('estimated')?.detail).toContain('not a billed amount');
    expect(usageStatusReading('cached')?.detail).toContain('nothing was billed');
    expect(usageStatusReading('unavailable')?.label).toBe('Unavailable');
    expect(usageStatusReading('unavailable')?.detail).toBe(
      'Provider did not return usage metadata.',
    );
    // The one that must never be silently re-labelled: those 0s cannot be trusted.
    expect(usageStatusReading('legacy')?.label).toBe('Legacy');
    expect(usageStatusReading('legacy')?.detail).toContain('cannot be trusted');
  });

  it('marks exactly the two states in which no measurement happened', () => {
    expect(usageStatusReading('reported')?.unmeasured).toBe(false);
    expect(usageStatusReading('estimated')?.unmeasured).toBe(false);
    expect(usageStatusReading('cached')?.unmeasured).toBe(false);
    expect(usageStatusReading('unavailable')?.unmeasured).toBe(true);
    expect(usageStatusReading('legacy')?.unmeasured).toBe(true);
  });

  it('shows an unknown status as itself instead of guessing a meaning for it', () => {
    const reading = usageStatusReading('throttled');
    expect(reading?.label).toBe('throttled');
    expect(reading?.unmeasured).toBe(true);
  });

  it('has nothing to say about a status that is absent', () => {
    expect(usageStatusReading(null)).toBeNull();
    expect(usageStatusReading(undefined)).toBeNull();
  });

  it('glossaries the five states in full, for the page that sums them', () => {
    expect(USAGE_STATUS_GLOSSARY.map((entry) => entry.label)).toEqual([
      'Reported',
      'Estimated',
      'Cached',
      'Unavailable',
      'Legacy',
    ]);
  });

  it('counts the statuses present, in glossary order', () => {
    const counts = usageStatusCounts([
      { usageStatus: 'unavailable' },
      { usageStatus: 'reported' },
      { usageStatus: 'reported' },
      { usageStatus: null },
    ]);
    expect(counts.map((entry) => [entry.reading.label, entry.count])).toEqual([
      ['Reported', 2],
      ['Unavailable', 1],
    ]);
    expect(usageStatusCounts([])).toEqual([]);
  });
});

describe('totals that skip what was never measured', () => {
  it('sums only the reported costs and counts the rest separately', () => {
    const spend = spendSummary([{ costUsd: 0.0012 }, { costUsd: null }, { costUsd: 0.0008 }]);
    expect(spend.usd).toBeCloseTo(0.002, 6);
    expect(spend.reported).toBe(2);
    expect(spend.unavailable).toBe(1);
  });

  it('keeps a measured zero as zero rather than treating it as missing', () => {
    const spend = spendSummary([{ costUsd: 0 }, { costUsd: 0 }]);
    expect(spend.usd).toBe(0);
    expect(spend.reported).toBe(2);
    expect(spend.unavailable).toBe(0);
  });

  it('does not add a non-finite cost to the sum', () => {
    const spend = spendSummary([{ costUsd: Number.NaN }, { costUsd: 1 }]);
    expect(spend.usd).toBe(1);
    expect(spend.unavailable).toBe(1);
  });

  it('stays silent while the total is complete, and states the floor when it is not', () => {
    expect(unaccountedSummary(0)).toBeNull();
    expect(unaccountedSummary(-1)).toBeNull();
    const note = unaccountedSummary(3);
    expect(note).toContain('3 次运行');
    expect(note).toContain('下限');
  });
});

describe('the budget guard does not invent a ceiling', () => {
  const day: DailyCost = { day: '2026-09-24', runs: 3, tokens: 0, costUsd: 0.42, costCny: 3.0 };

  it('reports a ratio against a configured ceiling', () => {
    const usage = budgetUsage(day, 1);
    expect(usage.ratio).toBeCloseTo(0.42, 5);
    expect(usage.exceeded).toBe(false);
    expect(usage.label).toBe('$0.4200 / $1.00');
  });

  it('flags an exceeded ceiling', () => {
    const usage = budgetUsage(day, 0.25);
    expect(usage.exceeded).toBe(true);
    // The bar is clamped at 100%: a bar that overflows its own track reads as a rendering bug.
    expect(usage.ratio).toBe(1);
  });

  it('treats a zero budget as "no ceiling configured", not "nothing allowed"', () => {
    const usage = budgetUsage(day, 0);
    expect(usage.ratio).toBeNull();
    expect(usage.exceeded).toBe(false);
    expect(usage.label).toContain('未配置');
  });

  it('handles a window with no recorded day', () => {
    const usage = budgetUsage(null, 5);
    expect(usage.spentUsd).toBe(0);
    expect(usage.ratio).toBe(0);
  });

  it('compares against the newest day the API reported', () => {
    const first: DailyCost = { day: '2026-09-22', runs: 1, tokens: 0, costUsd: 0.1, costCny: 0.7 };
    expect(latestDay([first, day])).toBe(day);
    expect(latestDay([])).toBeNull();
  });

  it('states how much of the window had activity, because the API does not zero-fill', () => {
    expect(activityWindowNote([day], '7d')).toContain('窗口 7 天中 1 天有运行');
    expect(activityWindowNote([day], 'all')).toBeNull();
  });
});

describe('shares of an empty total', () => {
  it('divides by the rows handed in', () => {
    const { rows, total } = costShares([
      { key: 'a', label: 'A', value: 3 },
      { key: 'b', label: 'B', value: 1 },
    ]);
    expect(total).toBe(4);
    expect(rows[0]?.share).toBe(0.75);
    expect(rows[1]?.share).toBe(0.25);
  });

  it('yields zero rather than NaN when nothing was spent', () => {
    const { rows, total } = costShares([{ key: 'a', label: 'A', value: 0 }]);
    expect(total).toBe(0);
    expect(rows[0]?.share).toBe(0);
  });
});

describe('the cache gauge', () => {
  const stats = (hitRate: number | null): CacheStats => ({
    byKind: [{ kind: 'llm', entries: 3, hits: 3, bytes: 4096 }],
    persistedHits: 3,
    process: {
      processHits: 3,
      processMisses: 2,
      processEntries: 3,
      eventsFlushed: 5,
      hitRate,
    },
  });

  it('reports a measurable rate with its own denominator', () => {
    const reading = cacheHitReading(stats(0.6));
    expect(reading.rate).toBe(0.6);
    expect(reading.requests).toBe(5);
    expect(reading.label).toBe('3 命中 / 5 次查询');
  });

  it('says a cache that served nothing has no hit rate', () => {
    const reading = cacheHitReading(stats(null));
    expect(reading.rate).toBeNull();
    expect(reading.label).toContain('命中率不可计算');
  });

  it('distinguishes "no data yet" from "stats unavailable"', () => {
    expect(cacheHitReading(undefined).label).toBe('缓存统计不可用');
  });
});
