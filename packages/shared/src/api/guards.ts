import {
  APPLICATION_STATUSES,
  type ApplicationBoardResponse,
  type ApplicationCard,
  type ApplicationColumn,
  type ApplicationDetail,
  type ApplicationEvent,
  type ApplicationStatus,
  type DashboardResponse,
  type DashboardStats,
  type ServiceHealthStatus,
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
