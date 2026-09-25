'use client';

import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';

import {
  fetchEvidenceDetail,
  fetchEvidenceGraph,
  fetchEvidenceList,
  fetchEvidenceTrace,
  fetchProfile,
} from '@/lib/graph-api';
import { importEvidenceSource, type ImportProgress } from '@/lib/graph-import';
import { queryKeys } from '@/lib/query-keys';

/**
 * The three reads the graph page is built on, fetched as one unit.
 *
 * They are one unit because they describe one thing: `GET /evidence-graph` draws the picture,
 * `GET /evidence` supplies the confidence *factors* the graph nodes do not carry, and
 * `GET /profile` supplies the declared skill level — without it a skill has no "strength" at
 * all, and inventing one is the failure this product exists to avoid.
 *
 * Only the graph itself can fail the page. The two supplementary reads degrade to "unavailable"
 * for the section that needed them, because a skill whose declared level cannot be read is still
 * a skill with evidence behind it.
 */
export interface GraphQueryInput {
  focus?: string | null;
  depth: number;
  types: string[];
  minConfidence: number;
}

export function useEvidenceGraph(query: GraphQueryInput) {
  const key = {
    focus: query.focus ?? null,
    depth: query.depth,
    types: [...query.types].sort(),
    minConfidence: query.minConfidence,
  };

  const [graph, evidence, profile] = useQueries({
    queries: [
      {
        queryKey: queryKeys.evidence.graph(key),
        queryFn: () =>
          fetchEvidenceGraph({
            focus: query.focus ?? null,
            depth: query.depth,
            types: query.types,
            minConfidence: query.minConfidence,
            limit: 500,
          }),
        retry: 1,
        staleTime: 20_000,
        // Clicking a node re-reads the same canvas with a new focus; dropping to a skeleton would
        // make the reader lose the picture they were looking at.
        placeholderData: keepPreviousData,
      },
      {
        queryKey: queryKeys.evidence.list(),
        queryFn: () => fetchEvidenceList({ limit: 200 }),
        retry: 1,
        staleTime: 30_000,
      },
      {
        queryKey: queryKeys.evidence.profile(),
        queryFn: () => fetchProfile(),
        retry: 1,
        staleTime: 60_000,
      },
    ],
  });

  return {
    graph,
    evidence,
    profile,
    isPending: graph.isPending,
    isFetching: [graph, evidence, profile].some((entry) => entry.isFetching),
    /** The page-level failure: only the graph read can stop it from rendering. */
    error: graph.error,
    refetch: () => {
      void graph.refetch();
      void evidence.refetch();
      void profile.refetch();
    },
  };
}

/**
 * One evidence item's full record, fetched only for the item the drawer is showing.
 *
 * The graph carries a 200-character snippet and the locator; the five confidence *factors* and
 * the reverse-provenance count only exist on `GET /evidence/{id}`, and fetching them for every
 * node in the picture would be 200 requests for one drawer.
 */
export function useEvidenceDetail(id: string | null) {
  return useQuery({
    queryKey: queryKeys.evidence.detail(id ?? 'none'),
    queryFn: () => fetchEvidenceDetail(id as string),
    enabled: Boolean(id),
    retry: 1,
    staleTime: 60_000,
  });
}

/** Reverse provenance: which skills or claims rest on this item. */
export function useEvidenceTrace(id: string | null) {
  return useQuery({
    queryKey: queryKeys.evidence.trace(id ?? 'none'),
    queryFn: () => fetchEvidenceTrace(id as string),
    enabled: Boolean(id),
    retry: 1,
    staleTime: 60_000,
  });
}

/**
 * The empty state's action: profile extraction, upload, parse task, analysis.
 *
 * Failure is surfaced verbatim and nothing is retried behind the reader's back — a half-imported
 * profile is worse than a visible failure, because the graph would then be built from material
 * that is only partly there.
 */
export function useImportEvidenceSource() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      text: string;
      filename?: string;
      onProgress?: (u: ImportProgress) => void;
    }) =>
      importEvidenceSource(input.text, { filename: input.filename, onProgress: input.onProgress }),
    onSuccess: () => {
      // The graph, the evidence list and the profile all just changed.
      void client.invalidateQueries({ queryKey: queryKeys.evidence.all() });
      void client.invalidateQueries({ queryKey: queryKeys.evidence.profile() });
      void client.invalidateQueries({ queryKey: queryKeys.dashboard.root() });
    },
  });
}
