import { describe, expect, it } from 'vitest';

import type { FunnelStage, RateCard, SkillCorrelation, TimelineBucket } from '@careerforge/shared';

import {
  MIN_BAND_WIDTH,
  correlationReading,
  correlationVerdict,
  formatInterval,
  formatLift,
  formatRate,
  formatStepRate,
  funnelBandPath,
  funnelGeometry,
  insufficientNote,
  insufficientSampleNote,
  peakBucketValue,
  sampleIsSufficient,
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
    // A hand-built bar, so the assertion is about the path and not about the geometry that fed it.
    const path = funnelBandPath(
      {
        key: 'a',
        topWidth: 1,
        bottomWidth: 0.5,
        drawTopWidth: 1,
        drawBottomWidth: 0.5,
        offset: 0,
        height: 1,
        empty: false,
      },
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

  it('draws the widths it was given for drawing, not the data widths', () => {
    const geometry = funnelGeometry([stage('applications', 200, 1), stage('offers', 1, 0.005)]);
    const drawn = geometry[1] as (typeof geometry)[number];
    const path = funnelBandPath(drawn, 1000, 100);
    // 4% of 1000 = 40 → the bottom edge is inset by 20 on each side.
    expect(path).toContain('L 520');
    expect(path).toContain('L 480');
  });

  /**
   * The drawn widths, which are what fixed the "giant empty trapezoid".
   *
   * A stage with one card out of two hundred is a real stage and an invisible band; a stage with
   * none is a gap. The two are drawn differently and the data widths are never rounded, so the
   * shape stays readable without the numbers becoming wrong.
   */
  it('draws a tiny non-empty stage at a visible minimum width', () => {
    const bars = funnelGeometry([stage('applications', 200, 1), stage('offers', 1, 0.005)]);
    // The data is exact…
    expect(bars[1]?.bottomWidth).toBe(0.005);
    // …and the drawing is floored.
    expect(bars[1]?.drawBottomWidth).toBe(MIN_BAND_WIDTH);
    expect(bars[1]?.empty).toBe(false);
  });

  it('keeps a band from tapering outward, which would read as growth', () => {
    // A degenerate input: a later stage claiming more than the one above it.
    const bars = funnelGeometry([stage('applications', 1, 0.1), stage('offers', 1, 1)]);
    expect(bars[1]?.drawTopWidth).toBeGreaterThanOrEqual(bars[1]?.drawBottomWidth ?? 0);
    expect(bars[1]?.drawTopWidth).toBe(bars[1]?.drawBottomWidth);
  });

  it('marks a zero stage as a gap and draws it at zero width', () => {
    const bars = funnelGeometry([stage('applications', 6, 1), stage('offers', 0, 0)]);
    expect(bars[1]?.empty).toBe(true);
    expect(bars[1]?.drawBottomWidth).toBe(0);
    // The band still exists: the gap is information, and the chart labels it.
    expect(bars).toHaveLength(2);
    expect(bars[1]?.height).toBeGreaterThan(0);
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

/**
 * The sample policy, and the difference between data and a finding.
 *
 * These functions are what stopped the page from printing a red `-100pt` verdict on rows whose own
 * footnote said the sample was too small. The rules they pin: never invent a threshold, never
 * colour an absence of evidence as bad news, and never let a too-small difference be read as a
 * decline.
 */
describe('an insufficient sample is not a decline', () => {
  const policy = { cohortSize: 4, minimumSample: 5 };

  it('uses the API’s own minimum rather than a new threshold', () => {
    expect(sampleIsSufficient({ cohortSize: 5, minimumSample: 5 })).toBe(true);
    expect(sampleIsSufficient({ cohortSize: 4, minimumSample: 5 })).toBe(false);
    // A deployment that asks for no minimum is not an insufficient one.
    expect(sampleIsSufficient({ cohortSize: 0, minimumSample: 0 })).toBe(true);
  });

  it('says "insufficient sample" in words, and says it is not a decline', () => {
    const note = insufficientSampleNote(policy);
    expect(note).toContain('Insufficient sample');
    expect(note).toContain('同期群是 4 条');
    expect(note).toContain('最少 5 条');
    // The framing that matters: the page must not tell a candidate they are getting worse.
    expect(note).toContain('不是「变差了」');
    expect(note).toContain('证据还不够');
  });

  it('says nothing at all when the cohort clears the minimum', () => {
    expect(insufficientSampleNote({ cohortSize: 5, minimumSample: 5 })).toBeNull();
    expect(insufficientSampleNote({ cohortSize: 40, minimumSample: 5 })).toBeNull();
  });

  function correlation(overrides: Partial<SkillCorrelation> = {}): SkillCorrelation {
    return {
      skillId: 'can',
      displayName: 'CAN',
      withSkillTotal: 2,
      withSkillSuccesses: 1,
      withSkillRate: 0.5,
      withoutSkillTotal: 8,
      withoutSkillSuccesses: 1,
      withoutSkillRate: 0.125,
      lift: 0.375,
      sufficient: true,
      notable: true,
      note: '',
      ...overrides,
    };
  }

  it('reads a too-small row as data, not as a finding', () => {
    const reading = correlationReading(
      correlation({ sufficient: false, notable: false, lift: -1, withSkillTotal: 1 }),
    );
    expect(reading.verdict).toBe('insufficient');
    expect(reading.label).toBe('Insufficient sample');
    expect(reading.actionable).toBe(false);
    // The number is the API's and stays on the page — but it is not a measurement of anything.
    expect(reading.lift.text).toBe('-100pt');
    expect(reading.lift.measured).toBe(false);
    expect(reading.note).toContain('不是趋势');
  });

  it('never tones an insufficient row as bad news', () => {
    // `danger` is not reachable from this function at all: neither a flat row nor an unmeasured
    // one is a decline, and only a measured, notable difference gets the signal tone.
    for (const overrides of [
      { sufficient: false },
      { sufficient: true, notable: false },
      { sufficient: true, notable: true },
    ]) {
      expect(['signal', 'outline']).toContain(correlationReading(correlation(overrides)).tone);
    }
    expect(correlationReading(correlation({ sufficient: false })).tone).toBe('outline');
  });

  it('keeps the signal tone for a difference that cleared the minimum', () => {
    const reading = correlationReading(correlation());
    expect(reading.verdict).toBe('notable');
    expect(reading.tone).toBe('signal');
    expect(reading.actionable).toBe(true);
    expect(reading.lift.measured).toBe(true);
    // A measured difference can be negative and still be a finding — that is what "measured" means.
    const decline = correlationReading(correlation({ lift: -0.4 }));
    expect(decline.lift.text).toBe('-40pt');
    expect(decline.lift.measured).toBe(true);
  });

  it('reports a flat measured row without a conclusion either way', () => {
    const reading = correlationReading(correlation({ notable: false, lift: -0.0833 }));
    expect(reading.label).toBe('无显著差异');
    expect(reading.tone).toBe('outline');
    expect(reading.actionable).toBe(true);
    expect(reading.note).toBeNull();
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
