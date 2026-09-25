import type {
  AiRun,
  AiRunStatus,
  CacheStats,
  DailyCost,
  ObservabilityRange,
  UsageStatus,
} from '@careerforge/shared';

/**
 * Presentation arithmetic for the AI Runs and Cost pages.
 *
 * Pure on purpose, like `analytics-format.ts`: the decisions here are the ones a reader will check
 * with a calculator, and every one of them is about **not overstating what was measured**.
 *
 * Three rules the functions below enforce:
 *
 * 1. `null` is not `0`. `latencyMs` on an unfinished run, `hitRate` on a cache that has served
 *    nothing, and — since PHASE 13 — every token/cost count the provider never reported render as
 *    an em dash; a real `0` renders as `0`. `usageStatus` is what says *which* of the two a row is.
 * 2. Timestamps are read on the same clock they were written on. The API stores naive-UTC
 *    instants (`utcnow()`), and `new Date('2026-09-24T10:00:00')` in a browser parses that as
 *    *local* time — a silent 8-hour shift for a reader in UTC+8. `parseApiInstant` adds the missing
 *    `Z` and the formatter renders UTC, which is why every page labels the column "UTC".
 * 3. Tokens and cost come from the provider. A deployment on the zero-key heuristic provider
 *    reports 0 because it spent 0, so the page says *why* instead of hiding the column — and where
 *    the truth is "the provider said nothing", it says that instead of a zero nobody measured.
 */

/** Group digits without depending on the runner's ICU data (`1,500`, always). */
export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const rounded = Math.round(value);
  const sign = rounded < 0 ? '-' : '';
  return sign + String(Math.abs(rounded)).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * USD with a precision that matches the magnitude: model calls cost fractions of a cent, and a
 * `$0.00` for a real charge would read as free.
 */
export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const magnitude = Math.abs(value);
  const digits = magnitude === 0 ? 4 : magnitude < 1 ? 4 : 2;
  return `$${value.toFixed(digits)}`;
}

/** CNY beside it, for the reader who pays in it. */
export function formatCny(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  const magnitude = Math.abs(value);
  const digits = magnitude === 0 ? 4 : magnitude < 1 ? 4 : 2;
  return `¥${value.toFixed(digits)}`;
}

/** `93` → `93 ms`; `1240` → `1.24 s`; `null` → an em dash (the run never finished). */
export function formatLatency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return '—';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '—';
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

/**
 * The API's naive-UTC instant, read as the UTC it actually is.
 *
 * A string that already carries an offset (`Z`, `+08:00`) is left alone; a bare
 * `2026-09-24T10:00:00` gets `Z` appended so the browser does not reinterpret it as local time.
 */
export function parseApiInstant(value: string | null | undefined): Date | null {
  if (!value) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value);
  const normalised = hasZone ? value : `${value}Z`;
  const parsed = new Date(normalised);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/** `2026-09-24 10:04` on the UTC clock the value was written on. */
export function formatInstant(value: string | null | undefined): string {
  const parsed = parseApiInstant(value);
  if (!parsed) return '—';
  const iso = parsed.toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;
}

/**
 * A duration between two instants, in words.
 *
 * Shown beside a run because "started 10:04, finished 10:04" hides whether the run took 90 ms or
 * nine minutes — and `latencyMs` on the row is the *provider's* number, not the wall clock. Unlike
 * `formatLatency` this scales up to minutes and hours: a run that a reader waited on for two
 * minutes should not have to be read as `120.00 s`.
 */
export function formatDuration(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
): string {
  const start = parseApiInstant(startedAt);
  const end = parseApiInstant(finishedAt);
  if (!start || !end) return '—';
  const ms = end.getTime() - start.getTime();
  if (ms < 0) return '—';
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(2)} s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${minutes.toFixed(1)} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}

/** Digests are shown truncated: enough to compare two runs, not a wall of hex. */
export function shortDigest(digest: string | null | undefined): string {
  if (!digest) return '—';
  return digest.length <= 12 ? digest : `${digest.slice(0, 12)}…`;
}

const STATUS_LABELS: Record<
  string,
  { label: string; variant: 'supported' | 'signal' | 'weak' | 'danger' | 'outline' }
> = {
  succeeded: { label: '成功', variant: 'supported' },
  degraded: { label: '降级', variant: 'weak' },
  failed: { label: '失败', variant: 'danger' },
  running: { label: '运行中', variant: 'signal' },
  cancelled: { label: '已取消', variant: 'outline' },
  ok: { label: '成功', variant: 'supported' },
  skipped: { label: '跳过', variant: 'outline' },
  cached: { label: '缓存命中', variant: 'signal' },
};

export function statusBadge(status: string | null | undefined): {
  label: string;
  variant: 'supported' | 'signal' | 'weak' | 'danger' | 'outline';
} {
  if (!status) return { label: '未知', variant: 'outline' };
  return STATUS_LABELS[status] ?? { label: status, variant: 'outline' };
}

export const RUN_STATUS_FILTERS: readonly { value: AiRunStatus | 'all'; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'succeeded', label: '成功' },
  { value: 'degraded', label: '降级' },
  { value: 'failed', label: '失败' },
  { value: 'running', label: '运行中' },
];

export const SINCE_HOUR_FILTERS: readonly { value: number | null; label: string }[] = [
  { value: null, label: '不限时间' },
  { value: 1, label: '1 小时' },
  { value: 24, label: '24 小时' },
  { value: 24 * 7, label: '7 天' },
];

/**
 * Why a whole page of runs can honestly report nothing, or nothing but zeros.
 *
 * Three cases, and they are three different sentences because they are three different facts:
 *
 * * **all counts `null`** — the provider returned no usage metadata. There is no number to print,
 *   so the list says `—` and this note says why;
 * * **all counts `0` on the zero-key heuristic provider** — a first-class deployment (ADR-009)
 *   that really does spend nothing, named rather than left to be misread as broken metering;
 * * **anything else with no positive count** — reported as a page of zeros with the providers
 *   named, because the cause is no longer visible from the page alone.
 *
 * A single run with a positive count means the numbers speak for themselves and this returns
 * `null`.
 */
export function zeroSpendSummary(
  runs: readonly Pick<AiRun, 'provider' | 'totalTokens'>[],
): string | null {
  if (runs.length === 0) return null;
  if (runs.some((run) => (run.totalTokens ?? 0) > 0)) return null;

  if (runs.every((run) => run.totalTokens === null)) {
    return '这些运行全部报告 null token：provider 没有返回 usage metadata（usageStatus=unavailable），因此没有可显示的用量 —— 这是「未知」，不是 0。延迟仍然被真实测量。';
  }

  const providers = new Set(runs.map((run) => run.provider ?? '（未记录）'));
  if (providers.size === 1 && providers.has('heuristic')) {
    return '这些运行全部报告 0 token：零 Key 启发式 provider 用本地规则计算，不调用模型。延迟仍然被真实测量。';
  }
  return `这些运行报告的 token 均为 0（provider：${[...providers].join('、')}）——可能是未调用模型，也可能是上游没有返回用量。`;
}

/** One usage status, as a reader should read it. */
export interface UsageStatusReading {
  key: string;
  /** `Reported` · `Estimated` · `Cached` · `Unavailable` · `Legacy`, plus a raw fallback. */
  label: string;
  /** One short line of *why*, printed as secondary text — never a badge wall. */
  detail: string;
  /** True when no number on the row can be trusted as a measurement. */
  unmeasured: boolean;
}

const USAGE_STATUS_READINGS: Record<UsageStatus, UsageStatusReading> = {
  reported: {
    key: 'reported',
    label: 'Reported',
    detail: 'Provider returned usage metadata.',
    unmeasured: false,
  },
  estimated: {
    key: 'estimated',
    label: 'Estimated',
    detail: 'Computed locally — a bound, not a billed amount.',
    unmeasured: false,
  },
  cached: {
    key: 'cached',
    label: 'Cached',
    detail: 'Served from the cache, so nothing was billed.',
    unmeasured: false,
  },
  unavailable: {
    key: 'unavailable',
    label: 'Unavailable',
    detail: 'Provider did not return usage metadata.',
    unmeasured: true,
  },
  legacy: {
    key: 'legacy',
    label: 'Legacy',
    detail:
      'Row written before the usage envelope existed; its 0s cannot be trusted as measurements.',
    unmeasured: true,
  },
};

/**
 * The usage status a number came with, in the page's vocabulary.
 *
 * Order matters and is stated rather than implied: a `cached` run is *not* a measured spend, a
 * `legacy` row is not a measured zero, and an unknown string is shown **as itself** — inventing a
 * reading for a status this build does not know would be the same class of lie as printing 0.
 */
export function usageStatusReading(status: string | null | undefined): UsageStatusReading | null {
  if (!status) return null;
  const known = USAGE_STATUS_READINGS[status as UsageStatus];
  if (known) return known;
  return {
    key: status,
    label: status,
    detail: 'Unknown to this build; shown as returned rather than translated.',
    unmeasured: true,
  };
}

/** The five states, in the order the glossary prints them. */
export const USAGE_STATUS_GLOSSARY: readonly UsageStatusReading[] = [
  USAGE_STATUS_READINGS.reported,
  USAGE_STATUS_READINGS.estimated,
  USAGE_STATUS_READINGS.cached,
  USAGE_STATUS_READINGS.unavailable,
  USAGE_STATUS_READINGS.legacy,
];

/** How many runs came with each status, for the one-line summary above the list. */
export function usageStatusCounts(
  runs: readonly Pick<AiRun, 'usageStatus'>[],
): { reading: UsageStatusReading; count: number }[] {
  const counts = new Map<string, { reading: UsageStatusReading; count: number }>();
  for (const run of runs) {
    const reading = usageStatusReading(run.usageStatus);
    if (!reading) continue;
    const current = counts.get(reading.key);
    counts.set(reading.key, { reading, count: (current?.count ?? 0) + 1 });
  }
  return USAGE_STATUS_GLOSSARY.filter((entry) => counts.has(entry.key)).map(
    (entry) => counts.get(entry.key) as { reading: UsageStatusReading; count: number },
  );
}

export interface SpendSummary {
  /** Sum of the costs the API actually reported; `0` only when every reported cost was `0`. */
  usd: number;
  /** How many rows carried a number at all. */
  reported: number;
  /** How many rows carried `null` — their spend is unknown and is *not* in `usd`. */
  unavailable: number;
}

/**
 * The spend of the rows on screen, with the rows that have no number counted separately.
 *
 * Summing a row whose `costUsd` is `null` as if it were `0` is the exact lie PHASE 13 removed from
 * the backend, so the sum is over reported values only and the caller is told how many were left
 * out. On a zero-key deployment `reported` is every row and the sum is a real `$0.0000`.
 */
export function spendSummary(runs: readonly Pick<AiRun, 'costUsd'>[]): SpendSummary {
  let usd = 0;
  let reported = 0;
  let unavailable = 0;
  for (const run of runs) {
    if (run.costUsd === null || run.costUsd === undefined || !Number.isFinite(run.costUsd)) {
      unavailable += 1;
      continue;
    }
    usd += run.costUsd;
    reported += 1;
  }
  return { usd, reported, unavailable };
}

/**
 * What a total that skips unreported runs means.
 *
 * `unaccountedRuns === 0` returns `null`: the total is complete and needs no caveat. Anything else
 * is a **floor**, and the page has to say so where the number is.
 */
export function unaccountedSummary(unaccountedRuns: number): string | null {
  if (!Number.isFinite(unaccountedRuns) || unaccountedRuns <= 0) return null;
  return `窗口内有 ${formatCount(unaccountedRuns)} 次运行的用量未被 provider 上报（token/成本为 null，未计入合计）——因此上面的合计是下限，不是确切值。`;
}

/** `5 天里有 3 天有运行` — the API does not zero-fill empty days, so the page says so (see UI.md). */
export function activityWindowNote(
  days: DailyCost[],
  range: ObservabilityRange | (string & {}),
): string | null {
  const expected: Record<string, number> = { '7d': 7, '30d': 30, '90d': 90 };
  const window = expected[range];
  if (window === undefined) return null;
  return `窗口 ${window} 天中 ${days.length} 天有运行记录（接口只返回有活动的日期，不做零填充）`;
}

/** The newest day the API reported, which is what the budget guard is compared against. */
export function latestDay(days: DailyCost[]): DailyCost | null {
  if (days.length === 0) return null;
  return days[days.length - 1] as DailyCost;
}

export interface BudgetUsage {
  /** `null` when no budget is configured (`dailyBudgetUsd <= 0`): there is no ratio to report. */
  ratio: number | null;
  spentUsd: number;
  budgetUsd: number;
  exceeded: boolean;
  label: string;
}

/**
 * Today's spend against the guard rail.
 *
 * `dailyBudgetUsd = 0` means "no ceiling configured", not "0 dollars allowed", so the ratio is
 * `null` and the label says so. Anything else would render a full red bar on a deployment that has
 * no budget at all.
 */
export function budgetUsage(day: DailyCost | null, dailyBudgetUsd: number): BudgetUsage {
  const spentUsd = day?.costUsd ?? 0;
  if (!Number.isFinite(dailyBudgetUsd) || dailyBudgetUsd <= 0) {
    return {
      ratio: null,
      spentUsd,
      budgetUsd: dailyBudgetUsd,
      exceeded: false,
      label: '未配置日预算上限（AI_DAILY_BUDGET_USD 为空或 0）',
    };
  }
  return {
    ratio: Math.min(1, spentUsd / dailyBudgetUsd),
    spentUsd,
    budgetUsd: dailyBudgetUsd,
    exceeded: spentUsd > dailyBudgetUsd,
    label: `${formatUsd(spentUsd)} / ${formatUsd(dailyBudgetUsd)}`,
  };
}

export interface CostShare {
  key: string;
  label: string;
  value: number;
  /** `0` when nothing was spent: a share of an empty total is not a share. */
  share: number;
}

/**
 * Shares are computed against the sum of the rows handed in, so a zero total yields zero shares
 * instead of `NaN` — and the page prints "本窗口没有可归因的花费" rather than an empty bar.
 */
export function costShares(rows: readonly { key: string; label: string; value: number }[]): {
  rows: CostShare[];
  total: number;
} {
  const total = rows.reduce((sum, row) => sum + (Number.isFinite(row.value) ? row.value : 0), 0);
  return {
    total,
    rows: rows.map((row) => ({
      key: row.key,
      label: row.label,
      value: row.value,
      share: total > 0 ? row.value / total : 0,
    })),
  };
}

/** The cache gauge's reading, with `null` preserved for "nothing served yet". */
export function cacheHitReading(stats: CacheStats | undefined): {
  rate: number | null;
  requests: number;
  label: string;
} {
  const process = stats?.process;
  if (!process) return { rate: null, requests: 0, label: '缓存统计不可用' };
  const requests = process.processHits + process.processMisses;
  if (process.hitRate === null) {
    return { rate: null, requests, label: '本进程还没有请求经过缓存，命中率不可计算' };
  }
  return {
    rate: process.hitRate,
    requests,
    label: `${formatCount(process.processHits)} 命中 / ${formatCount(requests)} 次查询`,
  };
}
