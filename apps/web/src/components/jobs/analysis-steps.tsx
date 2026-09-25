'use client';

import { Badge, Spinner } from '@careerforge/ui';
import { Check, ChevronRight, CircleDashed } from 'lucide-react';
import { useId, useState } from 'react';

export interface AnalysisStep {
  key: string;
  /** The step's honest name — what the pipeline does, not a progress animation. */
  label: string;
  /**
   * What the *response* proves about this step, or `null` when nothing has arrived yet.
   *
   * This is the whole design: a step is marked done because a payload contains the thing that
   * step produces (`role` and `parseConfidence`, the resolved skills, the cited evidence, the
   * five dimensions, the gap lists), never because a timer elapsed.
   */
  note: string | null;
}

export interface AnalysisStepsProps {
  steps: AnalysisStep[];
  /** Key of the step the request in flight belongs to, or `null` when nothing is running. */
  runningKey: string | null;
  /** Measured client-side for the request in flight. `null` when no request is running. */
  elapsedMs: number | null;
  /** True once every step has a note: the list collapses into a summary line. */
  complete: boolean;
}

export function formatElapsed(milliseconds: number): string {
  const seconds = Math.max(0, milliseconds) / 1000;
  return `${seconds.toFixed(1)} s`;
}

/**
 * The analysis stepper.
 *
 * **Why there is no animated per-step progress here.** `POST /jobs/analyze` and
 * `POST /jobs/{id}/match` are both synchronous, single-response endpoints (docs/API.md §2.6,
 * and `routers/jobs.py` says so in its module docstring): the server reports nothing until the
 * whole analysis is finished. A stepper that walked through five steps on a timer would be
 * inventing a progress signal that does not exist, and it would be *wrong* in the direction
 * that matters — showing "Scoring job fit" while the request is still parsing would tell the
 * user the analysis is nearly done when it may yet fail.
 *
 * So the component shows two things it can actually know:
 *
 * 1. **which stage the request in flight performs** (the analyze call parses and resolves
 *    skills; the match call compares evidence, scores and builds the gap lists) — marked with
 *    an indeterminate spinner and `aria-current="step"`, not a percentage;
 * 2. **which stages have demonstrably finished**, marked from the fields the response brought
 *    back, with the count or score that proves it.
 *
 * The elapsed time is measured on this side of the wire, so it is a real number rather than a
 * simulated one, and the in-flight note says plainly that the server reports no interim state.
 */
export function AnalysisSteps({ steps, runningKey, elapsedMs, complete }: AnalysisStepsProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const doneCount = steps.filter((step) => step.note !== null).length;

  // Once everything has landed, the list is an audit record rather than feedback, so it
  // collapses to one line and stays out of the way of the result it produced.
  if (complete && !open) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-expanded={false}
          // The list is rendered on demand, so the control only names it once it exists — a
          // dangling `aria-controls` id is worse than none.
          aria-controls={undefined}
          className="text-secondary hover:text-primary focus-visible:outline-brand inline-flex items-center gap-1 rounded-sm text-[11px] focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <ChevronRight className="size-3" aria-hidden="true" />
          Analysis steps
        </button>
        <Badge variant="outline">{`${doneCount}/${steps.length} 完成`}</Badge>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2" id={panelId}>
      {complete ? (
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-expanded
          aria-controls={panelId}
          className="text-tertiary hover:text-secondary focus-visible:outline-brand inline-flex items-center gap-1 self-start rounded-sm text-[11px] focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <ChevronRight className="size-3 rotate-90" aria-hidden="true" />
          收起步骤
        </button>
      ) : null}

      <ol className="flex flex-col gap-1.5" aria-label="Analysis steps">
        {steps.map((step) => {
          const running = step.key === runningKey;
          const done = step.note !== null;
          return (
            <li
              key={step.key}
              aria-current={running ? 'step' : undefined}
              className="flex items-start gap-2"
            >
              <span
                aria-hidden="true"
                className={
                  done
                    ? 'text-evidence mt-0.5'
                    : running
                      ? 'text-signal mt-0.5'
                      : 'text-tertiary mt-0.5'
                }
              >
                {done ? (
                  <Check className="size-3.5" />
                ) : running ? (
                  <Spinner size="sm" />
                ) : (
                  <CircleDashed className="size-3.5" />
                )}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className={done ? 'text-secondary text-xs' : 'text-primary text-xs'}>
                  {step.label}
                  {running ? <span className="sr-only">（进行中）</span> : null}
                </span>
                {step.note ? (
                  <span className="text-tertiary font-mono text-[11px] tabular-nums">
                    {step.note}
                  </span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ol>

      {runningKey ? (
        <p className="text-tertiary text-[11px] leading-relaxed">
          该接口一次请求只返回一次结果，服务端不上报中间阶段；这里只标注请求在做什么。 已等待{' '}
          <span className="font-mono tabular-nums">{formatElapsed(elapsedMs ?? 0)}</span>。
        </p>
      ) : null}
    </div>
  );
}
