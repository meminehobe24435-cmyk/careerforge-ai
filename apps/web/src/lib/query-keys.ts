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
  applications: {
    /** Everything under this prefix is invalidated when a card changes. */
    all: () => ['applications'] as const,
    board: (includeArchived = false) => ['applications', 'board', { includeArchived }] as const,
    detail: (id: string) => ['applications', 'detail', id] as const,
  },
} as const;
