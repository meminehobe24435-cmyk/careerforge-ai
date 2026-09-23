'use client';

import type { FunnelStage } from '@careerforge/shared';

import { formatRate, formatStepRate, funnelBandPath, funnelGeometry } from '@/lib/analytics-format';

interface FunnelChartProps {
  stages: FunnelStage[];
  height?: number;
}

/**
 * The funnel, drawn as SVG rather than with a chart library.
 *
 * Five bands with one number each do not justify a dependency, and hand-drawn geometry makes
 * the honest cases obvious: a stage with no cards is a **zero-width band**, so the shape shows
 * where the pipeline stopped rather than hiding it behind an interpolated line. The geometry
 * itself is a pure function (`funnelGeometry`) with its own tests.
 *
 * Every band labels three things: the count, its share of the first stage, and the conversion
 * from the band above. Showing only the share invites the reader to treat a 50% share as a 50%
 * conversion, which is a different (and usually better) number.
 */
export function FunnelChart({ stages, height = 300 }: FunnelChartProps) {
  if (stages.length === 0) {
    return <p className="text-secondary text-xs">没有可统计的投递。</p>;
  }
  const width = 480;
  const bandHeight = 1 / stages.length;
  const bars = funnelGeometry(stages, bandHeight);

  return (
    <div className="flex flex-col gap-3">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`投递漏斗：${stages.map((stage) => `${stage.label} ${stage.count}`).join('，')}`}
        className="h-[220px] w-full sm:h-[300px]"
        preserveAspectRatio="none"
      >
        {bars.map((bar) => {
          const stage = stages.find((candidate) => candidate.key === bar.key);
          const isEmpty = (stage?.count ?? 0) === 0;
          return (
            <path
              key={bar.key}
              d={funnelBandPath(bar, width, height)}
              data-stage={bar.key}
              data-empty={isEmpty ? 'true' : 'false'}
              className={isEmpty ? 'stroke-subtle fill-none' : 'fill-signal/25 stroke-signal/50'}
              strokeWidth={1}
            />
          );
        })}
      </svg>

      <ul className="flex flex-col gap-1.5">
        {stages.map((stage) => (
          <li key={stage.key} className="flex flex-wrap items-baseline gap-x-2 text-xs">
            <span className="text-primary w-16 font-medium">{stage.label}</span>
            <span className="text-primary font-mono tabular-nums">{stage.count}</span>
            <span className="text-tertiary">
              占比 {formatRate(stage.shareOfFirst, 0)} · 环比上一阶段{' '}
              {formatStepRate(stage.stepRate)}
            </span>
            <span className="text-tertiary w-full text-[11px] leading-relaxed">{stage.basis}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
