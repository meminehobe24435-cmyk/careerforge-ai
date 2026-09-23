import type { DashboardResponse, DashboardStats, ServiceHealthStatus } from './types';

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
