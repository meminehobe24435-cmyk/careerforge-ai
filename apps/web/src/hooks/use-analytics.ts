'use client';

import { useQueries } from '@tanstack/react-query';
import type { AnalyticsRange } from '@careerforge/shared';

import { api } from '@/lib/api';
import { queryKeys } from '@/lib/query-keys';

/**
 * The five analytics endpoints, fetched as one unit.
 *
 * They share a cohort and a window, so fetching them together keeps the page consistent: a
 * range switch moves every panel at once, and the page can show one loading state and one
 * error state instead of five that flicker independently. The backend builds the cohort once
 * per request, so five calls cost five runs of the same cheap aggregation — see
 * `AnalyticsService.snapshot`.
 */
export function useAnalytics(range: AnalyticsRange) {
  const [funnel, rates, correlation, categories, timeline] = useQueries({
    queries: [
      {
        queryKey: queryKeys.analytics.funnel(range),
        queryFn: () => api.funnel(range),
        retry: 1,
        staleTime: 30_000,
      },
      {
        queryKey: queryKeys.analytics.rates(range),
        queryFn: () => api.rates(range),
        retry: 1,
        staleTime: 30_000,
      },
      {
        queryKey: queryKeys.analytics.correlation(range),
        queryFn: () => api.skillCorrelation(range),
        retry: 1,
        staleTime: 30_000,
      },
      {
        queryKey: queryKeys.analytics.categories(range),
        queryFn: () => api.categories(range),
        retry: 1,
        staleTime: 30_000,
      },
      {
        queryKey: queryKeys.analytics.timeline(range),
        queryFn: () => api.timeline(range),
        retry: 1,
        staleTime: 30_000,
      },
    ],
  });

  const all = [funnel, rates, correlation, categories, timeline];
  const firstError = all.find((query) => query.isError)?.error ?? null;

  return {
    funnel,
    rates,
    correlation,
    categories,
    timeline,
    isPending: all.some((query) => query.isPending),
    isFetching: all.some((query) => query.isFetching),
    error: firstError,
    /** Refetch every panel — the button on the page refreshes the whole window. */
    refetch: () => {
      for (const query of all) void query.refetch();
    },
  };
}
