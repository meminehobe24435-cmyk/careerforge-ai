'use client';

import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  analyzeJob,
  computeMatch,
  fetchJob,
  fetchSkillTree,
  fetchStoredMatch,
  type AnalyzeJobInput,
  type JobDetail,
  type JobMatch,
  type SkillTree,
} from '@/lib/jobs-api';
import { queryKeys } from '@/lib/query-keys';

/**
 * `/app/jobs` queries and mutations.
 *
 * The shape matches the other phases' hooks: one query per endpoint, `staleTime` because a
 * stored analysis does not change under the reader, `retry: 1` because a second attempt is
 * worth one round-trip and a third is not, and an aggregated surface when several reads share a
 * window so the page has one loading state and one error state instead of three panels
 * flickering independently.
 *
 * Writes are **not** optimistic, deliberately: the server decides what a re-parse produces
 * (`parseConfidence`, the requirement rows, the warnings) and what a match scores, so predicting
 * any of it here would mean duplicating the engine — the one thing this architecture is arranged
 * to prevent. The mutation returns the real payload and the reads are invalidated behind it.
 *
 * The three read options are declared once and shared between the individual hooks and the
 * workspace hook, so a query key can never be valid in one and stale in the other.
 */

function detailOptions(jobId: string | null) {
  return {
    queryKey: queryKeys.jobs.detail(jobId ?? 'none'),
    queryFn: () => fetchJob(jobId as string),
    enabled: Boolean(jobId),
    staleTime: 60_000,
    retry: 1,
  };
}

function treeOptions(jobId: string | null) {
  return {
    queryKey: queryKeys.jobs.skillTree(jobId ?? 'none'),
    queryFn: () => fetchSkillTree(jobId as string),
    enabled: Boolean(jobId),
    staleTime: 60_000,
    retry: 1,
  };
}

/**
 * `GET /jobs/{id}/match` — the newest stored match.
 *
 * A posting that has never been matched resolves to `null` (the fetcher turns the API's `404`
 * into a state rather than an error), so this query's `error` only ever means a real failure.
 */
function storedMatchOptions(jobId: string | null) {
  return {
    queryKey: queryKeys.jobs.match(jobId ?? 'none'),
    queryFn: () => fetchStoredMatch(jobId as string),
    enabled: Boolean(jobId),
    staleTime: 30_000,
    retry: 1,
  };
}

/** `POST /jobs/analyze` — the posting → stored analysis. */
export function useAnalyzeJob() {
  const queryClient = useQueryClient();
  return useMutation<JobDetail, unknown, AnalyzeJobInput>({
    mutationFn: analyzeJob,
    onSuccess: (analysis) => {
      // The detail, the tree and any stored match all describe the job that was just written.
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all() });
      queryClient.setQueryData(queryKeys.jobs.detail(analysis.id), analysis);
    },
  });
}

/** `POST /jobs/{id}/match` — recompute against the current evidence graph and store the row. */
export function useComputeMatch() {
  const queryClient = useQueryClient();
  return useMutation<JobMatch, unknown, string>({
    mutationFn: computeMatch,
    onSuccess: () => {
      // The stored match is superseded by this one; the page keeps the computed payload and
      // this invalidation is what makes a later `GET` agree with it.
      void queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all() });
    },
  });
}

/** `GET /jobs/{id}` — the stored analysis. */
export function useJob(jobId: string | null) {
  return useQuery(detailOptions(jobId));
}

/** `GET /jobs/{id}/skill-tree` — the three levels, each requirement with its JD sentence. */
export function useSkillTree(jobId: string | null) {
  return useQuery(treeOptions(jobId));
}

/** `GET /jobs/{id}/match` — the newest stored match, or `null`. */
export function useStoredMatch(jobId: string | null) {
  return useQuery<JobMatch | null>(storedMatchOptions(jobId));
}

export interface JobsWorkspace {
  detail: ReturnType<typeof useJob>;
  tree: ReturnType<typeof useSkillTree>;
  storedMatch: ReturnType<typeof useStoredMatch>;
  /** True while any of the three has never resolved. */
  isPending: boolean;
  isFetching: boolean;
  /** The first real error across the three reads, or `null`. */
  error: unknown;
  refetch: () => void;
}

/**
 * The three reads of one posting, as one unit.
 *
 * They share a window: a new job id has to move all of them at once, or the page would show the
 * skill tree of one posting beside the match of another.
 */
export function useJobsWorkspace(jobId: string | null): JobsWorkspace {
  const [detail, tree, storedMatch] = useQueries({
    queries: [detailOptions(jobId), treeOptions(jobId), storedMatchOptions(jobId)],
  });

  const all = [detail, tree, storedMatch];
  return {
    detail: detail as ReturnType<typeof useJob>,
    tree: tree as ReturnType<typeof useSkillTree>,
    storedMatch: storedMatch as ReturnType<typeof useStoredMatch>,
    isPending: all.some((query) => query.isPending),
    isFetching: all.some((query) => query.isFetching),
    error: all.find((query) => query.isError)?.error ?? null,
    refetch: () => {
      for (const query of all) void query.refetch();
    },
  };
}

export type { JobDetail, JobMatch, SkillTree };
