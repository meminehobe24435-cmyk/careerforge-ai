import { Card, CardContent, Tooltip } from '@careerforge/ui';
import { Info } from 'lucide-react';

import { EMPTY_VALUE, formatCount, formatFractionPercent } from '@/lib/utils';

export interface StatCardProps {
  label: string;
  /** Raw API value: a 0..1 fraction for coverage/match metrics, a count otherwise. */
  value: number | null | undefined;
  kind: 'fraction' | 'count';
  /** Metric definition (`口径`) — shown on hover and to screen readers via the label. */
  definition: string;
  /** Optional 7-day delta once the backend exposes it (docs/API.md §2.10 has no trend yet). */
  delta?: number | null;
  /**
   * Set when the API reports this metric in `meta.unavailable`.
   *
   * A zero on a dashboard reads as "you have none". For a metric whose data source does not
   * exist yet — the application tracker — that would be a claim the system cannot make, so
   * the card says "not tracked yet" and keeps the number out of the way.
   */
  unavailable?: string | null;
}

/**
 * StatCard — one metric, its definition, and nothing invented.
 *
 * docs/UI.md §5.3 asks for a 7-day mini trend per card; `GET /dashboard` does not return
 * trend series today, so the card shows the documented value and states where the trend
 * will come from instead of drawing a decorative fake sparkline.
 */
export function StatCard({ label, value, kind, definition, delta, unavailable }: StatCardProps) {
  const display = kind === 'fraction' ? formatFractionPercent(value) : formatCount(value);
  const isMissing = display === EMPTY_VALUE;

  return (
    <Card className="min-w-0">
      <CardContent className="flex flex-col gap-2 p-4 pt-4">
        <div className="flex items-start gap-1.5">
          <p className="text-tertiary min-w-0 flex-1 truncate font-mono text-[11px] uppercase tracking-wide">
            {label}
          </p>
          <Tooltip content={definition}>
            <span
              className="text-tertiary focus-visible:outline-brand shrink-0 rounded-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2"
              role="img"
              aria-label={`${label} 口径：${definition}`}
              tabIndex={0}
            >
              <Info className="size-3.5" aria-hidden="true" />
            </span>
          </Tooltip>
        </div>

        {unavailable ? (
          <>
            <p className="text-secondary font-mono text-sm leading-none">尚未接入</p>
            <p className="text-tertiary font-mono text-[11px]">{unavailable}</p>
          </>
        ) : (
          <>
            <p className="text-primary font-mono text-2xl tabular-nums leading-none">{display}</p>

            <div className="flex items-center gap-2">
              {typeof delta === 'number' ? (
                <span
                  className={
                    delta > 0
                      ? 'text-evidence font-mono text-[11px] tabular-nums'
                      : 'text-secondary font-mono text-[11px] tabular-nums'
                  }
                >
                  {delta > 0 ? `+${delta}` : `${delta}`} / 7d
                </span>
              ) : (
                <span className="text-tertiary font-mono text-[11px]">7d trend · PHASE 10</span>
              )}
            </div>

            {isMissing ? (
              <p className="text-weak text-[11px]">接口未返回该字段 —— 不显示推测值</p>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
