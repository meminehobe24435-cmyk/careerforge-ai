'use client';

import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CodeBlock,
  Skeleton,
} from '@careerforge/ui';
import { Database, XCircle } from 'lucide-react';

import { useAiRun } from '@/hooks/use-observability';
import {
  formatCount,
  formatDuration,
  formatInstant,
  formatLatency,
  formatUsd,
  shortDigest,
  statusBadge,
} from '@/lib/observability-format';

interface RunDetailPanelProps {
  runId: string;
}

/**
 * The row's drill-down: the workflow's step chain, then the model calls the run made.
 *
 * They are two different granularities and the panel keeps them apart on purpose — a step can make
 * two calls, and a call can happen outside a step — so a reader who wants to know "which step was
 * slow" and one who wants to know "what did the model actually cost" both get an answer without
 * averaging the two together.
 *
 * Digests, not payloads: the trace says *what* was sent (so two runs can be compared) without
 * copying résumé or JD text into an ops table.
 */
export function RunDetailPanel({ runId }: RunDetailPanelProps) {
  const detail = useAiRun(runId);

  if (detail.isPending) {
    return (
      <div className="flex flex-col gap-2 p-4">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-24" />
      </div>
    );
  }

  if (detail.isError || !detail.data) {
    return (
      <div className="flex flex-col gap-1 p-4">
        <p className="text-danger flex items-center gap-1.5 text-xs">
          <XCircle className="size-3.5" aria-hidden="true" />
          运行详情加载失败 —— 这一行本身是存在的，只是详情没取到。
        </p>
        <p className="text-tertiary font-mono text-[11px]">GET /ai-runs/{runId}</p>
      </div>
    );
  }

  const run = detail.data;
  const calls = run.calls;

  return (
    <div className="flex flex-col gap-4 p-4">
      <section aria-label="步骤链" className="flex flex-col gap-2">
        <h4 className="text-secondary text-xs font-medium">
          步骤链（{run.steps.length} 步，来自执行器的 trace）
        </h4>
        {run.steps.length === 0 ? (
          <p className="text-tertiary text-[11px]">
            这次运行没有记录步骤 —— workflow 的每一步都会写
            trace，为空说明运行在进入第一步前就结束了。
          </p>
        ) : (
          <ol className="flex flex-col gap-1.5">
            {run.steps.map((step, index) => {
              const badge = statusBadge(step.status);
              return (
                <li
                  key={`${step.name}-${index}`}
                  data-step={step.name}
                  className="border-subtle bg-elevated flex flex-wrap items-center gap-2 rounded-sm border px-2.5 py-1.5 text-xs"
                >
                  <span className="text-tertiary font-mono text-[11px] tabular-nums">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="text-primary font-mono">{step.name}</span>
                  <Badge variant={badge.variant}>{badge.label}</Badge>
                  <span className="text-secondary font-mono tabular-nums">
                    {formatLatency(step.latencyMs)}
                  </span>
                  {step.tokens > 0 ? (
                    <span className="text-secondary font-mono tabular-nums">
                      {formatCount(step.tokens)} tok
                    </span>
                  ) : null}
                  {step.attempts > 1 ? (
                    <Badge variant="weak">重试 {step.attempts - 1} 次</Badge>
                  ) : null}
                  {step.cacheHit ? <Badge variant="signal">缓存</Badge> : null}
                  <span className="text-tertiary font-mono text-[10px]">
                    in {shortDigest(step.inputDigest)} → out {shortDigest(step.outputDigest)}
                  </span>
                  {step.errorCode ? (
                    <span className="text-danger font-mono text-[11px]">{step.errorCode}</span>
                  ) : null}
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <section aria-label="模型调用" className="flex flex-col gap-2">
        <h4 className="text-secondary flex items-center gap-1.5 text-xs font-medium">
          <Database className="size-3.5" aria-hidden="true" />
          模型调用（{calls.length} 次，来自 metered provider 的 llm_calls）
        </h4>
        {calls.length === 0 ? (
          <p className="text-tertiary text-[11px] leading-relaxed">
            这次运行没有产生模型调用记录。零 Key 的启发式路径走本地规则，不调用任何模型 ——
            这是部署事实，不是埋点缺失。
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <caption className="sr-only">
                本次运行的模型调用：操作、provider、token、耗时与成本
              </caption>
              <thead className="text-tertiary">
                <tr>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    操作
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Provider / Model
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    Token
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    耗时
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    成本
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    时间 (UTC)
                  </th>
                </tr>
              </thead>
              <tbody>
                {calls.map((call) => (
                  <tr key={call.id} className="border-subtle border-t">
                    <td className="text-primary py-1.5 pr-3 font-mono">{call.operation}</td>
                    <td className="text-secondary py-1.5 pr-3 font-mono">
                      {call.provider}
                      {call.model ? ` · ${call.model}` : ''}
                    </td>
                    <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                      {formatCount(call.totalTokens)}
                    </td>
                    <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                      {formatLatency(call.latencyMs)}
                    </td>
                    <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                      {formatUsd(call.costUsd)}
                    </td>
                    <td className="text-tertiary py-1.5 font-mono tabular-nums">
                      {formatInstant(call.createdAt)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="flex flex-wrap items-start gap-3">
        <Card className="min-w-0 flex-1">
          <CardHeader>
            <CardTitle className="text-xs">输入 / 输出引用（摘要，不是原文）</CardTitle>
          </CardHeader>
          <CardContent className="text-[11px]">
            <dl className="text-tertiary flex flex-wrap gap-x-4 gap-y-1 font-mono">
              {Object.entries({ ...run.inputRef, ...run.outputRef }).length === 0 ? (
                <p>这次运行没有记录输入输出引用。</p>
              ) : (
                Object.entries({ ...run.inputRef, ...run.outputRef }).map(([key, value]) => (
                  <div key={key} className="flex gap-1.5">
                    <dt className="text-secondary">{key}</dt>
                    <dd className="truncate">{String(value)}</dd>
                  </div>
                ))
              )}
            </dl>
          </CardContent>
        </Card>

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="text-xs">运行窗口</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1 text-[11px]">
            <span className="text-secondary font-mono tabular-nums">
              开始 {formatInstant(run.startedAt)}
            </span>
            <span className="text-secondary font-mono tabular-nums">
              结束 {formatInstant(run.finishedAt)}
            </span>
            <span className="text-tertiary font-mono tabular-nums">
              墙钟 {formatDuration(run.startedAt, run.finishedAt)} · provider 自报{' '}
              {formatLatency(run.latencyMs)}
            </span>
          </CardContent>
        </Card>
      </div>

      {run.requestId ? (
        <CodeBlock
          filename="requestId"
          code={run.requestId}
          language="txt"
          maxHeight={40}
          className="max-w-md"
        />
      ) : null}

      {run.error ? (
        <p className="text-danger font-mono text-[11px] leading-relaxed">错误：{run.error}</p>
      ) : null}
    </div>
  );
}
