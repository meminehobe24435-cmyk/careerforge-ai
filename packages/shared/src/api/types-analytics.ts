/**
 * 8. Analytics — part of the frozen client contract.
 *
 * Split out of `types.ts` when that file crossed the 500-line guard; the split is by
 * domain, and `types.ts` re-exports every one of these so importers do not care.
 */

/* ------------------------------------------------------------------ *
 * 8. Analytics (API.md §2.11, PRD FR-14)
 * ------------------------------------------------------------------ */

export type AnalyticsRange = '7d' | '30d' | '90d' | 'all';

export const ANALYTICS_RANGES: readonly AnalyticsRange[] = ['7d', '30d', '90d', 'all'];

/**
 * The window, the sample policy, and whether the range filtered applications or events.
 *
 * `windowBasis` is the field a reader needs most: the funnel answers "of the applications I
 * started in this period, how far did they get", while the timeline answers "what happened in
 * this period". Same word, two different filters — so the API says which one it used.
 */
export interface AnalyticsMeta {
  range: AnalyticsRange | string;
  fromAt: string | null;
  toAt: string | null;
  cohortSize: number;
  minimumSample: number;
  windowBasis: 'applications' | 'events' | string;
  notes: string[];
}

export interface FunnelStage {
  key: string;
  label: string;
  count: number;
  shareOfFirst: number;
  /** `null` when the stage above is empty: nobody converted, so there is no rate to report. */
  stepRate: number | null;
  basis: string;
}

export interface FunnelResponse {
  meta: AnalyticsMeta;
  stages: FunnelStage[];
}

export interface RateCard {
  key: string;
  label: string;
  /** `null` when there is nothing to divide by — not a rate of zero. */
  rate: number | null;
  numerator: number;
  denominator: number;
  sufficient: boolean;
  intervalLow: number;
  intervalHigh: number;
  definition: string;
}

export interface RatesResponse {
  meta: AnalyticsMeta;
  cards: RateCard[];
}

export interface SkillCorrelation {
  skillId: string;
  displayName: string;
  withSkillTotal: number;
  withSkillSuccesses: number;
  withSkillRate: number;
  withoutSkillTotal: number;
  withoutSkillSuccesses: number;
  withoutSkillRate: number;
  lift: number;
  sufficient: boolean;
  notable: boolean;
  note: string;
}

export interface CategoryPerformance {
  category: string;
  applications: number;
  interviews: number;
  offers: number;
  interviewRate: number;
  averageMatchScore: number | null;
  sufficient: boolean;
}

export interface TimelineEntry {
  kind: string;
  title: string;
  occurredAt: string;
  status: string | null;
  refId: string | null;
}

export interface TimelineBucket {
  month: string;
  applications: number;
  interviews: number;
  offers: number;
}

export interface TimelineResponse {
  meta: AnalyticsMeta;
  entries: TimelineEntry[];
  buckets: TimelineBucket[];
}
