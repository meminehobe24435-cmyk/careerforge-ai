'use client';

import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CodeBlock,
  EmptyState,
  ErrorState,
  Skeleton,
} from '@careerforge/ui';
import { ANALYTICS_RANGES, isApiError, type AnalyticsRange } from '@careerforge/shared';
import { Activity, RefreshCw } from 'lucide-react';

import { CategoryTable, TimelinePanel } from '@/components/analytics/category-and-timeline';
import { CorrelationTable } from '@/components/analytics/correlation-table';
import { FunnelChart } from '@/components/analytics/funnel-chart';
import { RateCards } from '@/components/analytics/rate-cards';
import { useAnalytics } from '@/hooks/use-analytics';
import { API_BASE_URL } from '@/lib/api';
import { RANGE_LABELS } from '@/lib/analytics-format';

/**
 * `/app/analytics` (PRD FR-14).
 *
 * The page is built around one idea: **the window is part of every number**. So the range
 * switcher is at the top, the active window is repeated in the header, and each panel's own
 * notes travel with it — a funnel screenshot without its range is a number nobody can check.
 */
export function AnalyticsView() {
  const [range, setRange] = useState<AnalyticsRange>('30d');
  const analytics = useAnalytics(range);
  const { funnel, rates, correlation, categories, timeline } = analytics;

  if (analytics.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-56" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <Skeleton key={index} className="h-32" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  if (analytics.error || !funnel.data || !rates.data || !timeline.data) {
    const apiError = isApiError(analytics.error) ? analytics.error : null;
    return (
      <div className="flex flex-col gap-5">
        <Header
          range={range}
          onRangeChange={setRange}
          onRefresh={analytics.refetch}
          refreshing={analytics.isFetching}
        />
        <ErrorState
          title={apiError?.isNetworkError ? 'Backend not reachable' : '分析加载失败'}
          error={analytics.error}
          code={apiError?.code ?? 'UNKNOWN'}
          requestId={apiError?.requestId ?? null}
          onRetry={analytics.refetch}
          retrying={analytics.isFetching}
          statusHref="/system"
          details={
            <CodeBlock filename="API base URL" code={API_BASE_URL} language="txt" maxHeight={64} />
          }
        />
      </div>
    );
  }

  const meta = funnel.data.meta;
  const empty = meta.cohortSize === 0;

  return (
    <div className="flex flex-col gap-5">
      <Header
        range={range}
        onRangeChange={setRange}
        onRefresh={analytics.refetch}
        refreshing={analytics.isFetching}
        cohortSize={meta.cohortSize}
      />

      {empty ? (
        <EmptyState
          icon={<Activity className="size-5" />}
          title="这个窗口内没有投递"
          description="漏斗、比率与相关性都建立在投递记录上。先在投递看板加入几个岗位（或换一个更大的时间窗口），这里就会有数据。"
          hint={`GET /analytics/funnel?range=${range} → cohortSize 0`}
        />
      ) : null}

      <section aria-labelledby="analytics-rates-heading" className="flex flex-col gap-3">
        <h2 id="analytics-rates-heading" className="sr-only">
          核心比率
        </h2>
        <RateCards cards={rates.data.cards} meta={rates.data.meta} />
      </section>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>投递漏斗</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <FunnelChart stages={funnel.data.stages} />
            <p className="text-tertiary text-[11px] leading-relaxed">{meta.notes.join(' ')}</p>
          </CardContent>
        </Card>

        <TimelinePanel timeline={timeline.data} />
      </div>

      <CorrelationTable rows={correlation.data ?? []} />
      <CategoryTable rows={categories.data ?? []} />
    </div>
  );
}

interface HeaderProps {
  range: AnalyticsRange;
  onRangeChange: (range: AnalyticsRange) => void;
  onRefresh: () => void;
  refreshing: boolean;
  cohortSize?: number;
}

function Header({ range, onRangeChange, onRefresh, refreshing, cohortSize }: HeaderProps) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-primary text-lg font-semibold tracking-tight">求职分析</h1>
        <p className="text-tertiary font-mono text-[11px]">
          GET {API_BASE_URL}/analytics/funnel?range={range}
          {typeof cohortSize === 'number' ? ` · 同期群 ${cohortSize} 张卡片` : ''}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="时间窗口" className="flex items-center gap-1">
          {ANALYTICS_RANGES.map((value) => (
            <Button
              key={value}
              size="sm"
              variant={value === range ? 'secondary' : 'ghost'}
              aria-pressed={value === range}
              onClick={() => onRangeChange(value)}
            >
              {RANGE_LABELS[value]}
            </Button>
          ))}
        </div>
        <Badge variant="outline">漏斗按事件流统计</Badge>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          loading={refreshing}
          aria-label="刷新分析数据"
        >
          <RefreshCw className="size-3.5" aria-hidden="true" />
          刷新
        </Button>
      </div>
    </header>
  );
}
