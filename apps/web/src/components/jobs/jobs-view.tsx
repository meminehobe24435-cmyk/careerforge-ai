'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  Skeleton,
  Spinner,
} from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';
import { Briefcase, Wand2 } from 'lucide-react';

import { AnalysisSteps, type AnalysisStep } from '@/components/jobs/analysis-steps';
import { JdInputPanel } from '@/components/jobs/jd-input-panel';
import { JobResult } from '@/components/jobs/job-result';
import {
  demoDraft,
  draftToRequest,
  emptyDraft,
  isDraftAnalysable,
  type JobDraft,
} from '@/components/jobs/job-draft';
import { analysisWarnings, formatPoints, type MatchSource } from '@/components/jobs/job-match-view';
import { useAnalyzeJob, useComputeMatch, useJobsWorkspace } from '@/hooks/use-jobs';
import { API_BASE_URL } from '@/lib/api';
import type { JobDetail, JobMatch } from '@/lib/jobs-api';

export interface JobsViewProps {
  /** `?job=<id>` — a posting loaded from the database rather than analysed in this session. */
  initialJobId?: string | null;
}

/**
 * `/app/jobs` — JD Intelligence (PRD FR-5, docs/UI.md §5.7–5.8).
 *
 * One page for the two halves of the documented flow (`/app/jobs/new` and `/app/jobs/[id]` in
 * docs/UI.md §4), because they are one task: paste a posting, read the parse, see the match and
 * the gaps. Left is the input, right is the result — stacked below `lg`.
 *
 * Three things this page refuses to do:
 *
 * 1. **invent progress.** Both endpoints are synchronous single-response calls, so the stepper
 *    marks the stages a response proves happened and shows an indeterminate state for the stage
 *    the in-flight request performs (see `analysis-steps.tsx`);
 * 2. **invent numbers.** A figure the payload does not carry renders as `—`, with the endpoint
 *    that would report it named;
 * 3. **merge states that are different.** Unknown is not Missing, and a requirement the payload
 *    never classified is not silently reported as either.
 *
 * State is by job id, not by response: `?job=<id>` reloads a posting through `GET /jobs/{id}`,
 * `GET /jobs/{id}/skill-tree` and `GET /jobs/{id}/match`, so a link to an analysis is shareable
 * and a refresh does not lose the reader's place.
 */
export function JobsView({ initialJobId = null }: JobsViewProps) {
  const [draft, setDraft] = useState<JobDraft>(() => emptyDraft());
  const [jobId, setJobId] = useState<string | null>(initialJobId);
  const [analyzed, setAnalyzed] = useState<JobDetail | null>(null);
  const [computedMatch, setComputedMatch] = useState<JobMatch | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  const analyze = useAnalyzeJob();
  const computeMatch = useComputeMatch();
  const workspace = useJobsWorkspace(jobId);

  const busy = analyze.isPending || computeMatch.isPending;
  const elapsedMs = useElapsedMs(busy);

  const analysis = workspace.detail.data ?? analyzed ?? null;
  const tree = workspace.tree.data;
  const match: JobMatch | null = computedMatch ?? workspace.storedMatch.data ?? null;
  const matchSource: MatchSource = computedMatch ? 'computed' : 'stored';

  const steps = useMemo<AnalysisStep[]>(
    () => [
      {
        key: 'parse',
        label: 'Parsing job description',
        note: analysis
          ? `parseConfidence ${analysis.parseConfidence.toFixed(2)} · ${analysis.descriptionChars} 字符 · ${analysis.parseStatus}`
          : null,
      },
      {
        key: 'skills',
        label: 'Extracting required skills',
        note: tree
          ? `${tree.required.length}+${tree.preferred.length}+${tree.bonus.length} 项要求 · 未归一化 ${tree.unmatchedCount}`
          : null,
      },
      {
        key: 'evidence',
        label: 'Comparing candidate evidence',
        note: match ? `引用证据 ${match.why.evidenceUsed.length} 条` : null,
      },
      {
        key: 'score',
        label: 'Scoring job fit',
        note: match
          ? `score ${formatPoints(match.score)}/100 · ${Object.keys(match.dimensions).length} 个维度`
          : null,
      },
      {
        key: 'gaps',
        label: 'Building gap analysis',
        note: match
          ? `strengths ${match.strengths.length} · 缺口 ${match.gaps.length} · 待确认 ${match.unknowns.length}`
          : null,
      },
    ],
    [analysis, tree, match],
  );

  // Which stage the request currently in flight performs. The analyze call parses and resolves
  // skills; the match call compares evidence, scores and builds the gap lists. Nothing else is
  // claimed — see the long comment in `analysis-steps.tsx` for why there is no per-step progress.
  const runningKey = analyze.isPending ? 'parse' : computeMatch.isPending ? 'evidence' : null;
  const stepsComplete = steps.every((step) => step.note !== null);

  const patchDraft = useCallback((patch: Partial<JobDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
  }, []);

  const handleAnalyze = useCallback(() => {
    if (!isDraftAnalysable(draft)) return;
    const request = draftToRequest(draft);
    setComputedMatch(null);
    setWarnings([]);
    analyze.mutate(request, {
      onSuccess: (result) => {
        setAnalyzed(result);
        setWarnings(analysisWarnings(result));
        setJobId(result.id);
        rememberJob(result.id);
        computeMatch.mutate(result.id, {
          onSuccess: (fresh) => setComputedMatch(fresh),
        });
      },
    });
  }, [analyze, computeMatch, draft]);

  const handleRecompute = useCallback(() => {
    if (!jobId) return;
    computeMatch.mutate(jobId, { onSuccess: (fresh) => setComputedMatch(fresh) });
  }, [computeMatch, jobId]);

  const handleLoadDemo = useCallback(() => setDraft(demoDraft()), []);
  const handleClear = useCallback(() => {
    setDraft(emptyDraft());
    setComputedMatch(null);
    setWarnings([]);
  }, []);

  const analyzeError = analyze.isError ? analyze.error : null;
  const analyzeApiError = isApiError(analyzeError) ? analyzeError : null;
  const detailError = jobId && workspace.detail.isError ? workspace.detail.error : null;
  const detailApiError = isApiError(detailError) ? detailError : null;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-primary text-lg font-semibold tracking-tight">JD Intelligence</h1>
          <p className="text-secondary text-xs leading-relaxed">
            Understand what the role actually asks for, how well you match, and where the gaps are.
          </p>
          <p className="text-tertiary font-mono text-[11px]">
            {`POST ${API_BASE_URL}/jobs/analyze · GET /jobs/{id}/skill-tree · POST /jobs/{id}/match`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="outline">解析同步返回</Badge>
          <Badge variant="outline">匹配为确定性算术</Badge>
          <Badge variant="outline">match@1.0.0</Badge>
        </div>
      </header>

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[minmax(0,24rem)_minmax(0,1fr)] xl:grid-cols-[minmax(0,28rem)_minmax(0,1fr)]">
        <div className="min-w-0 lg:sticky lg:top-4">
          <JdInputPanel
            draft={draft}
            onChange={patchDraft}
            onAnalyze={handleAnalyze}
            onLoadDemo={handleLoadDemo}
            onClear={handleClear}
            busy={busy}
          />
        </div>

        <section aria-label="分析结果" className="flex min-w-0 flex-col gap-4">
          {analyzeError ? (
            <ErrorState
              title={analyzeApiError?.isNetworkError ? 'Backend not reachable' : '岗位解析失败'}
              error={analyzeError}
              code={analyzeApiError?.code ?? 'UNKNOWN'}
              requestId={analyzeApiError?.requestId ?? null}
              onRetry={() => {
                if (analyze.variables) analyze.mutate(analyze.variables);
              }}
              retrying={analyze.isPending}
              statusHref="/system"
              details={
                <span className="font-mono text-[11px]">POST {API_BASE_URL}/jobs/analyze</span>
              }
            />
          ) : null}

          {!analysis && busy ? (
            <Card>
              <CardHeader>
                <CardTitle>Analyzing</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <AnalysisSteps
                  steps={steps}
                  runningKey={runningKey}
                  elapsedMs={elapsedMs}
                  complete={false}
                />
                <Skeleton className="h-24" />
                <Skeleton className="h-40" />
              </CardContent>
            </Card>
          ) : null}

          {!analysis && !busy && jobId ? (
            detailError ? (
              <ErrorState
                title="读取岗位失败"
                error={detailError}
                code={detailApiError?.code ?? 'UNKNOWN'}
                requestId={detailApiError?.requestId ?? null}
                onRetry={workspace.refetch}
                retrying={workspace.isFetching}
                statusHref="/system"
                details={
                  <span className="font-mono text-[11px]">
                    GET {API_BASE_URL}/jobs/{jobId}
                  </span>
                }
              />
            ) : (
              <Card>
                <CardContent className="flex items-center gap-2 pt-5">
                  <Spinner size="sm" label="读取岗位" />
                  <span className="text-secondary text-xs">
                    正在读取已保存的解析结果 <span className="font-mono">{jobId}</span>
                  </span>
                </CardContent>
              </Card>
            )
          ) : null}

          {!analysis && !busy && !jobId && !analyzeError ? (
            <EmptyState
              data-jobs-empty
              icon={<Briefcase className="size-5" />}
              title="还没有分析结果"
              description="Paste a job description to see how your evidence lines up."
              action={
                <Button onClick={handleLoadDemo} aria-label="Load Demo JD（填入左侧输入框）">
                  <Wand2 className="size-3.5" aria-hidden="true" />
                  Load Demo JD
                </Button>
              }
              hint="POST /jobs/analyze → JDAnalysis · 想先看看效果可以直接载入示例 JD"
            />
          ) : null}

          {analysis ? (
            <>
              {!busy && steps.length > 0 ? (
                <AnalysisSteps
                  steps={steps}
                  runningKey={null}
                  elapsedMs={null}
                  complete={stepsComplete}
                />
              ) : null}
              <JobResult
                analysis={analysis}
                tree={tree}
                treePending={Boolean(jobId) && workspace.tree.isPending}
                treeError={workspace.tree.isError ? workspace.tree.error : null}
                onRetryTree={() => void workspace.tree.refetch()}
                match={match}
                matchSource={matchSource}
                matchPending={computeMatch.isPending}
                matchError={computeMatch.isError ? computeMatch.error : null}
                analyzeWarnings={warnings}
                onRecomputeMatch={handleRecompute}
                onRetryMatch={handleRecompute}
              />
            </>
          ) : null}
        </section>
      </div>
    </div>
  );
}

/**
 * Milliseconds since the current request started, measured on this side of the wire.
 *
 * A real measurement rather than a simulated one: the stepper prints it while a request is in
 * flight, and it resets when nothing is running, so it can never be mistaken for server-side
 * progress.
 */
function useElapsedMs(running: boolean): number | null {
  const [elapsed, setElapsed] = useState<number | null>(null);
  useEffect(() => {
    if (!running) {
      setElapsed(null);
      return;
    }
    const startedAt = Date.now();
    setElapsed(0);
    const handle = window.setInterval(() => setElapsed(Date.now() - startedAt), 200);
    return () => window.clearInterval(handle);
  }, [running]);
  return elapsed;
}

/**
 * Keep `?job=<id>` in the address bar.
 *
 * `history.replaceState` rather than the router: the state that matters is the *job id*, the
 * page is already mounted, and a client-side navigation would re-run the route for no reason.
 * Wrapped because the view is rendered in jsdom by the tests, where `history` exists but the
 * layout's other browser APIs may not.
 */
function rememberJob(jobId: string): void {
  if (typeof window === 'undefined' || !window.history?.replaceState) return;
  window.history.replaceState(null, '', `/app/jobs?job=${encodeURIComponent(jobId)}`);
}
