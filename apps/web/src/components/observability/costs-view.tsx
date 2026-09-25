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
  ErrorState,
  Skeleton,
} from '@careerforge/ui';
import {
  OBSERVABILITY_RANGES,
  isApiError,
  type DailyCost,
  type ObservabilityRange,
} from '@careerforge/shared';
import { Gauge, RefreshCw } from 'lucide-react';

import { CachePanel, PromptPanel } from '@/components/observability/cache-and-prompts';
import { AgentCostPanel, FeatureCostPanel } from '@/components/observability/cost-breakdown';
import { DailyCostChart } from '@/components/observability/daily-cost-chart';
import { useCosts } from '@/hooks/use-observability';
import { API_BASE_URL } from '@/lib/api';
import {
  USAGE_STATUS_GLOSSARY,
  budgetUsage,
  formatCny,
  formatCount,
  formatLatency,
  formatUsd,
  latestDay,
  unaccountedSummary,
} from '@/lib/observability-format';

const RANGE_LABELS: Record<ObservabilityRange, string> = {
  '7d': '7 天',
  '30d': '30 天',
  '90d': '90 天',
  all: '全部',
};

/**
 * `/app/costs` (PRD FR-15.2, docs/UI.md §5.15).
 *
 * Ordered by the question a reader arrives with: *what did this cost* (totals), *am I near a
 * ceiling* (the budget guard), *when* (daily), *what* (per agent / per feature), *was anything
 * reused* (cache), and finally *which prompt produced these numbers* (registry).
 *
 * What the page will not do is convert tokens into money it was not told about. When the deployment
 * runs the zero-key heuristic provider the honest answer really is "$0.0000 spent and 0 tokens", and
 * the API's `notes` travel with the numbers so the reader knows why.
 *
 * **The one word that changes with the data.** `totals` is a `SUM`, and `SUM` skips the runs whose
 * usage was never reported (`NULL`, PHASE 13). So while `unaccountedRuns` is 0 the headline is a
 * *Total cost*; the moment it is not, the same number becomes a *Known cost* — a floor — and
 * `unaccountedRuns` gets its own card instead of a footnote. A page that kept saying "Total" over a
 * SUM with holes in it would be reporting a plausible number rather than a true one.
 */
export function CostsView() {
  const [range, setRange] = useState<ObservabilityRange>('7d');
  const costs = useCosts(range);

  if (costs.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-56" />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28" />
          ))}
        </div>
        <Skeleton className="h-64" />
      </div>
    );
  }

  const apiError = isApiError(costs.error) ? costs.error : null;
  const summary = costs.costs.data;
  const unaccounted = summary?.unaccountedRuns ?? 0;
  const floorNote = summary ? unaccountedSummary(unaccounted) : null;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-primary text-lg font-semibold tracking-tight">AI 成本</h1>
          <p className="text-tertiary font-mono text-[11px]">
            GET {API_BASE_URL}/ai-costs?range={range}
            {summary ? ` · ${formatCount(summary.totals.runs)} 条运行` : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label="时间窗口" className="flex items-center gap-1">
            {OBSERVABILITY_RANGES.map((value) => (
              <Button
                key={value}
                size="sm"
                variant={value === range ? 'secondary' : 'ghost'}
                aria-pressed={value === range}
                onClick={() => setRange(value)}
              >
                {RANGE_LABELS[value]}
              </Button>
            ))}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={costs.refetch}
            loading={costs.isFetching}
            aria-label="刷新成本数据"
          >
            <RefreshCw className="size-3.5" aria-hidden="true" />
            刷新
          </Button>
        </div>
      </header>

      {costs.error || !summary ? (
        <ErrorState
          title={apiError?.isNetworkError ? 'Backend not reachable' : '成本数据加载失败'}
          error={costs.error}
          code={apiError?.code ?? 'UNKNOWN'}
          requestId={apiError?.requestId ?? null}
          onRetry={costs.refetch}
          retrying={costs.isFetching}
          statusHref="/system"
          details={
            <CodeBlock filename="API base URL" code={API_BASE_URL} language="txt" maxHeight={64} />
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
            <TotalCard
              label={unaccounted > 0 ? 'Known cost（USD）' : 'Total cost（USD）'}
              value={formatUsd(summary.totals.costUsd)}
              hint={
                unaccounted > 0
                  ? `约 ${formatCny(summary.totals.costCny)} · 已知下限，不含 ${formatCount(unaccounted)} 次未上报用量的运行`
                  : `约 ${formatCny(summary.totals.costCny)} · 窗口 ${RANGE_LABELS[range]}`
              }
            />
            <TotalCard
              label="Token"
              value={formatCount(summary.totals.tokens)}
              hint="provider 自报用量，未经推算；未上报的运行不计入"
            />
            <TotalCard
              label="运行 / 模型调用"
              value={`${formatCount(summary.totals.runs)} / ${formatCount(summary.totals.modelCalls)}`}
              hint="运行次数与真正发出的模型请求数不同"
            />
            <TotalCard
              label="累计延迟"
              value={formatLatency(summary.totals.latencyMs)}
              hint="所有运行自报延迟之和，不是平均"
            />
            {/*
              Its own card rather than a footnote: "the total is a floor" is only actionable if the
              reader can see how many runs are missing from it.
            */}
            <TotalCard
              label="Unaccounted runs"
              value={formatCount(unaccounted)}
              hint={
                unaccounted > 0
                  ? '这些运行的用量未被 provider 上报（usageStatus=unavailable/legacy），token 与成本为 null 而非 0'
                  : '窗口内每次运行的用量都有来源：没有 null 计数被当成 0 计入合计'
              }
            />
          </div>

          <UsageStatusGlossary />

          <BudgetCard
            range={range}
            dailyBudgetUsd={summary.dailyBudgetUsd}
            latest={latestDay(summary.days)}
          />

          <DailyCostChart days={summary.days} range={range} unaccountedRuns={unaccounted} />

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <AgentCostPanel rows={costs.byAgent.data ?? []} unaccountedRuns={unaccounted} />
            <FeatureCostPanel rows={costs.byFeature.data ?? []} unaccountedRuns={unaccounted} />
          </div>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <CachePanel stats={costs.cache.data} />
            <PromptPanel prompts={costs.prompts.data ?? []} />
          </div>

          {floorNote ? (
            <p className="text-weak text-[11px] leading-relaxed" data-unaccounted-note>
              {floorNote}
            </p>
          ) : null}

          {summary.notes.length > 0 ? (
            <p className="text-tertiary text-[11px] leading-relaxed">{summary.notes.join(' ')}</p>
          ) : null}
        </>
      )}
    </div>
  );
}

/**
 * The five usage states, once, in secondary text.
 *
 * On a page made of `SUM`s this is the only thing that can tell a reader whether a `0` is a measured
 * zero or the absence of a measurement. It is a one-line glossary rather than a badge on every
 * figure: the vocabulary is small, fixed, and belongs to the API — repeating it eight times would
 * turn a caveat into decoration.
 */
function UsageStatusGlossary() {
  return (
    <p className="text-tertiary text-[11px] leading-relaxed" data-usage-glossary>
      用量状态（usageStatus）：
      {USAGE_STATUS_GLOSSARY.map((entry) => `${entry.label} = ${entry.detail}`).join(' ')}
    </p>
  );
}

function TotalCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Card className="min-w-0" data-total={label}>
      <CardHeader>
        <CardTitle className="text-tertiary text-[11px] font-medium uppercase tracking-wide">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        <span className="text-primary font-mono text-xl tabular-nums">{value}</span>
        <span className="text-tertiary text-[11px] leading-snug">{hint}</span>
      </CardContent>
    </Card>
  );
}

interface BudgetCardProps {
  range: ObservabilityRange;
  dailyBudgetUsd: number;
  latest: DailyCost | null;
}

/**
 * The guard rail: the newest recorded day's spend against `AI_DAILY_BUDGET_USD`.
 *
 * The comparison is made against **the newest day the API reported, and the date is printed**, not
 * against the browser's idea of "today". The backend buckets runs by `date(started_at)` on a
 * UTC clock, so a reader in UTC+8 before 08:00 would otherwise be shown yesterday's spend as
 * today's — a wrong number is worse than a slightly stale label. The `RoutedProvider` raises
 * `BudgetExceededError` on exhaustion and the resilience layer degrades to the next provider, so
 * this card describes a real ceiling and not a decorative progress bar (ADR-009).
 */
function BudgetCard({ range, dailyBudgetUsd, latest }: BudgetCardProps) {
  const usage = budgetUsage(latest, dailyBudgetUsd);
  const percent = usage.ratio === null ? null : Math.round(usage.ratio * 100);

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <Gauge className="size-3.5" aria-hidden="true" />
          日预算护栏
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-primary font-mono text-sm tabular-nums">{usage.label}</span>
          {usage.exceeded ? (
            <Badge variant="danger">已超出上限</Badge>
          ) : percent === null ? (
            <Badge variant="outline">无上限</Badge>
          ) : (
            <Badge variant="signal">{percent}%</Badge>
          )}
          {latest ? (
            <span className="text-tertiary font-mono text-[11px]">
              最近记录日 {latest.day}（UTC）
            </span>
          ) : (
            <span className="text-tertiary font-mono text-[11px]">
              窗口 {RANGE_LABELS[range]} 内没有运行记录
            </span>
          )}
        </div>
        <span
          className="border-subtle bg-elevated relative block h-2 w-full overflow-hidden rounded-sm border"
          role="img"
          aria-label={usage.label}
        >
          <span
            className={
              usage.exceeded
                ? 'bg-danger absolute inset-y-0 left-0'
                : 'bg-signal absolute inset-y-0 left-0'
            }
            style={{ width: `${percent ?? 0}%` }}
            data-budget-used={percent === null ? 'null' : percent}
          />
        </span>
        <p className="text-tertiary text-[11px] leading-relaxed">
          超限时路由层抛出 BudgetExceededError，ResilientProvider 会降级到下一个 provider 而不是返回
          500 —— 因此护栏触发表现为 status=degraded 的运行，可在{' '}
          <a href="/app/ai-runs" className="text-signal underline underline-offset-2">
            AI 运行记录
          </a>{' '}
          里筛选出来。
        </p>
      </CardContent>
    </Card>
  );
}
