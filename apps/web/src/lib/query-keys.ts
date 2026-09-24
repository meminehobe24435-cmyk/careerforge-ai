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
  analytics: {
    all: () => ['analytics'] as const,
    funnel: (range: string) => ['analytics', 'funnel', range] as const,
    rates: (range: string) => ['analytics', 'rates', range] as const,
    correlation: (range: string) => ['analytics', 'correlation', range] as const,
    categories: (range: string) => ['analytics', 'categories', range] as const,
    timeline: (range: string) => ['analytics', 'timeline', range] as const,
  },
  publicProfile: {
    settings: () => ['public', 'settings'] as const,
  },
} as const;
