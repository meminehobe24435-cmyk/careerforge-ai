import { cn, EMPTY_VALUE, formatDelta, formatScore } from '@/lib/utils';
import type { DashboardStrengthDimension } from '@careerforge/shared';

export interface ProfileStrengthRingProps {
  score: number | null | undefined;
  delta7d?: number | null;
  /**
   * The five weighted dimensions the API returned, in its own order and with its own labels.
   *
   * Optional because the payload shape is additive: a response without them renders the ring alone.
   * What is *not* done here is deriving them from the score — a breakdown computed in the browser
   * would be a second opinion about arithmetic that already has an owner (`strength@1.0.0`).
   */
  dimensions?: DashboardStrengthDimension[] | null;
  /** e.g. `strength@1.0.0`; printed under the breakdown so the score is attributable. */
  algorithmVersion?: string | null;
  size?: number;
  className?: string;
}

/**
 * Profile Strength ring — pure CSS (conic-gradient over design tokens), no chart library.
 * docs/UI.md §5.3 asks for an 82/100 style ring; the number always comes from
 * `GET /dashboard` → `profileStrength.score`, never from a hard-coded placeholder.
 *
 * The five-dimension breakdown below the ring is the API's own (`profileStrength.dimensions`). It is
 * here rather than absent because the engine's stated purpose is that a bare number is not
 * actionable — and because this card used to tell the reader the breakdown would arrive in a later
 * phase, while the server was computing it on every request and the response was dropping it.
 */
export function ProfileStrengthRing({
  score,
  delta7d,
  dimensions,
  algorithmVersion,
  size = 132,
  className,
}: ProfileStrengthRingProps) {
  const hasScore = typeof score === 'number' && Number.isFinite(score);
  const clamped = hasScore ? Math.max(0, Math.min(100, score)) : 0;
  const display = hasScore ? formatScore(score) : EMPTY_VALUE;
  const rows = dimensions ?? [];

  return (
    <div className={cn('flex flex-col gap-4', className)}>
      <div className="flex items-center gap-4">
        <div
          role="img"
          aria-label={
            hasScore ? `Profile Strength ${display} / 100` : 'Profile Strength 数据不可用'
          }
          className="relative shrink-0 rounded-full"
          style={{
            width: size,
            height: size,
            backgroundImage: hasScore
              ? `conic-gradient(var(--brand) ${clamped * 3.6}deg, var(--bg-active) 0deg)`
              : 'conic-gradient(var(--bg-active) 360deg, var(--bg-active) 0deg)',
          }}
        >
          <div className="bg-surface absolute inset-[7px] flex flex-col items-center justify-center rounded-full">
            <span className="text-primary font-mono text-2xl tabular-nums leading-none">
              {display}
            </span>
            <span className="text-tertiary mt-1 font-mono text-[10px]">/ 100</span>
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-2">
          <p className="text-primary text-sm font-medium">Profile Strength</p>
          <p className="text-secondary text-xs leading-relaxed">
            五维加权得分，由确定性引擎计算（非模型生成）。每一维的贡献在下方列出，五项相加即总分。
          </p>
          {typeof delta7d === 'number' ? (
            <p className="text-tertiary font-mono text-[11px] tabular-nums">
              近 7 天变化 {formatDelta(delta7d)}
            </p>
          ) : null}
        </div>
      </div>

      {rows.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <dl className="flex flex-col gap-1.5" data-testid="strength-dimensions">
            {rows.map((row) => (
              <div
                key={row.key}
                data-dimension={row.key}
                className="flex items-baseline justify-between gap-3"
              >
                <dt className="text-secondary min-w-0 truncate text-[11px]">
                  {row.label}
                  <span className="text-tertiary ml-1.5 font-mono text-[10px] tabular-nums">
                    ×{row.weight.toFixed(2)}
                  </span>
                </dt>
                <dd className="text-primary shrink-0 font-mono text-[11px] tabular-nums">
                  {row.weighted.toFixed(1)}
                </dd>
              </div>
            ))}
          </dl>
          <p className="text-tertiary font-mono text-[10px]">
            {algorithmVersion ? `${algorithmVersion} · ` : ''}weighted = raw × weight × 100
          </p>
        </div>
      ) : null}
    </div>
  );
}
