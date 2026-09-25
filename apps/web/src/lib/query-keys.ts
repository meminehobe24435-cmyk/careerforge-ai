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
  jobs: {
    /** Everything under this prefix is invalidated when a posting is analysed or matched. */
    all: () => ['jobs'] as const,
    detail: (id: string) => ['jobs', 'detail', id] as const,
    skillTree: (id: string) => ['jobs', 'skill-tree', id] as const,
    /** The stored match — invalidated (not overwritten) by a fresh `POST .../match`. */
    match: (id: string) => ['jobs', 'match', id] as const,
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
  interview: {
    all: () => ['interview'] as const,
    /**
     * One key per session id: a resumed session (`?session=`) is a different cache entry from
     * the fresh one, so a stale transcript can never be shown over a live one.
     */
    session: (id: string) => ['interview', 'session', id] as const,
    /** The target-job picker's read of `GET /jobs`. */
    targetJobs: () => ['interview', 'target-jobs'] as const,
    /** `GET /jobs/{id}/skill-tree` — the requirements this session's questions are drawn from. */
    skillTree: (jobId: string) => ['interview', 'skill-tree', jobId] as const,
    /** `GET /ai/capabilities` — provider and the deployment's stated limitations. */
    capabilities: () => ['interview', 'capabilities'] as const,
  },
  /**
   * PHASE 13 — the Career Evidence Graph (`docs/API.md` §2.5).
   *
   * `graph` takes the whole query object as its key: a different focus, depth or type filter is
   * a different slice of the graph, and sharing one cache entry across them would put a
   * neighbourhood on the canvas under a summary strip counted from another one.
   */
  evidence: {
    all: () => ['evidence'] as const,
    graph: (query: Record<string, unknown>) => ['evidence', 'graph', query] as const,
    list: () => ['evidence', 'list'] as const,
    detail: (id: string) => ['evidence', 'detail', id] as const,
    trace: (id: string) => ['evidence', 'trace', id] as const,
    /** Declared skills — where a skill's *strength* comes from, because the graph has none. */
    profile: () => ['profile', 'summary'] as const,
  },
  /**
   * PHASE 13 — the Resume Claim Validator (`docs/API.md` §2.5, `POST /evidence/validate`).
   *
   * The verdict itself is not keyed: it is a `POST` with a body, so it is a mutation rather than
   * a cached read. What is keyed is the evidence index the verdict's citations are joined
   * against, because that is an ordinary read with an ordinary staleness question.
   */
  validator: {
    all: () => ['validator'] as const,
    /** Keyed by limit: two limits are two reads, and one of them can be truncated. */
    evidenceIndex: (limit: number) => ['validator', 'evidence-index', { limit }] as const,
  },
} as const;
