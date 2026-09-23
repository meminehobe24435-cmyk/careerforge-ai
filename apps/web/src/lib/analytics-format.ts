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
 * zero cards, what a rate with no denominator shows, when "样本不足" appears — are the ones a
 * reader will check, and they are testable without a browser.
 */

export interface FunnelBar {
  key: string;
  /** Trapezoid width at the top of the band, as a fraction of the chart width. */
  topWidth: number;
  bottomWidth: number;
  /** Vertical offset as a fraction of the chart height, and the band's own height. */
  offset: number;
  height: number;
}

/**
 * Geometry for a classic funnel: each band tapers from the stage above's width to its own.
 *
 * Widths are **share of the first stage**, so the shape is the conversion story at a glance.
 * The first band is a rectangle (there is nothing above it) and a stage with no cards is a
 * zero-width band rather than a missing one — the gap is the information.
 */
export function funnelGeometry(stages: FunnelStage[], bandHeight = 1): FunnelBar[] {
  if (stages.length === 0) return [];
  const widthOf = (stage: FunnelStage) => Math.max(0, Math.min(1, stage.shareOfFirst));
  return stages.map((stage, index) => {
    const previous = index === 0 ? widthOf(stage) : widthOf(stages[index - 1] as FunnelStage);
    return {
      key: stage.key,
      topWidth: previous,
      bottomWidth: widthOf(stage),
      offset: index * bandHeight,
      height: bandHeight,
    };
  });
}

/** An SVG path for one funnel band, centred horizontally. */
export function funnelBandPath(bar: FunnelBar, width: number, height: number): string {
  const topHalf = (width * bar.topWidth) / 2;
  const bottomHalf = (width * bar.bottomWidth) / 2;
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

/** The correlation table's verdict word, so the same vocabulary is used everywhere. */
export function correlationVerdict(row: SkillCorrelation): 'notable' | 'flat' | 'insufficient' {
  if (!row.sufficient) return 'insufficient';
  return row.notable ? 'notable' : 'flat';
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
