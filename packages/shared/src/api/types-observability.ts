/**
 * 9. AI observability (API.md §2.12) — part of the frozen client contract.
 *
 * Split out of `types.ts` by domain, the same way analytics and applications are, and re-exported
 * from `types.ts` so importers do not care where a type lives.
 *
 * The shape mirrors `apps/api/src/careerforge_api/schemas/observability.py` field for field. Two
 * conventions are worth stating because the UI depends on them:
 *
 * * `tokens`/`cost` are **measured, zero, or absent** — never estimated. A deployment on the
 *   zero-key heuristic provider really does spend 0 tokens, and the pages say so from `provider`
 *   and `notes` rather than dressing the number up;
 * * `null` means "not measurable" and is not interchangeable with `0`. PHASE 13 made that true
 *   end to end: the usage columns are nullable (migration `0009`), and a `NULL` count means the
 *   provider never reported one. The UI prints `—`/“unavailable” for `null` and `0` for a real
 *   zero, which is why every count below is `number | null` and `usageStatus` travels beside it.
 */

import { ANALYTICS_RANGES, type AnalyticsRange } from './types-analytics.ts';

/* ------------------------------------------------------------------ *
 * 9. AI observability (API.md §2.12, PRD FR-15)
 * ------------------------------------------------------------------ */

/**
 * The cost window. Same four keywords as analytics, deliberately: `GET /ai-costs?range=` takes
 * `7d|30d|90d|all`, and two unions that mean the same thing would drift.
 */
export type ObservabilityRange = AnalyticsRange;

export const OBSERVABILITY_RANGES: readonly ObservabilityRange[] = ANALYTICS_RANGES;

/** The five states `agent_runs.status` can hold; the API filters on `status` with this enum. */
export type AiRunStatus = 'running' | 'succeeded' | 'failed' | 'degraded' | 'cancelled';

export const AI_RUN_STATUSES: readonly AiRunStatus[] = [
  'succeeded',
  'degraded',
  'failed',
  'running',
  'cancelled',
];

/**
 * Where the numbers beside a run or a call came from (PHASE 13, migration `0009`).
 *
 * `unavailable` always means every count on that row is `null`; `legacy` means the row was written
 * before the envelope existed, so its `0`s are zeros of unknown provenance rather than
 * measurements. A client that prints either as `0` is claiming a measurement nobody made.
 */
export type UsageStatus = 'reported' | 'estimated' | 'cached' | 'unavailable' | 'legacy';

export const USAGE_STATUSES: readonly UsageStatus[] = [
  'reported',
  'estimated',
  'cached',
  'unavailable',
  'legacy',
];

/**
 * A stored count: a finite number, or `null` when the provider never reported one.
 *
 * The alias exists so "this may be unknown" is visible in the contract itself rather than in a
 * comment on each field.
 */
export type ReportedCount = number | null;

/** One traced agent run, as the list shows it. */
export interface AiRun {
  id: string;
  userId: string | null;
  workflow: string;
  agent: string;
  status: AiRunStatus | (string & {});
  trigger: string;
  provider: string | null;
  model: string | null;
  promptVersion: string | null;
  promptTokens: ReportedCount;
  completionTokens: ReportedCount;
  totalTokens: ReportedCount;
  cachedTokens: ReportedCount;
  costUsd: ReportedCount;
  costCny: ReportedCount;
  /** Which of the five states produced the counts above; `null` only on a pre-PHASE-13 row. */
  usageStatus: UsageStatus | (string & {}) | null;
  latencyMs: number | null;
  cacheHit: boolean;
  requestId: string | null;
  error: string | null;
  /** Machine-readable classification of `error` (`PROVIDER_UNAVAILABLE`, …). */
  errorCode: string | null;
  stepCount: number;
  startedAt: string | null;
  finishedAt: string | null;
}

/** `GET /ai-runs` is offset-paginated, not cursor-paginated, so it has its own list shape. */
export interface AiRunList {
  items: AiRun[];
  total: number;
  limit: number;
  offset: number;
}

/** The filters the list endpoint accepts (`GET /ai-runs`). */
export interface AiRunFilters {
  agent?: string;
  workflow?: string;
  status?: AiRunStatus;
  sinceHours?: number;
  limit?: number;
  offset?: number;
}

/** One workflow step, read from the run's own trace. */
export interface AiStep {
  name: string;
  status: string;
  latencyMs: number;
  provider: string | null;
  model: string | null;
  promptVersion: string | null;
  attempts: number;
  cacheHit: boolean;
  /**
   * `null` both when the step made no model call and when the call's usage went unreported —
   * `usageStatus` is what tells the two apart, and the distinction is why both fields exist.
   */
  tokens: ReportedCount;
  costUsd: ReportedCount;
  usageStatus: UsageStatus | (string & {}) | null;
  /** Digests, not payloads: the trace says what was sent without copying candidate material. */
  inputDigest: string;
  outputDigest: string;
  errorCode: string | null;
  errorMessage: string | null;
  startedAt: string | null;
}

/** One metered model call. A step can make two of these, and a call can happen outside a step. */
export interface LlmCall {
  id: string;
  agent: string;
  provider: string;
  /** Empty when the operation returned a parsed schema and the provider's envelope was dropped. */
  model: string;
  operation: string;
  promptVersion: string | null;
  promptTokens: ReportedCount;
  completionTokens: ReportedCount;
  totalTokens: ReportedCount;
  cachedTokens: ReportedCount;
  costUsd: ReportedCount;
  costCny: ReportedCount;
  usageStatus: UsageStatus | (string & {}) | null;
  latencyMs: number | null;
  status: string;
  requestId: string | null;
  createdAt: string | null;
}

/** `GET /ai-runs/{id}` — the run, its step chain and every call it made. */
export interface AiRunDetail extends AiRun {
  steps: AiStep[];
  calls: LlmCall[];
  inputRef: Record<string, unknown>;
  outputRef: Record<string, unknown>;
}

export interface DailyCost {
  /** `YYYY-MM-DD`, the day the run started. Only days with activity appear. */
  day: string;
  runs: number;
  tokens: number;
  costUsd: number;
  costCny: number;
}

export interface CostTotals {
  runs: number;
  modelCalls: number;
  tokens: number;
  costUsd: number;
  costCny: number;
  latencyMs: number;
}

export interface AiCosts {
  range: ObservabilityRange | (string & {});
  days: DailyCost[];
  totals: CostTotals;
  dailyBudgetUsd: number;
  /**
   * Runs in the window whose usage was never reported (`unavailable`/`legacy`).
   *
   * Their counters are `NULL` and `SUM` skips them, so `totals` is a **floor** and not a complete
   * figure. The page says so, which is the difference between an honest total and a plausible one.
   */
  unaccountedRuns: number;
  notes: string[];
}

export interface CostByAgent {
  agent: string;
  runs: number;
  tokens: number;
  costUsd: number;
  costCny: number;
  avgLatencyMs: number;
  cacheHits: number;
}

export interface CostByFeature {
  feature: string;
  workflows: string[];
  runs: number;
  tokens: number;
  costUsd: number;
  costCny: number;
}

export interface CacheKindStats {
  kind: string;
  entries: number;
  hits: number;
  bytes: number;
}

export interface CacheProcessStats {
  processHits: number;
  processMisses: number;
  processEntries: number;
  eventsFlushed: number;
  /** `null` before the process has answered anything: an empty cache has no hit *rate*. */
  hitRate: number | null;
}

export interface CacheStats {
  byKind: CacheKindStats[];
  persistedHits: number;
  process: CacheProcessStats;
}

export interface PromptVersion {
  name: string;
  version: number;
  sha256: string;
  isActive: boolean;
  updatedAt: string | null;
}
