import {
  APPLICATION_STATUSES,
  type AiCosts,
  type AiRun,
  type AiRunDetail,
  type AiRunList,
  type ApplicationBoardResponse,
  type ApplicationCard,
  type ApplicationColumn,
  type ApplicationDetail,
  type ApplicationEvent,
  type ApplicationStatus,
  type CacheStats,
  type CategoryPerformance,
  type CostByAgent,
  type CostByFeature,
  type DashboardResponse,
  type DashboardStats,
  type FunnelResponse,
  type PromptVersion,
  type PublicEvidence,
  type PublicProfileResponse,
  type PublicSettingsResponse,
  type RatesResponse,
  type ServiceHealthStatus,
  type SkillCorrelation,
  type TimelineResponse,
} from './types.ts';

/** Narrow `unknown` to a plain object (safe for `noUncheckedIndexedAccess`). */
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

export function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function hasNumericStats(stats: unknown): stats is DashboardStats {
  if (!isRecord(stats)) return false;
  return (
    isNumber(stats['evidenceCoverage']) &&
    isNumber(stats['skillCoverage']) &&
    isNumber(stats['resumeMatch']) &&
    isNumber(stats['applications']) &&
    isNumber(stats['interviews']) &&
    isNumber(stats['offers'])
  );
}

/**
 * Runtime guard for `GET /dashboard` (API.md §2.10).
 *
 * Deliberately tolerant: `skillsRadar` / `recentJobs` / `nextActions` are normalised to
 * `[]` when absent, because the six stat numbers are what the UI must never fake —
 * the rest can legitimately be empty for a brand-new account.
 */
export function isDashboardResponse(value: unknown): value is DashboardResponse {
  if (!isRecord(value)) return false;
  const strength = value['profileStrength'];
  if (!isRecord(strength) || !isNumber(strength['score'])) return false;
  return hasNumericStats(value['stats']);
}

export function toServiceHealthStatus(value: unknown): ServiceHealthStatus {
  if (!isString(value)) return 'unknown';
  const normalised = value.toLowerCase();
  if (['ok', 'up', 'healthy', 'ready', 'pass', 'online'].includes(normalised)) return 'ok';
  if (['degraded', 'warn', 'warning', 'partial'].includes(normalised)) return 'degraded';
  if (['down', 'unhealthy', 'fail', 'error', 'offline', 'unavailable'].includes(normalised)) {
    return 'down';
  }
  return 'unknown';
}

/* ------------------------------------------------------------------ *
 * Application tracker (API.md §2.9)
 * ------------------------------------------------------------------ */

export function isApplicationStatus(value: unknown): value is ApplicationStatus {
  return isString(value) && (APPLICATION_STATUSES as readonly string[]).includes(value);
}

/**
 * One card.
 *
 * The guard checks the fields the board cannot render without — id, status, company — and
 * tolerates the rest. A card whose `company` arrived missing is a contract bug worth
 * failing on; a card without `salaryExpectation` is an ordinary card.
 */
export function isApplicationCard(value: unknown): value is ApplicationCard {
  if (!isRecord(value)) return false;
  return (
    isString(value['id']) &&
    isString(value['company']) &&
    isString(value['role']) &&
    isApplicationStatus(value['status']) &&
    (value['position'] === undefined || isNumber(value['position']))
  );
}

function isApplicationColumn(value: unknown): value is ApplicationColumn {
  if (!isRecord(value)) return false;
  const items = value['items'];
  return (
    isApplicationStatus(value['status']) &&
    Array.isArray(items) &&
    items.every((item) => isApplicationCard(item))
  );
}

/**
 * Runtime guard for `GET /applications/board` (API.md §2.9).
 *
 * `columns` must cover all seven statuses exactly: the board's whole promise is "every
 * column is present, empty ones included", so a board missing a column is a contract
 * violation rather than something to patch over by rendering six columns.
 */
export function isApplicationBoard(value: unknown): value is ApplicationBoardResponse {
  if (!isRecord(value)) return false;
  const columns = value['columns'];
  if (!Array.isArray(columns) || !columns.every((column) => isApplicationColumn(column))) {
    return false;
  }
  const statuses = columns.map((column) => (column as ApplicationColumn).status);
  if (statuses.length !== APPLICATION_STATUSES.length) return false;
  if (new Set(statuses).size !== statuses.length) return false;
  if (!APPLICATION_STATUSES.every((status) => statuses.includes(status))) return false;
  const counts = value['counts'];
  if (counts !== undefined && isRecord(counts)) {
    if (!Object.values(counts).every((count) => isNumber(count))) return false;
  }
  return true;
}

function isApplicationEvent(value: unknown): value is ApplicationEvent {
  if (!isRecord(value)) return false;
  return isString(value['id']) && isApplicationStatus(value['toStatus']);
}

/** `GET /applications/{id}` — a card with its history. */
export function isApplicationDetail(value: unknown): value is ApplicationDetail {
  if (!isApplicationCard(value)) return false;
  const events = (value as { events?: unknown }).events;
  return Array.isArray(events) && events.every((event) => isApplicationEvent(event));
}

/* ------------------------------------------------------------------ *
 * Analytics (API.md §2.11)
 * ------------------------------------------------------------------ */

/**
 * `GET /analytics/funnel`.
 *
 * The guard requires the meta block, because a funnel without its window and its stated basis
 * is exactly the payload that gets misread: the five counts look authoritative on their own.
 */
export function isFunnelResponse(value: unknown): value is FunnelResponse {
  if (!isRecord(value)) return false;
  const meta = value['meta'];
  if (!isRecord(meta) || !isString(meta['range']) || !isNumber(meta['cohortSize'])) return false;
  const stages = value['stages'];
  return (
    Array.isArray(stages) &&
    stages.length > 0 &&
    stages.every(
      (stage) =>
        isRecord(stage) &&
        isString(stage['key']) &&
        isNumber(stage['count']) &&
        isNumber(stage['shareOfFirst']),
    )
  );
}

export function isRatesResponse(value: unknown): value is RatesResponse {
  if (!isRecord(value)) return false;
  if (!isRecord(value['meta'])) return false;
  const cards = value['cards'];
  return (
    Array.isArray(cards) &&
    cards.length > 0 &&
    cards.every(
      (card) =>
        isRecord(card) &&
        isString(card['key']) &&
        isNumber(card['numerator']) &&
        isNumber(card['denominator']) &&
        typeof card['sufficient'] === 'boolean',
    )
  );
}

export function isTimelineResponse(value: unknown): value is TimelineResponse {
  if (!isRecord(value)) return false;
  if (!isRecord(value['meta'])) return false;
  const entries = value['entries'];
  const buckets = value['buckets'];
  return (
    Array.isArray(entries) &&
    Array.isArray(buckets) &&
    entries.every((entry) => isRecord(entry) && isString(entry['title'])) &&
    buckets.every((bucket) => isRecord(bucket) && isString(bucket['month']))
  );
}

/** The correlation and category endpoints return bare arrays; validate the fields used. */
export function isSkillCorrelationList(value: unknown): value is SkillCorrelation[] {
  return (
    Array.isArray(value) &&
    value.every(
      (row) =>
        isRecord(row) &&
        isString(row['skillId']) &&
        isNumber(row['withSkillTotal']) &&
        isNumber(row['withoutSkillTotal']) &&
        typeof row['sufficient'] === 'boolean',
    )
  );
}

export function isCategoryPerformanceList(value: unknown): value is CategoryPerformance[] {
  return (
    Array.isArray(value) &&
    value.every(
      (row) =>
        isRecord(row) &&
        isString(row['category']) &&
        isNumber(row['applications']) &&
        isNumber(row['interviews']),
    )
  );
}

/* ------------------------------------------------------------------ *
 * Public candidate page (API.md §2.13)
 * ------------------------------------------------------------------ */

/**
 * `GET /public/candidate/{slug}`.
 *
 * The guard requires `displayName` and `meta` — a public page without its meta block would hide
 * which sections are private, which is the one piece of the payload a reader needs to interpret
 * the rest.
 */
export function isPublicProfileResponse(value: unknown): value is PublicProfileResponse {
  if (!isRecord(value)) return false;
  if (!isString(value['displayName'])) return false;
  const meta = value['meta'];
  if (!isRecord(meta) || !isString(meta['slug'])) return false;
  const skills = value['skills'];
  return (
    Array.isArray(skills) &&
    skills.every(
      (skill) =>
        isRecord(skill) && isString(skill['canonicalId']) && isString(skill['displayName']),
    )
  );
}

export function isPublicEvidenceList(value: unknown): value is PublicEvidence[] {
  return (
    Array.isArray(value) &&
    value.every((item) => isRecord(item) && isString(item['evidenceId']) && isString(item['title']))
  );
}

export function isPublicSettingsResponse(value: unknown): value is PublicSettingsResponse {
  if (!isRecord(value)) return false;
  return (
    typeof value['isPublished'] === 'boolean' &&
    typeof value['canPublish'] === 'boolean' &&
    isRecord(value['sections'])
  );
}

/* ------------------------------------------------------------------ *
 * AI observability (API.md §2.12)
 * ------------------------------------------------------------------ */

/**
 * The guards below are deliberately about **presence and type**, not about totals.
 *
 * The pages must never invent a number, so what has to be guaranteed is that the fields it prints
 * exist and are the right kind; whether they are zero is a fact about the deployment (the zero-key
 * provider really does spend nothing) and not something a guard should reject.
 */

function isAiRun(value: unknown): value is AiRun {
  return (
    isRecord(value) &&
    isString(value['id']) &&
    isString(value['workflow']) &&
    isString(value['agent']) &&
    isString(value['status']) &&
    isNumber(value['totalTokens']) &&
    isNumber(value['costUsd']) &&
    typeof value['cacheHit'] === 'boolean' &&
    isNumber(value['stepCount'])
  );
}

export function isAiRunList(value: unknown): value is AiRunList {
  if (!isRecord(value)) return false;
  const items = value['items'];
  return Array.isArray(items) && items.every(isAiRun) && isNumber(value['total']);
}

/** `GET /ai-runs/{id}` — requires the step chain, which is the whole reason to open the row. */
export function isAiRunDetail(value: unknown): value is AiRunDetail {
  if (!isAiRun(value)) return false;
  const detail = value as unknown as Record<string, unknown>;
  const steps = detail['steps'];
  const calls = detail['calls'];
  return (
    Array.isArray(steps) &&
    steps.every((step) => isRecord(step) && isString(step['name'])) &&
    Array.isArray(calls) &&
    calls.every((call) => isRecord(call) && isString(call['provider']))
  );
}

/** `GET /ai-costs` — `totals` is what the page would otherwise have to sum itself. */
export function isAiCosts(value: unknown): value is AiCosts {
  if (!isRecord(value)) return false;
  const totals = value['totals'];
  const days = value['days'];
  if (!isRecord(totals) || !isNumber(totals['runs']) || !isNumber(totals['costUsd'])) return false;
  return (
    Array.isArray(days) &&
    days.every((day) => isRecord(day) && isString(day['day']) && isNumber(day['costUsd'])) &&
    isNumber(value['dailyBudgetUsd'])
  );
}

function isCostRow(value: unknown, key: string): boolean {
  return (
    isRecord(value) && isString(value[key]) && isNumber(value['runs']) && isNumber(value['tokens'])
  );
}

export function isCostByAgentList(value: unknown): value is CostByAgent[] {
  return Array.isArray(value) && value.every((row) => isCostRow(row, 'agent'));
}

export function isCostByFeatureList(value: unknown): value is CostByFeature[] {
  return (
    Array.isArray(value) &&
    value.every(
      (row) =>
        isCostRow(row, 'feature') && Array.isArray((row as Record<string, unknown>)['workflows']),
    )
  );
}

/**
 * `GET /cache/stats`.
 *
 * `process` must be present and `hitRate` must be a number or `null` — the page prints "尚未服务"
 * for `null`, and a missing field would make that indistinguishable from a broken response.
 */
export function isCacheStats(value: unknown): value is CacheStats {
  if (!isRecord(value)) return false;
  const byKind = value['byKind'];
  const process = value['process'];
  if (!Array.isArray(byKind) || !byKind.every((item) => isRecord(item) && isString(item['kind']))) {
    return false;
  }
  if (
    !isRecord(process) ||
    !isNumber(process['processHits']) ||
    !isNumber(process['processMisses'])
  ) {
    return false;
  }
  const hitRate = process['hitRate'];
  return hitRate === null || isNumber(hitRate);
}

/** `GET /prompts` — a bare array; `version` is the field the page attributes runs to. */
export function isPromptVersionList(value: unknown): value is PromptVersion[] {
  return (
    Array.isArray(value) &&
    value.every(
      (row) =>
        isRecord(row) &&
        isString(row['name']) &&
        isNumber(row['version']) &&
        typeof row['isActive'] === 'boolean',
    )
  );
}
