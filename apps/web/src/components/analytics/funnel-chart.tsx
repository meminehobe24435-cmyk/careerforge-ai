'use client';

import type { FunnelStage } from '@careerforge/shared';

import {
  formatRate,
  formatStepRate,
  funnelBandPath,
  funnelGeometry,
  insufficientSampleNote,
  sampleIsSufficient,
  type SamplePolicy,
} from '@/lib/analytics-format';

interface FunnelChartProps {
  stages: FunnelStage[];
  /** The API's cohort policy, so an insufficient sample is stated neutrally instead of drawn. */
  sample?: SamplePolicy;
}

/** Rendered height of one band, in px. Every label row is the same height, so they line up. */
const BAND_HEIGHT = 56;
const VIEW_WIDTH = 1000;
const VIEW_BAND_HEIGHT = 100;

/**
 * The funnel, drawn as SVG with its stages labelled **beside** the bands.
 *
 * Five bands with one number each do not justify a chart library, and hand-drawn geometry makes the
 * honest cases obvious. Two of them are why this component was rebuilt:
 *
 * 1. **A funnel whose later stages are all zero.** Four zero-width bands inside a 300px box drew
 *    one full-width rectangle over four-fifths of empty chart — it read as a broken render, and the
 *    reader had to scroll to a list below to find out that nothing was wrong. Now every band has a
 *    faint full-width *slot*, its own label row beside it, and an empty stage is drawn as a dashed
 *    labelled gap ("0 · 没有卡片到达这一阶段") rather than as blank space.
 * 2. **Alignment.** The label column is a plain list of equal-height rows next to a chart drawn at
 *    `BAND_HEIGHT × stages.length`, so row *i* always sits against band *i*; nothing is positioned
 *    by a magic offset that a new stage count would invalidate.
 *
 * Each label states three things: the count, its share of the first stage, and the conversion from
 * the band above. Showing only the share invites the reader to treat a 50% share as a 50%
 * conversion, which is a different (and usually better) number.
 */
export function FunnelChart({ stages, sample }: FunnelChartProps) {
  if (stages.length === 0) {
    return <p className="text-secondary text-xs">没有可统计的投递。</p>;
  }

  const chartHeight = stages.length * BAND_HEIGHT;
  const bandHeight = 1 / stages.length;
  const bars = funnelGeometry(stages, bandHeight);
  const viewHeight = stages.length * VIEW_BAND_HEIGHT;
  const sampleNote = sample ? insufficientSampleNote(sample) : null;
  const sufficient = sample ? sampleIsSufficient(sample) : true;

  return (
    <div className="flex flex-col gap-3">
      {/*
        Neutral by construction: no danger colour, no arrow, no "declining" framing. An
        insufficient sample is an absence of evidence, and the panel's job is to say so once.
      */}
      {sampleNote ? (
        <p
          className="text-secondary bg-elevated border-subtle rounded-sm border px-2.5 py-2 text-[11px] leading-relaxed"
          data-sample-notice={sufficient ? 'sufficient' : 'insufficient'}
        >
          {sampleNote}
        </p>
      ) : null}

      <div className="grid grid-cols-[minmax(0,90px)_minmax(0,1fr)] gap-3 sm:grid-cols-[minmax(0,220px)_minmax(0,1fr)]">
        <svg
          viewBox={`0 0 ${VIEW_WIDTH} ${viewHeight}`}
          preserveAspectRatio="none"
          style={{ height: chartHeight }}
          className="w-full"
          role="img"
          aria-label={`投递漏斗：${stages.map((stage) => `${stage.label} ${stage.count}`).join('，')}`}
        >
          {/* The slots first, so the space around a narrow band reads as a track rather than as a
              chart that failed to draw. */}
          {bars.map((bar) => (
            <rect
              key={`slot-${bar.key}`}
              x={0}
              y={bar.offset * viewHeight}
              width={VIEW_WIDTH}
              height={bar.height * viewHeight}
              className="fill-subtle/20"
            />
          ))}
          {bars.map((bar) => (
            <path
              key={bar.key}
              d={funnelBandPath(bar, VIEW_WIDTH, viewHeight)}
              data-stage={bar.key}
              data-empty={bar.empty ? 'true' : 'false'}
              className={bar.empty ? 'stroke-subtle fill-none' : 'fill-signal/25 stroke-signal/50'}
              strokeWidth={1}
            />
          ))}
          {/* One dashed rule per empty stage: the gap is labelled by the row beside it. */}
          {bars
            .filter((bar) => bar.empty)
            .map((bar) => {
              const y = (bar.offset + bar.height / 2) * viewHeight;
              return (
                <line
                  key={`gap-${bar.key}`}
                  x1={VIEW_WIDTH * 0.35}
                  y1={y}
                  x2={VIEW_WIDTH * 0.65}
                  y2={y}
                  className="stroke-subtle"
                  strokeWidth={1}
                  strokeDasharray="6 6"
                  vectorEffect="non-scaling-stroke"
                  data-gap={bar.key}
                />
              );
            })}
        </svg>

        <ul className="flex flex-col" style={{ height: chartHeight }}>
          {stages.map((stage) => (
            <li
              key={stage.key}
              data-stage-label={stage.key}
              style={{ height: BAND_HEIGHT }}
              className="flex flex-col justify-center gap-0.5"
            >
              <span className="flex flex-wrap items-baseline gap-x-2 text-xs">
                <span className="text-primary font-medium">{stage.label}</span>
                <span className="text-primary font-mono tabular-nums">{stage.count}</span>
              </span>
              <span className="text-tertiary text-[11px]">
                {stage.count === 0
                  ? '没有卡片到达这一阶段'
                  : `占比 ${formatRate(stage.shareOfFirst, 0)} · 环比上一阶段 ${formatStepRate(stage.stepRate)}`}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <ul className="flex flex-col gap-1.5 text-[11px]">
        {stages.map((stage) => (
          <li key={stage.key} className="text-tertiary flex flex-wrap gap-x-2 leading-relaxed">
            <span className="text-secondary font-mono">{stage.label}</span>
            <span>{stage.basis}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
