'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import type { CategoryPerformance, TimelineResponse } from '@careerforge/shared';

import {
  categoryLabel,
  formatCategoryScore,
  formatRate,
  peakBucketValue,
  shortMonth,
} from '@/lib/analytics-format';

interface CategoryTableProps {
  rows: CategoryPerformance[];
}

/** Performance by role family (FR-14.4). The category is derived from the postings' skills. */
export function CategoryTable({ rows }: CategoryTableProps) {
  if (rows.length === 0) {
    return (
      <Card className="min-w-0">
        <CardHeader>
          <CardTitle>岗位类别表现</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-secondary text-xs">还没有已投递的岗位，无法归类。</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>岗位类别表现</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">按岗位类别统计的投递、面试与 Offer</caption>
            <thead className="text-tertiary">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">
                  类别
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  投递
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  面试
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  Offer
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  面试率
                </th>
                <th scope="col" className="py-1 font-medium">
                  均分
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.category} className="border-subtle border-t">
                  <td className="text-primary py-2 pr-3 font-medium">
                    {categoryLabel(row.category)}
                    {!row.sufficient ? (
                      <Badge variant="outline" className="ml-2">
                        样本不足
                      </Badge>
                    ) : null}
                  </td>
                  <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                    {row.applications}
                  </td>
                  <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                    {row.interviews}
                  </td>
                  <td className="text-secondary py-2 pr-3 font-mono tabular-nums">{row.offers}</td>
                  <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                    {formatRate(row.interviewRate, 0)}
                  </td>
                  <td className="text-secondary py-2 font-mono tabular-nums">
                    {formatCategoryScore(row.averageMatchScore)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-tertiary text-[11px] leading-relaxed">
          类别由岗位要求技能的**技能词典分类加权**得出，不是人工标签；无法归类的投递记为
          「未分类」，不会被悄悄丢掉。
        </p>
      </CardContent>
    </Card>
  );
}

interface TimelinePanelProps {
  timeline: TimelineResponse;
}

/**
 * The activity trend and the milestone feed (FR-14.5).
 *
 * Bars per month rather than a line: applications, interviews and offers are discrete counts,
 * and a line implies continuity between months that the data does not have. Idle months are
 * kept — skipping them compresses three empty months into zero distance and makes the trend
 * look busier than it was.
 */
export function TimelinePanel({ timeline }: TimelinePanelProps) {
  const { buckets, entries, meta } = timeline;
  const peak = peakBucketValue(buckets);
  const window = buckets.slice(-12);

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>时间趋势与里程碑</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {peak === 0 ? (
          <p className="text-secondary text-xs">这个窗口内没有活动记录。</p>
        ) : (
          <div
            className="flex items-end gap-1.5 overflow-x-auto pb-1"
            role="img"
            aria-label="每月投递、面试、Offer 数量"
          >
            {window.map((bucket) => (
              <div key={bucket.month} className="flex w-10 shrink-0 flex-col items-center gap-1">
                <div className="flex h-24 w-full flex-col justify-end gap-0.5">
                  <span
                    className="bg-signal/70 w-full rounded-sm"
                    style={{ height: `${(bucket.offers / peak) * 100}%` }}
                    title={`${bucket.month} Offer ${bucket.offers}`}
                  />
                  <span
                    className="bg-signal/40 w-full rounded-sm"
                    style={{ height: `${(bucket.interviews / peak) * 100}%` }}
                    title={`${bucket.month} 面试 ${bucket.interviews}`}
                  />
                  <span
                    className="bg-subtle w-full rounded-sm"
                    style={{ height: `${(bucket.applications / peak) * 100}%` }}
                    title={`${bucket.month} 投递 ${bucket.applications}`}
                  />
                </div>
                <span className="text-tertiary font-mono text-[10px]">
                  {shortMonth(bucket.month)}
                </span>
              </div>
            ))}
          </div>
        )}
        <div className="text-tertiary flex flex-wrap gap-3 text-[11px]">
          <span>■ 投递</span>
          <span className="text-signal/50">■ 面试</span>
          <span className="text-signal">■ Offer</span>
        </div>

        {entries.length === 0 ? (
          <p className="text-secondary text-xs">没有里程碑记录。</p>
        ) : (
          <ol className="flex flex-col gap-2">
            {entries.slice(0, 8).map((entry) => (
              <li key={`${entry.occurredAt}-${entry.title}`} className="flex flex-col gap-0.5">
                <span className="text-primary text-xs">{entry.title}</span>
                <span className="text-tertiary font-mono text-[10px]">
                  {entry.occurredAt.slice(0, 10)} · {entry.kind}
                  {entry.status ? ` · ${entry.status}` : ''}
                </span>
              </li>
            ))}
          </ol>
        )}
        <p className="text-tertiary text-[11px] leading-relaxed">{meta.notes.join(' ')}</p>
      </CardContent>
    </Card>
  );
}
