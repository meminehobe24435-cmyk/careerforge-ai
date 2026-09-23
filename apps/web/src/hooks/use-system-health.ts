'use client';

import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { queryKeys } from '@/lib/query-keys';

/** `GET /system/health` (docs/API.md §2.13) — public, read-only. */
export function useSystemHealth() {
  return useQuery({
    queryKey: queryKeys.system.health(),
    queryFn: () => api.systemHealth(),
    retry: 1,
    staleTime: 15_000,
  });
}
