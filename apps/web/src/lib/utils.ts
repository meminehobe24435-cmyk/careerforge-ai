export { cn } from '@careerforge/ui';

/**
 * Formatting helpers. Everything that renders a number, an id or a timestamp goes
 * through these so the "mono + tabular-nums" rule (docs/UI.md §2.2) stays consistent
 * and so a missing value never silently becomes `0`.
 */

/** `undefined`/`null` render as an em dash — never as a fabricated zero. */
export const EMPTY_VALUE = '—';

/**
 * Metrics such as `evidenceCoverage` arrive as 0..1 fractions (docs/API.md §2.10).
 * `null`/`NaN` → em dash rather than a fake percentage.
 */
export function formatFractionPercent(
  value: number | null | undefined,
  fractionDigits = 0,
): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return EMPTY_VALUE;
  return `${(value * 100).toFixed(fractionDigits)}%`;
}

/** Values already expressed as 0..100 (match score, profile strength). */
export function formatScore(value: number | null | undefined, fractionDigits = 0): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return EMPTY_VALUE;
  return value.toFixed(fractionDigits);
}

export function formatCount(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return EMPTY_VALUE;
  return new Intl.NumberFormat('zh-CN').format(value);
}

/** Signed 7-day delta: `+3` / `-2` / `0`. */
export function formatDelta(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return EMPTY_VALUE;
  if (value === 0) return '0';
  return value > 0 ? `+${value}` : `${value}`;
}

export function formatLatency(ms: number | null | undefined): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms)) return EMPTY_VALUE;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY_VALUE;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return EMPTY_VALUE;
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

/** Short relative time (`3天前`) for evidence freshness; falls back to the date. */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY_VALUE;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return EMPTY_VALUE;

  const diffMs = date.getTime() - Date.now();
  const diffMinutes = Math.round(diffMs / 60_000);
  const formatter = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' });
  const absMinutes = Math.abs(diffMinutes);

  if (absMinutes < 60) return formatter.format(diffMinutes, 'minute');
  const diffHours = Math.round(diffMinutes / 60);
  if (Math.abs(diffHours) < 24) return formatter.format(diffHours, 'hour');
  const diffDays = Math.round(diffHours / 24);
  if (Math.abs(diffDays) < 30) return formatter.format(diffDays, 'day');
  return formatter.format(Math.round(diffDays / 30), 'month');
}

/** Truncates the middle of long ids/hashes: `req_01HQ8Z…9f2c`. */
export function truncateMiddle(value: string, max = 18): string {
  if (value.length <= max) return value;
  const head = Math.ceil((max - 1) / 2);
  const tail = Math.floor((max - 1) / 2);
  return `${value.slice(0, head)}…${value.slice(value.length - tail)}`;
}

/** Initials for the user avatar (`Alex Chen` → `AC`). */
export function initialsOf(displayName: string): string {
  const parts = displayName
    .split(/[\s_-]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  const first = parts[0]?.charAt(0) ?? '?';
  const last = parts.length > 1 ? (parts[parts.length - 1]?.charAt(0) ?? '') : '';
  return `${first}${last}`.toUpperCase();
}
