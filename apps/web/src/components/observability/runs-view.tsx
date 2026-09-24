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
  Input,
  Skeleton,
} from '@careerforge/ui';
import { isApiError, type AiRunFilters, type AiRunStatus } from '@careerforge/shared';
import { Radar, RefreshCw, SlidersHorizontal } from 'lucide-react';

import { RunTable } from '@/components/observability/run-table';
import { useAiRuns } from '@/hooks/use-observability';
import { API_BASE_URL } from '@/lib/api';
import {
  RUN_STATUS_FILTERS,
  SINCE_HOUR_FILTERS,
  formatCount,
  formatUsd,
} from '@/lib/observability-format';

/**
 * `/app/ai-runs` (PRD FR-15.1, docs/UI.md §5.15).
 *
 * The page answers three questions and refuses to answer a fourth:
 *
 * 1. *what ran?* — every traced operation, newest first, with the request's own filters;
 * 2. *what did it cost?* — tokens, latency and money as the provider reported them;
 * 3. *where did it go wrong?* — status, attempts and error codes on the opened row;
 * 4. ~~*was it accurate?*~~ — that is the eval suite's job (`reports/eval-report.json`), and
 *    presenting a run as "good" here would be inventing a metric this data cannot produce.
 */
export function AiRunsView() {
  const [status, setStatus] = useState<AiRunStatus | 'all'>('all');
  const [sinceHours, setSinceHours] = useState<number | null>(null);
  const [workflow, setWorkflow] = useState('');
  const [agent, setAgent] = useState('');

  const filters: AiRunFilters = {
    ...(status === 'all' ? {} : { status }),
    ...(sinceHours === null ? {} : { sinceHours }),
    ...(workflow.trim() ? { workflow: workflow.trim() } : {}),
    ...(agent.trim() ? { agent: agent.trim() } : {}),
    limit: 50,
  };

  const runs = useAiRuns(filters);

  if (runs.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-80" />
      </div>
    );
  }

  const apiError = isApiError(runs.error) ? runs.error : null;
  const data = runs.data;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-primary text-lg font-semibold tracking-tight">AI 运行记录</h1>
          <p className="text-tertiary font-mono text-[11px]">
            GET {API_BASE_URL}/ai-runs · {formatCount(data?.total ?? 0)} 条运行
            {data ? `（本次返回 ${data.items.length} 条）` : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">读取 agent_runs / llm_calls</Badge>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void runs.refetch()}
            loading={runs.isFetching}
            aria-label="刷新运行记录"
          >
            <RefreshCw className="size-3.5" aria-hidden="true" />
            刷新
          </Button>
        </div>
      </header>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-1.5 text-xs">
            <SlidersHorizontal className="size-3.5" aria-hidden="true" />
            筛选
          </CardTitle>
          {runs.isFetching ? <Badge variant="signal">读取中</Badge> : null}
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div role="group" aria-label="状态" className="flex flex-wrap items-center gap-1">
            {RUN_STATUS_FILTERS.map((option) => (
              <Button
                key={option.value}
                size="sm"
                variant={option.value === status ? 'secondary' : 'ghost'}
                aria-pressed={option.value === status}
                onClick={() => setStatus(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
          <div role="group" aria-label="时间范围" className="flex flex-wrap items-center gap-1">
            {SINCE_HOUR_FILTERS.map((option) => (
              <Button
                key={String(option.value)}
                size="sm"
                variant={option.value === sinceHours ? 'secondary' : 'ghost'}
                aria-pressed={option.value === sinceHours}
                onClick={() => setSinceHours(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
          <label className="flex flex-col gap-1">
            <span className="text-tertiary text-[11px]">Workflow</span>
            <Input
              value={workflow}
              onChange={(event) => setWorkflow(event.target.value)}
              placeholder="例如 jd_analysis"
              aria-label="按 workflow 过滤"
              className="w-44"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-tertiary text-[11px]">Agent</span>
            <Input
              value={agent}
              onChange={(event) => setAgent(event.target.value)}
              placeholder="例如 job"
              aria-label="按 agent 过滤"
              className="w-36"
            />
          </label>
        </CardContent>
      </Card>

      {runs.isError ? (
        <ErrorState
          title={apiError?.isNetworkError ? 'Backend not reachable' : '运行记录加载失败'}
          error={runs.error}
          code={apiError?.code ?? 'UNKNOWN'}
          requestId={apiError?.requestId ?? null}
          onRetry={() => void runs.refetch()}
          retrying={runs.isFetching}
          statusHref="/system"
          details={
            <CodeBlock filename="API base URL" code={API_BASE_URL} language="txt" maxHeight={64} />
          }
        />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>运行记录</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {data && data.total === 0 ? (
            <EmptyState
              icon={<Radar className="size-5" />}
              title="还没有被追踪的 AI 运行"
              description="每次 AI 操作都会写一条 agent_runs：分析一段 JD、做一次匹配、跑一轮模拟面试。先用一次功能，这里就会有记录。"
              hint="GET /ai-runs → total 0"
            />
          ) : null}
          <RunTable runs={data?.items ?? []} />
        </CardContent>
      </Card>

      {data && data.items.length > 0 ? (
        <p className="text-tertiary text-[11px] leading-relaxed">
          本页返回的最新 {data.items.length} 条运行合计花费{' '}
          {formatUsd(data.items.reduce((sum, run) => sum + run.costUsd, 0))}
          。窗口化的成本汇总在{' '}
          <a href="/app/costs" className="text-signal underline underline-offset-2">
            成本看板
          </a>
          ，那里按天、按 agent、按功能分组，并给出缓存命中率。
        </p>
      ) : null}
    </div>
  );
}
