'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import type { DailyCost, ObservabilityRange } from '@careerforge/shared';

import { activityWindowNote, formatCount, formatUsd, latestDay } from '@/lib/observability-format';

interface DailyCostChartProps {
  days: DailyCost[];
  range: ObservabilityRange | (string & {});
  /** Runs in the window whose usage was never reported — their days are `0` for want of a number. */
  unaccountedRuns?: number;
}

const WIDTH = 320;
const HEIGHT = 110;
const PAD = 8;

/**
 * Daily spend, as a line with a point per day that had activity.
 *
 * A line rather than bars (docs/UI.md §5.15 asks for 折线) with one honest caveat printed under it:
 * **the API only returns days that had runs**, so a gap between two points means "no runs that
 * day", not "zero cost interpolated across the window". The caption states it and the table below
 * lists the raw rows, because a chart nobody can check against its data is decoration.
 *
 * When nothing was spent the chart is not drawn as a flat line at zero: a flat line looks like a
 * measurement, and the truth is that there is nothing to measure.
 */
export function DailyCostChart({ days, range, unaccountedRuns = 0 }: DailyCostChartProps) {
  const note = activityWindowNote(days, range);
  const total = days.reduce((sum, day) => sum + day.costUsd, 0);
  const peak = days.reduce((max, day) => Math.max(max, day.costUsd), 0);
  // `0` here is two different facts, and the sentence below has to pick the right one: a zero-key
  // provider really spends nothing, while an unreported run's `0` is a hole the day-sum closed.
  const floorNote =
    unaccountedRuns > 0
      ? `其中 ${unaccountedRuns} 次运行的用量未被 provider 上报，接口的按日合计把它们的 null 当作 0 —— 因此这些天的成本是下限。`
      : null;

  if (days.length === 0 || peak === 0) {
    return (
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>每日成本</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <p className="text-secondary text-xs leading-relaxed">
            {days.length === 0
              ? '这个窗口内没有运行记录，因此没有成本曲线可画。'
              : unaccountedRuns > 0
                ? '这个窗口内的运行成本都是 0 —— 但其中一部分运行的用量并未被 provider 上报，因此这里没有可画的曲线，而不是「花费为 0」。'
                : '这个窗口内的运行成本都是 0：零 Key 启发式 provider 不产生费用，延迟与调用次数仍然被记录。'}
          </p>
          {note ? <p className="text-tertiary text-[11px]">{note}</p> : null}
          {floorNote ? <p className="text-weak text-[11px]">{floorNote}</p> : null}
        </CardContent>
      </Card>
    );
  }

  const points = days.map((day, index) => {
    const x = days.length === 1 ? WIDTH / 2 : PAD + (index * (WIDTH - PAD * 2)) / (days.length - 1);
    const y = HEIGHT - PAD - (day.costUsd / peak) * (HEIGHT - PAD * 2);
    return { day, x, y };
  });
  const path = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ');
  const newest = latestDay(days);
  const first = days[0] as DailyCost;

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>每日成本</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          preserveAspectRatio="none"
          className="h-28 w-full"
          role="img"
          aria-label={`每日成本折线：${first.day} 至 ${newest?.day ?? first.day}，峰值 ${formatUsd(peak)}，合计 ${formatUsd(total)}`}
        >
          <line
            x1={PAD}
            y1={HEIGHT - PAD}
            x2={WIDTH - PAD}
            y2={HEIGHT - PAD}
            className="stroke-subtle"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
          <path
            d={path}
            fill="none"
            className="stroke-signal"
            strokeWidth={1.5}
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
          {points.map((point) => (
            <circle
              key={point.day.day}
              cx={point.x}
              cy={point.y}
              r={2}
              className="fill-signal"
              vectorEffect="non-scaling-stroke"
            >
              <title>{`${point.day.day} 成本 ${formatUsd(point.day.costUsd)}，${point.day.runs} 次运行`}</title>
            </circle>
          ))}
        </svg>

        <p className="text-tertiary text-[11px] leading-relaxed">
          峰值 {formatUsd(peak)}（
          {
            points.reduce((best, point) => (point.day.costUsd > best.day.costUsd ? point : best))
              .day.day
          }
          ） ，合计 {formatUsd(total)}。{note ?? '窗口为全部历史，只显示有运行记录的日期。'}
        </p>
        {floorNote ? <p className="text-weak text-[11px] leading-relaxed">{floorNote}</p> : null}

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">每日成本明细：日期、运行次数、token 与成本</caption>
            <thead className="text-tertiary">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">
                  日期 (UTC)
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  运行
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Tokens
                </th>
                <th scope="col" className="py-1 font-medium">
                  成本
                </th>
              </tr>
            </thead>
            <tbody>
              {days.map((day) => (
                <tr key={day.day} className="border-subtle border-t" data-day={day.day}>
                  <td className="text-secondary py-1 pr-3 font-mono tabular-nums">{day.day}</td>
                  <td className="text-secondary py-1 pr-3 font-mono tabular-nums">{day.runs}</td>
                  <td className="text-secondary py-1 pr-3 font-mono tabular-nums">
                    {formatCount(day.tokens)}
                  </td>
                  <td className="text-secondary py-1 font-mono tabular-nums">
                    {formatUsd(day.costUsd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
