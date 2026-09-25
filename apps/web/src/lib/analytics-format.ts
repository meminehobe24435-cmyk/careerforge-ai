import type {
  AnalyticsRange,
  CategoryPerformance,
  FunnelStage,
  RateCard,
  SkillCorrelation,
  TimelineBucket,
} from '@careerforge/shared';

/**
 * Presentation arithmetic for the analytics page.
 *
 * Pure on purpose: the interesting decisions here — how wide a funnel bar is when a stage has
 * zero cards, what a rate with no denominator shows, when "样本不足" appears, and whether a number
 * may be read as a *finding* or only as data — are the ones a reader will check, and they are
 * testable without a browser.
 */

/**
 * The narrowest a non-empty funnel band is ever **drawn**.
 *
 * A stage with one card out of two hundred has a true share of 0.005, which on a 1000-unit-wide
 * chart is five units — visible on a good monitor and invisible on most. The band is therefore
 * drawn at 4% and labelled with its real count and share, so the shape stays legible while the
 * numbers stay exact. The *data* widths in {@link FunnelBar} are never rounded; only the drawing is.
 */
export const MIN_BAND_WIDTH = 0.04;

export interface FunnelBar {
  key: string;
  /** Trapezoid width at the top of the band, as a fraction of the chart width. */
  topWidth: number;
  bottomWidth: number;
  /** The same edges as drawn, floored at {@link MIN_BAND_WIDTH} for a non-empty stage. */
  drawTopWidth: number;
  drawBottomWidth: number;
  /** Vertical offset as a fraction of the chart height, and the band's own height. */
  offset: number;
  height: number;
  /** `true` when this stage counted nothing: the band is a labelled gap, not an empty shape. */
  empty: boolean;
}

/**
 * Geometry for a classic funnel: each band tapers from the stage above's width to its own.
 *
 * Widths are **share of the first stage**, so the shape is the conversion story at a glance.
 * The first band is a rectangle (there is nothing above it) and a stage with no cards is a
 * zero-width band rather than a missing one — the gap is the information.
 *
 * A funnel whose later stages are all zero is the case this has to survive: five bands of which
 * four are 0 draws one full-width rectangle over four-ninths of an empty chart, which reads as a
 * rendering fault. So every band also carries the widths it is *drawn* at, floored at
 * {@link MIN_BAND_WIDTH} when its count is non-zero, and an `empty` flag the chart uses to render a
 * labelled gap in its place.
 */
export function funnelGeometry(stages: FunnelStage[], bandHeight = 1): FunnelBar[] {
  if (stages.length === 0) return [];
  const widthOf = (stage: FunnelStage) => Math.max(0, Math.min(1, stage.shareOfFirst));
  const drawn = (stage: FunnelStage) =>
    stage.count === 0 ? 0 : Math.max(widthOf(stage), MIN_BAND_WIDTH);
  return stages.map((stage, index) => {
    const previous = index === 0 ? widthOf(stage) : widthOf(stages[index - 1] as FunnelStage);
    const own = drawn(stage);
    // The first band has nothing above it, so it does not taper; a later one never widens.
    const previousDrawn = index === 0 ? own : drawn(stages[index - 1] as FunnelStage);
    return {
      key: stage.key,
      topWidth: previous,
      bottomWidth: widthOf(stage),
      drawTopWidth: index === 0 ? own : Math.max(previousDrawn, own),
      drawBottomWidth: own,
      offset: index * bandHeight,
      height: bandHeight,
      empty: stage.count === 0,
    };
  });
}

/** An SVG path for one funnel band, centred horizontally. */
export function funnelBandPath(bar: FunnelBar, width: number, height: number): string {
  const topHalf = (width * bar.drawTopWidth) / 2;
  const bottomHalf = (width * bar.drawBottomWidth) / 2;
  const centre = width / 2;
  const top = height * bar.offset;
  const bottom = top + height * bar.height;
  return [
    `M ${centre - topHalf} ${top}`,
    `L ${centre + topHalf} ${top}`,
    `L ${centre + bottomHalf} ${bottom}`,
    `L ${centre - bottomHalf} ${bottom}`,
    'Z',
  ].join(' ');
}

/** `0.4` → `40.0%`; `null` → an em dash, never 0%. */
export function formatRate(rate: number | null | undefined, digits = 1): string {
  if (rate === null || rate === undefined) return '—';
  return `${(rate * 100).toFixed(digits)}%`;
}

/** `null` step rates are shown as a dash: an empty stage above is not a 0% conversion. */
export function formatStepRate(rate: number | null | undefined): string {
  return rate === null || rate === undefined ? '—' : formatRate(rate, 0);
}

export function formatInterval(card: RateCard): string {
  if (card.denominator === 0) return '无样本';
  return `95% CI ${formatRate(card.intervalLow, 0)}–${formatRate(card.intervalHigh, 0)}`;
}

/**
 * The sample-size caveat, or `null` when the number stands on its own.
 *
 * FR-14.3 asks for "样本不足，仅供参考" explicitly, and the same rule is applied to the rate
 * cards: a claim the numbers cannot support should say so where the number is, not in a
 * tooltip.
 */
export function insufficientNote(entry: {
  sufficient: boolean;
  denominator?: number;
}): string | null {
  if (entry.sufficient) return null;
  const denominator = entry.denominator;
  return denominator === undefined
    ? '样本不足，仅供参考'
    : `样本不足（n=${denominator}），仅供参考`;
}

/** The cohort policy the analytics endpoints apply (`AnalyticsMeta`). */
export interface SamplePolicy {
  cohortSize: number;
  minimumSample: number;
}

/** Whether the cohort clears the API's own minimum — the API's rule, not a new threshold. */
export function sampleIsSufficient(meta: SamplePolicy): boolean {
  return meta.cohortSize >= meta.minimumSample;
}

/**
 * The **neutral** treatment of a cohort below the API's minimum, or `null` when it clears it.
 *
 * This is the sentence the funnel and the correlation table put next to their numbers instead of a
 * verdict. The distinction it draws is the whole point of this function: a sample that is too
 * small is **not** a decline, **not** a failure and **not** a bad sign — it is an absence of
 * evidence, and the page must not colour it red or point an arrow at it. Nothing here is phrased as
 * a finding, and no threshold is invented: `minimumSample` comes from the payload.
 */
export function insufficientSampleNote(meta: SamplePolicy): string | null {
  if (sampleIsSufficient(meta)) return null;
  return `Insufficient sample（样本不足）：这个窗口的同期群是 ${meta.cohortSize} 条，低于接口自己声明的最少 ${meta.minimumSample} 条。下面的数字照实列出，但它们不构成结论 —— 这不是「变差了」，而是证据还不够。`;
}

/** The correlation table's verdict word, so the same vocabulary is used everywhere. */
export function correlationVerdict(row: SkillCorrelation): 'notable' | 'flat' | 'insufficient' {
  if (!row.sufficient) return 'insufficient';
  return row.notable ? 'notable' : 'flat';
}

export type CorrelationTone = 'signal' | 'outline';

/** One correlation row, ready to render — including whether it may be read as a finding. */
export interface CorrelationReading {
  verdict: 'notable' | 'flat' | 'insufficient';
  /** The word in the 结论 column. */
  label: string;
  /**
   * `signal` only for a difference that cleared the sample minimum. `outline` is the neutral
   * treatment, and it is deliberately the tone for **both** "no difference" and "not enough data":
   * neither is bad news, and the danger tone belongs to nothing on this page.
   */
  tone: CorrelationTone;
  /** The 差值 cell. `measured: false` means it must not be styled or read as a trend. */
  lift: { text: string; measured: boolean };
  /** `true` when this row may be treated as a finding about the candidate's skills. */
  actionable: boolean;
  /** Shown under the table when the row must not be read as a conclusion. */
  note: string | null;
}

/**
 * Read one correlation row.
 *
 * The table used to print `-100pt` in a red `样本不足` badge on every row whose groups were too
 * small, while the footnote under it said the sample was insufficient — the visual said "your
 * skills are hurting you" and the text said "we do not know". The redesign is this function: an
 * insufficient row keeps the API's own difference (it is real arithmetic, not a fabrication) but is
 * marked `measured: false`, so the page prints it in muted text with no sign emphasis, labels the
 * verdict `Insufficient sample`, and states in words that it is not a conclusion.
 */
export function correlationReading(row: SkillCorrelation): CorrelationReading {
  const verdict = correlationVerdict(row);
  if (verdict === 'insufficient') {
    return {
      verdict,
      label: 'Insufficient sample',
      tone: 'outline',
      lift: { text: formatLift(row.lift), measured: false },
      actionable: false,
      note: `Insufficient sample：${row.withSkillTotal} 个要求它的岗位 vs ${row.withoutSkillTotal} 个未要求的岗位。差值是这两组的算术结果，不是趋势 —— 样本量不够时不看方向。`,
    };
  }
  if (verdict === 'notable') {
    return {
      verdict,
      label: '值得注意',
      tone: 'signal',
      lift: { text: formatLift(row.lift), measured: true },
      actionable: true,
      note: null,
    };
  }
  return {
    verdict,
    label: '无显著差异',
    tone: 'outline',
    lift: { text: formatLift(row.lift), measured: true },
    actionable: true,
    note: null,
  };
}

export function formatLift(lift: number): string {
  const percent = (lift * 100).toFixed(0);
  return lift > 0 ? `+${percent}pt` : `${percent}pt`;
}

/** Category labels: the taxonomy's own names, with a human translation for the common ones. */
const CATEGORY_LABELS: Record<string, string> = {
  embedded: '嵌入式',
  backend: '服务端',
  frontend: '前端',
  ai: 'AI / 算法',
  devops: '运维 / DevOps',
  database: '数据库',
  language: '编程语言',
  framework: '框架',
  tool: '工具',
  domain: '领域',
  soft: '软技能',
  unknown: '未分类',
};

export function categoryLabel(category: string): string {
  return CATEGORY_LABELS[category] ?? category;
}

export function formatCategoryScore(score: number | null): string {
  return score === null ? '—' : score.toFixed(0);
}

/** The month with the largest activity, so the trend chart can scale to its own data. */
export function peakBucketValue(buckets: TimelineBucket[]): number {
  return buckets.reduce(
    (peak, bucket) => Math.max(peak, bucket.applications, bucket.interviews, bucket.offers),
    0,
  );
}

/** `2026-03` → `26/03`, short enough for an axis. */
export function shortMonth(month: string): string {
  const [year, index] = month.split('-');
  if (!year || !index) return month;
  return `${year.slice(2)}/${index}`;
}

export const RANGE_LABELS: Record<AnalyticsRange, string> = {
  '7d': '7 天',
  '30d': '30 天',
  '90d': '90 天',
  all: '全部',
};

export type AnalyticsCard = RateCard | CategoryPerformance;
