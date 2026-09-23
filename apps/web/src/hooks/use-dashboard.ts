'use client';

import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { queryKeys } from '@/lib/query-keys';

/**
 * `GET /dashboard` (docs/API.md §2.10).
 *
 * `retry: 1` keeps a dead backend honest and fast: one retry, then the UI shows the
 * "backend not reachable" panel instead of spinning forever.
 */
export function useDashboard() {
  return useQuery({
    queryKey: queryKeys.dashboard.root(),
    queryFn: () => api.dashboard(),
    retry: 1,
    staleTime: 30_000,
  });
}
