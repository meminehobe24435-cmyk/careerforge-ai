import { describe, expect, it } from 'vitest';

import type { FunnelStage, RateCard, TimelineBucket } from '@careerforge/shared';

import {
  correlationVerdict,
  formatInterval,
  formatLift,
  formatRate,
  formatStepRate,
  funnelBandPath,
  funnelGeometry,
  insufficientNote,
  peakBucketValue,
  shortMonth,
} from '@/lib/analytics-format';

/**
 * The analytics page's arithmetic.
 *
 * These are the functions that decide what a reader concludes: whether an empty stage looks
 * empty, whether a missing rate shows an em dash or a zero, and whether "样本不足" appears. Each
 * is pure, so each is pinned here rather than discovered by scrolling a chart.
 */

function stage(key: string, count: number, share: number, step: number | null = null): FunnelStage {
  return { key, label: key, count, shareOfFirst: share, stepRate: step, basis: 'test' };
}

describe('the funnel shape', () => {
  it('tapers from the stage above to its own share', () => {
    const bars = funnelGeometry([
      stage('applications', 10, 1),
      stage('replies', 5, 0.5),
      stage('interviews', 2, 0.2),
    ]);
    expect(bars[0]?.topWidth).toBe(1);
    expect(bars[0]?.bottomWidth).toBe(1);
    expect(bars[1]?.topWidth).toBe(1);
    expect(bars[1]?.bottomWidth).toBe(0.5);
    expect(bars[2]?.topWidth).toBe(0.5);
    expect(bars[2]?.bottomWidth).toBe(0.2);
  });

  it('gives an empty stage zero width rather than hiding it', () => {
    const bars = funnelGeometry([stage('applications', 3, 1), stage('offers', 0, 0)]);
    expect(bars[1]?.bottomWidth).toBe(0);
    // The band still exists, so the shape shows where the pipeline stopped.
    expect(bars).toHaveLength(2);
    expect(bars[1]?.height).toBeGreaterThan(0);
  });

  it('stacks bands without gaps or overlap', () => {
    const bars = funnelGeometry([stage('a', 1, 1), stage('b', 1, 1)], 0.25);
    expect(bars[0]?.offset).toBe(0);
    expect(bars[1]?.offset).toBe(0.25);
    expect(bars[1]?.height).toBe(0.25);
  });

  it('has nothing to draw for an empty cohort', () => {
    expect(funnelGeometry([])).toEqual([]);
  });

  it('centres each band and closes the path', () => {
    const path = funnelBandPath(
      { key: 'a', topWidth: 1, bottomWidth: 0.5, offset: 0, height: 1 },
      400,
      100,
    );
    expect(path.startsWith('M 0')).toBe(true);
    expect(path).toContain('L 400');
    expect(path.endsWith('Z')).toBe(true);
    // A half-width bottom edge is inset by a quarter of the width on each side.
    expect(path).toContain('L 300');
    expect(path).toContain('L 100');
  });
});

describe('formatting a rate', () => {
  it('shows an em dash when there is nothing to divide by', () => {
    expect(formatRate(null)).toBe('—');
    expect(formatRate(undefined)).toBe('—');
    expect(formatStepRate(null)).toBe('—');
  });

  it('shows a real zero as a zero', () => {
    expect(formatRate(0)).toBe('0.0%');
    expect(formatStepRate(0)).toBe('0%');
  });

  it('rounds to the requested precision', () => {
    expect(formatRate(0.1234, 0)).toBe('12%');
    expect(formatRate(0.1234, 1)).toBe('12.3%');
  });

  it('describes the interval rather than only the point estimate', () => {
    const card = {
      key: 'interviewRate',
      label: 'Interview Rate',
      rate: 0.5,
      numerator: 1,
      denominator: 2,
      sufficient: false,
      intervalLow: 0.094,
      intervalHigh: 0.906,
      definition: 'test',
    } satisfies RateCard;
    expect(formatInterval(card)).toBe('95% CI 9%–91%');
    expect(formatInterval({ ...card, denominator: 0 })).toBe('无样本');
  });

  it('says 样本不足 with the sample size, because "how insufficient" is the useful part', () => {
    expect(insufficientNote({ sufficient: false, denominator: 3 })).toBe(
      '样本不足（n=3），仅供参考',
    );
    expect(insufficientNote({ sufficient: false })).toBe('样本不足，仅供参考');
    expect(insufficientNote({ sufficient: true, denominator: 30 })).toBeNull();
  });
});

describe('the correlation verdict', () => {
  const row = { sufficient: true, notable: true } as Parameters<typeof correlationVerdict>[0];

  it('separates "not enough data" from "no difference"', () => {
    expect(correlationVerdict({ ...row, sufficient: false, notable: false })).toBe('insufficient');
    expect(correlationVerdict({ ...row, notable: false })).toBe('flat');
    expect(correlationVerdict(row)).toBe('notable');
  });

  it('formats a lift in percentage points, keeping the sign', () => {
    expect(formatLift(0.25)).toBe('+25pt');
    expect(formatLift(-0.25)).toBe('-25pt');
    expect(formatLift(0)).toBe('0pt');
  });
});

describe('the trend axis', () => {
  const bucket = (month: string, applications: number, interviews = 0): TimelineBucket => ({
    month,
    applications,
    interviews,
    offers: 0,
  });

  it('scales to the busiest month across all three series', () => {
    expect(peakBucketValue([bucket('2026-01', 3, 4), bucket('2026-02', 1)])).toBe(4);
    expect(peakBucketValue([])).toBe(0);
  });

  it('shortens a month for the axis without changing its meaning', () => {
    expect(shortMonth('2026-03')).toBe('26/03');
    expect(shortMonth('nonsense')).toBe('nonsense');
  });
});
