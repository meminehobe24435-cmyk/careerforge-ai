'use client';

import { Badge } from '@careerforge/ui';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Fragment, useId, useState } from 'react';
import type { AiRun } from '@careerforge/shared';

import { RunDetailPanel } from '@/components/observability/run-detail-panel';
import {
  formatCount,
  formatInstant,
  formatLatency,
  formatUsd,
  statusBadge,
  zeroSpendSummary,
} from '@/lib/observability-format';

interface RunTableProps {
  runs: AiRun[];
}

interface RunRowsProps {
  runs: AiRun[];
  openId: string | null;
  onToggle: (id: string) => void;
  panelPrefix: string;
}

/**
 * `AiRunsTable` (docs/UI.md §5.15).
 *
 * Columns are the ones an operator asks for in order: who did it (agent/workflow), with what
 * (model), what it cost (tokens/latency/money), whether it worked (status/cache), and when.
 *
 * Four deliberate choices:
 *
 * * the expand control is a `<button>` in the row header rather than a click handler on `<tr>`, so
 *   the drill-down is keyboard-reachable and announced with `aria-expanded`/`aria-controls`;
 * * below `sm` the nine columns are **replaced by a list of the same facts** instead of being
 *   squeezed or clipped. Measured at 375 px, a horizontally scrolling table hid cost, status and
 *   time off-screen with no hint that they existed — and those are the columns this page is for;
 * * the "why is this zero" explanation is printed **once above the list** rather than repeated on
 *   every row — on a zero-key deployment every row is zero, and a note per row would double the
 *   height while adding no information;
 * * `latencyMs` of `null` renders as an em dash: `0 ms` would be a claim about a run that never
 *   finished.
 */
export function RunTable({ runs }: RunTableProps) {
  const [openId, setOpenId] = useState<string | null>(null);
  const panelPrefix = useId();
  const zeroNote = zeroSpendSummary(runs);

  if (runs.length === 0) {
    return (
      <p className="text-secondary text-xs leading-relaxed">
        没有符合条件的运行记录。放宽筛选条件，或先去触发一次 AI 操作（分析一段 JD
        就会产生一条运行）。
      </p>
    );
  }

  const toggle = (id: string) => setOpenId((current) => (current === id ? null : id));
  const shared = { runs, openId, onToggle: toggle, panelPrefix };

  return (
    <div className="flex flex-col gap-2">
      {zeroNote ? <p className="text-tertiary text-[11px] leading-relaxed">{zeroNote}</p> : null}
      <RunListMobile {...shared} />
      <RunTableDesktop {...shared} />
    </div>
  );
}

function RunTableDesktop({ runs, openId, onToggle, panelPrefix }: RunRowsProps) {
  return (
    <div className="hidden overflow-x-auto sm:block">
      <table className="w-full text-left text-xs">
        <caption className="sr-only">
          AI 运行记录：Agent、workflow、模型、token、耗时、成本、状态与缓存命中
        </caption>
        <thead className="text-tertiary">
          <tr>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Agent / Workflow
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Model
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Tokens
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Latency
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Cost
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Status
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Cache
            </th>
            <th scope="col" className="py-1.5 pr-3 font-medium">
              时间 (UTC)
            </th>
            <th scope="col" className="py-1.5 font-medium">
              <span className="sr-only">展开步骤链</span>
              <span aria-hidden="true">步骤</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const expanded = openId === run.id;
            const badge = statusBadge(run.status);
            const panelId = `${panelPrefix}-${run.id}`;
            return (
              <Fragment key={run.id}>
                <tr data-run={run.id} className="border-subtle border-t align-top">
                  <th scope="row" className="text-primary py-2 pr-3 text-left font-medium">
                    <button
                      type="button"
                      onClick={() => onToggle(run.id)}
                      aria-expanded={expanded}
                      aria-controls={panelId}
                      className="ease-forge flex items-center gap-1.5 text-left transition-colors duration-[var(--dur-fast)]"
                    >
                      {expanded ? (
                        <ChevronDown className="size-3.5 shrink-0" aria-hidden="true" />
                      ) : (
                        <ChevronRight className="size-3.5 shrink-0" aria-hidden="true" />
                      )}
                      <span className="font-mono">{run.agent}</span>
                      <span className="text-tertiary" aria-hidden="true">
                        ·
                      </span>
                      <span className="text-secondary">{run.workflow}</span>
                    </button>
                    {run.promptVersion ? (
                      <span className="text-tertiary mt-0.5 block pl-5 font-mono text-[10px]">
                        prompt {run.promptVersion}
                      </span>
                    ) : null}
                  </th>
                  <td className="text-secondary py-2 pr-3 font-mono">
                    {run.model ?? run.provider ?? '—'}
                  </td>
                  <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                    {formatCount(run.totalTokens)}
                  </td>
                  <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                    {formatLatency(run.latencyMs)}
                  </td>
                  <td className="text-secondary py-2 pr-3 font-mono tabular-nums">
                    {formatUsd(run.costUsd)}
                  </td>
                  <td className="py-2 pr-3">
                    <Badge variant={badge.variant}>{badge.label}</Badge>
                  </td>
                  <td className="py-2 pr-3">
                    {run.cacheHit ? (
                      <Badge variant="signal">命中</Badge>
                    ) : (
                      <span className="text-tertiary font-mono text-[11px]">未命中</span>
                    )}
                  </td>
                  <td className="text-tertiary py-2 pr-3 font-mono tabular-nums">
                    {formatInstant(run.startedAt)}
                  </td>
                  <td className="text-tertiary py-2 font-mono tabular-nums">
                    {run.stepCount > 0 ? `${run.stepCount} 步` : '—'}
                  </td>
                </tr>
                {expanded ? (
                  <tr className="border-subtle bg-surface border-t">
                    <td colSpan={9} id={panelId} className="p-0">
                      <RunDetailPanel runId={run.id} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RunListMobile({ runs, openId, onToggle, panelPrefix }: RunRowsProps) {
  return (
    <ul className="flex flex-col gap-2 sm:hidden" data-run-list>
      {runs.map((run) => {
        const expanded = openId === run.id;
        const badge = statusBadge(run.status);
        const panelId = `${panelPrefix}-m-${run.id}`;
        return (
          <li
            key={run.id}
            data-run={run.id}
            className="border-subtle bg-elevated flex flex-col gap-1.5 rounded-sm border p-2.5"
          >
            <button
              type="button"
              onClick={() => onToggle(run.id)}
              aria-expanded={expanded}
              aria-controls={panelId}
              className="flex items-start gap-1.5 text-left text-xs"
            >
              {expanded ? (
                <ChevronDown className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              ) : (
                <ChevronRight className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              )}
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-primary break-all font-mono">
                  {run.agent} · <span className="text-secondary">{run.workflow}</span>
                </span>
                {run.promptVersion ? (
                  <span className="text-tertiary font-mono text-[10px]">
                    prompt {run.promptVersion}
                  </span>
                ) : null}
              </span>
            </button>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] tabular-nums">
              <Badge variant={badge.variant}>{badge.label}</Badge>
              <span className="text-secondary">{run.model ?? run.provider ?? '—'}</span>
              <span className="text-secondary">{formatLatency(run.latencyMs)}</span>
              <span className="text-secondary">{formatCount(run.totalTokens)} tok</span>
              <span className="text-secondary">{formatUsd(run.costUsd)}</span>
              <span className="text-tertiary">
                {run.cacheHit ? '缓存命中' : '未命中'} · {run.stepCount} 步
              </span>
              <span className="text-tertiary">{formatInstant(run.startedAt)}</span>
            </div>
            {expanded ? (
              <div id={panelId} className="border-subtle bg-surface rounded-sm border">
                <RunDetailPanel runId={run.id} />
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
