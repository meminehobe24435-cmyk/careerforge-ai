import { cn, EMPTY_VALUE, formatDelta, formatScore } from '@/lib/utils';

export interface ProfileStrengthRingProps {
  score: number | null | undefined;
  delta7d?: number | null;
  size?: number;
  className?: string;
}

/**
 * Profile Strength ring — pure CSS (conic-gradient over design tokens), no chart library.
 * docs/UI.md §5.3 asks for an 82/100 style ring; the number always comes from
 * `GET /dashboard` → `profileStrength.score`, never from a hard-coded placeholder.
 */
export function ProfileStrengthRing({
  score,
  delta7d,
  size = 132,
  className,
}: ProfileStrengthRingProps) {
  const hasScore = typeof score === 'number' && Number.isFinite(score);
  const clamped = hasScore ? Math.max(0, Math.min(100, score)) : 0;
  const display = hasScore ? formatScore(score) : EMPTY_VALUE;

  return (
    <div className={cn('flex items-center gap-4', className)}>
      <div
        role="img"
        aria-label={hasScore ? `Profile Strength ${display} / 100` : 'Profile Strength 数据不可用'}
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
          五维拆解（资料完整度 / 证据覆盖率 / 证据质量 / GitHub 信号 / 成果加分）来自{' '}
          <span className="text-tertiary font-mono text-[11px]">GET /profile/strength</span>
          ，将在 PHASE 3 接入。
        </p>
        {typeof delta7d === 'number' ? (
          <p className="text-tertiary font-mono text-[11px] tabular-nums">
            近 7 天变化 {formatDelta(delta7d)}
          </p>
        ) : null}
      </div>
    </div>
  );
}
