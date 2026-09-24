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
  observability: {
    all: () => ['observability'] as const,
    /** The filter object is part of the key: two filter sets are two different lists. */
    runs: (filters: Record<string, unknown>) => ['observability', 'runs', filters] as const,
    run: (id: string) => ['observability', 'run', id] as const,
    costs: (range: string) => ['observability', 'costs', range] as const,
    costsByAgent: (range: string) => ['observability', 'costs', 'by-agent', range] as const,
    costsByFeature: (range: string) => ['observability', 'costs', 'by-feature', range] as const,
    cache: () => ['observability', 'cache'] as const,
    prompts: () => ['observability', 'prompts'] as const,
  },
  publicProfile: {
    settings: () => ['public', 'settings'] as const,
  },
} as const;
