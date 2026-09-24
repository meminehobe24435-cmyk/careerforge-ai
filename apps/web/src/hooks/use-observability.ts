'use client';

import { keepPreviousData, useQueries, useQuery } from '@tanstack/react-query';
import type { AiRunFilters, ObservabilityRange } from '@careerforge/shared';

import { api } from '@/lib/api';
import { queryKeys } from '@/lib/query-keys';

/**
 * The AI Runs list, with its filters.
 *
 * `placeholderData: keepPreviousData` on purpose: switching a filter is a re-read of the same table,
 * and dropping back to a skeleton would make the reader lose their place every time they narrow the
 * list. The header shows the in-flight state instead.
 */
export function useAiRuns(filters: AiRunFilters) {
  return useQuery({
    queryKey: queryKeys.observability.runs(filters as Record<string, unknown>),
    queryFn: () => api.aiRuns(filters),
    placeholderData: keepPreviousData,
    staleTime: 5_000,
    retry: 1,
  });
}

/**
 * One run's step chain and calls — fetched only when a row is opened.
 *
 * A list of fifty rows must not fire fifty detail requests, so the query is disabled until the row
 * is expanded; `enabled` is the whole reason this hook takes a boolean.
 */
export function useAiRun(id: string | null) {
  return useQuery({
    queryKey: queryKeys.observability.run(id ?? 'none'),
    queryFn: () => api.aiRun(id as string),
    enabled: Boolean(id),
    staleTime: 30_000,
    retry: 1,
  });
}

/**
 * The five cost reads, fetched as one unit so the page has one loading and one error state.
 *
 * They share a window, and a range switch has to move all of them at once — five independently
 * flickering panels would show a reader numbers from two different windows side by side.
 */
export function useCosts(range: ObservabilityRange) {
  const [costs, byAgent, byFeature, cache, prompts] = useQueries({
    queries: [
      {
        queryKey: queryKeys.observability.costs(range),
        queryFn: () => api.aiCosts(range),
        retry: 1,
        staleTime: 30_000,
      },
      {
        queryKey: queryKeys.observability.costsByAgent(range),
        queryFn: () => api.costsByAgent(range),
        retry: 1,
        staleTime: 30_000,
      },
      {
        queryKey: queryKeys.observability.costsByFeature(range),
        queryFn: () => api.costsByFeature(range),
        retry: 1,
        staleTime: 30_000,
      },
      {
        // The cache and prompt registry are window-independent: they describe the deployment, not
        // the period, so they are keyed without a range.
        queryKey: queryKeys.observability.cache(),
        queryFn: () => api.cacheStats(),
        retry: 1,
        staleTime: 15_000,
      },
      {
        queryKey: queryKeys.observability.prompts(),
        queryFn: () => api.prompts(),
        retry: 1,
        staleTime: 60_000,
      },
    ],
  });

  const all = [costs, byAgent, byFeature, cache, prompts];
  return {
    costs,
    byAgent,
    byFeature,
    cache,
    prompts,
    isPending: all.some((query) => query.isPending),
    isFetching: all.some((query) => query.isFetching),
    error: all.find((query) => query.isError)?.error ?? null,
    refetch: () => {
      for (const query of all) void query.refetch();
    },
  };
}
