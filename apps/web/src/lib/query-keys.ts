/**
 * TanStack Query key factory — one place for every cache key, so invalidations in later
 * phases cannot drift from the queries that populate them.
 */
export const queryKeys = {
  auth: {
    me: () => ['auth', 'me'] as const,
  },
  dashboard: {
    root: () => ['dashboard'] as const,
  },
  system: {
    health: () => ['system', 'health'] as const,
  },
} as const;
