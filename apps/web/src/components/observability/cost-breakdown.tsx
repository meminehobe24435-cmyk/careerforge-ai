'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import type { CostByAgent, CostByFeature } from '@careerforge/shared';

import { costShares, formatCount, formatLatency, formatUsd } from '@/lib/observability-format';

interface AgentCostPanelProps {
  rows: CostByAgent[];
}

/**
 * Cost per agent, as horizontal bars plus the numbers.
 *
 * docs/UI.md §5.15 asks for 堆叠柱 (stacked columns) here; this renders **one bar per agent** and
 * the deviation is deliberate and recorded in UI.md: stacking needs a second dimension to stack
 * over (day), and with a handful of agents and a young deployment those columns would be one
 * segment tall each — a bar chart with extra ink. The table beside every bar carries the fields a
 * stacked column would have encoded (cache hits, average latency), which is what a reader actually
 * compares.
 */
export function AgentCostPanel({ rows }: AgentCostPanelProps) {
  const { rows: shares, total } = costShares(
    rows.map((row) => ({ key: row.agent, label: row.agent, value: row.costUsd })),
  );

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>每个 Agent 的花费</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {shares.length === 0 ? (
          <p className="text-secondary text-xs leading-relaxed">
            这个窗口内没有可归因的 agent 花费。
          </p>
        ) : (
          <>
            <p className="text-tertiary text-[11px] leading-relaxed">
              合计 {formatUsd(total)}。占比以本窗口内所有 agent 的花费为分母。
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <caption className="sr-only">
                  每个 agent 的运行次数、token、成本、平均耗时与缓存命中
                </caption>
                <thead className="text-tertiary">
                  <tr>
                    <th scope="col" className="py-1 pr-3 font-medium">
                      Agent
                    </th>
                    <th scope="col" className="py-1 pr-3 font-medium">
                      占比
                    </th>
                    <th scope="col" className="py-1 pr-3 font-medium">
                      运行
                    </th>
                    <th scope="col" className="py-1 pr-3 font-medium">
                      Tokens
                    </th>
                    <th scope="col" className="py-1 pr-3 font-medium">
                      成本
                    </th>
                    <th scope="col" className="py-1 pr-3 font-medium">
                      平均耗时
                    </th>
                    <th scope="col" className="py-1 font-medium">
                      缓存命中
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {shares.map((share, index) => {
                    const row = rows[index] as CostByAgent;
                    return (
                      <tr key={share.key} className="border-subtle border-t" data-agent={share.key}>
                        <td className="text-primary py-1.5 pr-3 font-mono">{share.label}</td>
                        <td className="py-1.5 pr-3">
                          <span className="border-subtle bg-elevated relative block h-2 w-24 overflow-hidden rounded-sm border">
                            <span
                              className="bg-signal absolute inset-y-0 left-0"
                              style={{ width: `${Math.round(share.share * 100)}%` }}
                            />
                          </span>
                          <span className="text-tertiary font-mono text-[10px] tabular-nums">
                            {(share.share * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                          {row.runs}
                        </td>
                        <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                          {formatCount(row.tokens)}
                        </td>
                        <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                          {formatUsd(row.costUsd)}
                        </td>
                        <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                          {formatLatency(row.avgLatencyMs)}
                        </td>
                        <td className="text-secondary py-1.5 font-mono tabular-nums">
                          {row.cacheHits}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

interface FeatureCostPanelProps {
  rows: CostByFeature[];
}

/**
 * Cost per product feature — the same money, grouped by the button that spent it.
 *
 * docs/UI.md §5.15 asks for a pie chart. This renders a single 100% share bar plus the table, and
 * the deviation is recorded: with two or three features a pie's slice angles are unreadable and its
 * ordering arbitrary, while a reader's actual question — "which feature dominates, and by how much"
 * — is answered exactly by a share bar. Each feature also lists the workflows that fed it, so the
 * mapping from `workflow` (what the executor ran) to feature (what the candidate pressed) is visible
 * rather than buried in the backend.
 */
export function FeatureCostPanel({ rows }: FeatureCostPanelProps) {
  const { rows: shares, total } = costShares(
    rows.map((row) => ({ key: row.feature, label: row.feature, value: row.costUsd })),
  );

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>每个功能的花费</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {shares.length === 0 ? (
          <p className="text-secondary text-xs leading-relaxed">这个窗口内没有可归因的功能花费。</p>
        ) : (
          <>
            <div
              className="border-subtle flex h-3 w-full overflow-hidden rounded-sm border"
              role="img"
              aria-label={shares
                .map((share) => `${share.label} ${(share.share * 100).toFixed(1)}%`)
                .join('，')}
            >
              {shares.map((share, index) => (
                <span
                  key={share.key}
                  data-feature={share.key}
                  className={index % 2 === 0 ? 'bg-signal' : 'bg-signal/50'}
                  style={{ width: `${share.share * 100}%` }}
                  title={`${share.label} ${formatUsd(share.value)}（${(share.share * 100).toFixed(1)}%）`}
                />
              ))}
            </div>
            <p className="text-tertiary text-[11px] leading-relaxed">
              合计 {formatUsd(total)}；占比按成本计算，颜色交替只为区分相邻区块。
            </p>
            <ul className="flex flex-col gap-1 text-xs">
              {shares.map((share, index) => {
                const row = rows[index] as CostByFeature;
                return (
                  <li key={share.key} className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{(share.share * 100).toFixed(1)}%</Badge>
                    <span className="text-primary">{share.label}</span>
                    <span className="text-tertiary font-mono text-[11px]">
                      {row.workflows.join(', ')}
                    </span>
                    <span className="text-secondary ml-auto font-mono text-[11px] tabular-nums">
                      {row.runs} 次 · {formatCount(row.tokens)} tok · {formatUsd(row.costUsd)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}
