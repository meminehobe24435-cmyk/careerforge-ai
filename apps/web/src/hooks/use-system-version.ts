'use client';

import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { queryKeys } from '@/lib/query-keys';

/**
 * `GET /system/version` (docs/API.md §2.13) — public, read-only.
 *
 * `staleTime: Infinity` rather than the health grid's 15s: the answer only changes when the
 * process is replaced, and re-fetching it on every focus would make a page whose whole point is
 * "which build answered me" flicker between two builds.
 */
export function useSystemVersion() {
  return useQuery({
    queryKey: queryKeys.system.version(),
    queryFn: () => api.systemVersion(),
    retry: 1,
    staleTime: Infinity,
  });
}
