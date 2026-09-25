'use client';

import { Card, CodeBlock, ErrorState, Skeleton, cn } from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';
import dynamic from 'next/dynamic';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { FilteredOutState, GraphEmptyState } from '@/components/graph/graph-empty';
import { GraphFilterPanel, MIN_CONFIDENCES } from '@/components/graph/graph-filter-panel';
import {
  FilterTrigger,
  GraphDisplayControls,
  GraphHeader,
  ReadTrigger,
} from '@/components/graph/graph-header';
import { layoutGraph, readingOrder, type GraphLayout } from '@/components/graph/graph-layout';
import {
  dimmedEdges,
  factsForAll,
  indexGraph,
  relationsOf,
  searchGraph,
  summarise,
} from '@/components/graph/graph-model';
import { groupOf, nodeReadout } from '@/components/graph/graph-node-style';
import { GraphSummaryStrip, RelationFooter } from '@/components/graph/graph-summary-strip';
import { HowToRead } from '@/components/graph/how-to-read';
import { NodeDrawer } from '@/components/graph/node-drawer';
import { NodeList } from '@/components/graph/node-list';
import { useEvidenceDetail, useEvidenceGraph, useEvidenceTrace } from '@/hooks/use-evidence-graph';
import { API_BASE_URL } from '@/lib/api';
import { GRAPH_NODE_TYPES, evidenceGraphUrl, type EvidenceGraphNode } from '@/lib/graph-api';

/**
 * `/app/evidence-graph` — the Career Evidence Graph explorer (PRD FR-6, `docs/API.md` §2.5).
 *
 * One idea, three surfaces:
 *
 * 1. **the canvas** (`@xyflow/react`, through `next/dynamic` so the dashboard never ships it) draws
 *    the layered graph, dims what a search excludes, and is one tab stop with arrow-key movement
 *    inside;
 * 2. **the node index** lists the same nodes as real buttons — the accessible equivalent, and the
 *    primary view below 1024px, where a pan-and-zoom canvas is the wrong tool at 375px;
 * 3. **the drawer** explains one node: where a piece of evidence came from, what rests on it, and
 *    how its confidence was computed.
 *
 * Three rules from the brief are enforced in code rather than in a comment: search **dims** and
 * never deletes (`searchGraph`); the selected node lives in the URL (`?skill=` / `?node=`) so a
 * refresh and a shared link restore the view; and every figure is either read from the API or
 * counted from what the API returned — `0` is never printed where the answer is "unavailable".
 *
 * All the state lives here and nowhere else: the header, the filter panel and the summary strip are
 * pure functions of it, which is why the whole page can be reasoned about from this one file.
 */

const GraphCanvas = dynamic(
  () => import('@/components/graph/graph-canvas').then((module) => module.GraphCanvas),
  {
    ssr: false,
    // A skeleton that keeps the page's height stable, so nothing jumps when the canvas lands.
    loading: () => <Skeleton className="h-full w-full" />,
  },
);

function parseDepth(raw: string | null): number {
  const value = Number(raw);
  return value === 1 || value === 2 || value === 3 ? value : 2;
}

function parseMinConfidence(raw: string | null): number {
  const value = Number(raw);
  return MIN_CONFIDENCES.some((option) => option.value === value) ? value : 0;
}

export function EvidenceGraphView() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname() ?? '/app/evidence-graph';

  const skillParam = searchParams.get('skill');
  const nodeParam = searchParams.get('node');
  const depth = parseDepth(searchParams.get('depth'));
  const minConfidence = parseMinConfidence(searchParams.get('minConfidence'));
  const hidden = useMemo(
    () => new Set((searchParams.get('hide') ?? '').split(',').filter(Boolean)),
    [searchParams],
  );

  /**
   * The canvas scope, seeded from the URL *once*.
   *
   * A deep link (`/app/jobs` → `?skill=FreeRTOS`) and a refresh have to re-read the graph around
   * that node. A click inside the page must not: selecting a skill in order to read it is not a
   * request to throw the rest of the picture away, so the scope moves only when the reader presses
   * Focus or Reset.
   */
  const [scope, setScope] = useState<string | null>(() => {
    const focus = searchParams.get('focus');
    if (focus) return focus;
    const skill = searchParams.get('skill');
    return skill ? `skill:${skill}` : null;
  });
  const [query, setQuery] = useState('');
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [forceCanvas, setForceCanvas] = useState(false);
  const [command, setCommand] = useState({ kind: 'fit' as 'fit' | 'reset', seq: 0 });

  const update = useCallback(
    (patch: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === '') next.delete(key);
        else next.set(key, value);
      }
      const queryString = next.toString();
      // `replace`, not `push`: the selection is page state, and a reader clicking through eight
      // nodes should not have to press Back eight times.
      router.replace(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
    },
    [pathname, router, searchParams],
  );

  /**
   * `?types=` is an **include** list, so it is the API's own vocabulary minus what the reader hid.
   * An empty list means "no filter" and is sent as absent — sending `types=` empty would ask for a
   * graph with no nodes in it, which is the opposite of the default view.
   */
  const includedTypes = useMemo(
    () => (hidden.size === 0 ? [] : [...GRAPH_NODE_TYPES].filter((type) => !hidden.has(type))),
    [hidden],
  );

  const graph = useEvidenceGraph({ focus: scope, depth, types: includedTypes, minConfidence });

  const data = graph.graph.data;
  const nodes = useMemo(() => data?.nodes ?? [], [data]);
  const edges = useMemo(() => data?.edges ?? [], [data]);

  const index = useMemo(() => indexGraph(nodes, edges), [nodes, edges]);
  const facts = useMemo(() => factsForAll(index, nodes), [index, nodes]);
  const readouts = useMemo(
    () => new Map(nodes.map((node) => [node.id, nodeReadout(node, facts.get(node.id)!)] as const)),
    [nodes, facts],
  );

  const layout: GraphLayout = useMemo(
    () =>
      layoutGraph(
        nodes.map((node) => ({
          id: node.id,
          type: node.type,
          label: node.label,
          weight: facts.get(node.id)?.evidenceCount ?? 0,
          subkey: `${String((node.meta ?? {})['category'] ?? '')}${String((node.meta ?? {})['kind'] ?? '')}`,
        })),
      ),
    [nodes, facts],
  );
  const order = useMemo(() => readingOrder(layout.placements), [layout]);

  const search = useMemo(() => searchGraph(nodes, edges, query), [nodes, edges, query]);
  const dimEdges = useMemo(
    () => dimmedEdges(edges, search.dimmed, search.term),
    [edges, search.dimmed, search.term],
  );

  const selectedId = useMemo(() => {
    if (nodeParam && index.byId.has(nodeParam)) return nodeParam;
    if (skillParam) {
      const match = nodes.find(
        (node) =>
          groupOf(node.type) === 'skill' &&
          (node.group === skillParam || node.label === skillParam || node.id === skillParam),
      );
      if (match) return match.id;
    }
    return null;
  }, [index, nodeParam, skillParam, nodes]);

  const selectedNode = selectedId ? (index.byId.get(selectedId) ?? null) : null;
  const selectedGroup = selectedNode ? groupOf(selectedNode.type) : null;
  const isEvidenceSelection = selectedGroup === 'evidence' || selectedGroup === 'claim';
  const detailId = isEvidenceSelection && selectedNode ? selectedNode.id : null;

  const detail = useEvidenceDetail(detailId);
  const trace = useEvidenceTrace(detailId);

  const declaredSkills = useMemo(
    () => new Map((graph.profile.data?.skills ?? []).map((skill) => [skill.canonicalId, skill])),
    [graph.profile.data],
  );

  const selectNode = useCallback(
    (id: string | null) => {
      if (id === null) {
        update({ node: null, skill: null });
        return;
      }
      const node = index.byId.get(id);
      // A skill is stored by its canonical id: `?skill=free_rtos` is the link other pages make, and
      // it stays readable where a uuid5 does not.
      if (node && groupOf(node.type) === 'skill' && node.group) {
        update({ skill: node.group, node: null });
      } else {
        update({ node: id, skill: null });
      }
    },
    [index, update],
  );

  const focusOn = useCallback(
    (node: EvidenceGraphNode) => {
      const reference =
        groupOf(node.type) === 'skill' && node.group ? `skill:${node.group}` : node.id;
      setScope(reference);
      update({ focus: reference });
    },
    [update],
  );

  const resetView = useCallback(() => {
    setScope(null);
    setForceCanvas(false);
    update({ focus: null, skill: null, node: null });
    setCommand({ kind: 'reset', seq: Date.now() });
  }, [update]);

  const fitCanvas = useCallback(() => {
    setForceCanvas(true);
    setCommand({ kind: 'fit', seq: Date.now() });
  }, []);

  // Escape closes the drawer even when the reader never moved focus into it (a click on a list row
  // does not). `defaultPrevented` is the courtesy that lets the "How to read" popover consume its
  // own Escape instead of closing both.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      if (selectedId) update({ node: null, skill: null });
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [selectedId, update]);

  const header = (
    <GraphHeader
      query={query}
      onQueryChange={setQuery}
      onFit={fitCanvas}
      onReset={resetView}
      searchDisabled={!data}
      endpointLine={
        data
          ? evidenceGraphUrl({ focus: scope, depth, types: includedTypes, minConfidence })
          : undefined
      }
      filterSlot={
        data ? (
          <FilterTrigger>
            <GraphFilterPanel
              graph={data}
              hidden={hidden}
              onToggleGroup={(types, shown) => {
                for (const type of types) {
                  if (shown) hidden.add(type);
                  else hidden.delete(type);
                }
                update({ hide: [...hidden].join(',') });
              }}
              depth={depth}
              onDepthChange={(value) => update({ depth: String(value) })}
              minConfidence={minConfidence}
              onMinConfidenceChange={(value) =>
                update({ minConfidence: value === 0 ? null : String(value) })
              }
              onClear={() => update({ hide: null, minConfidence: null })}
            />
          </FilterTrigger>
        ) : null
      }
      readSlot={
        data ? (
          <ReadTrigger>
            <HowToRead graph={data} />
          </ReadTrigger>
        ) : null
      }
    />
  );

  if (graph.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-[clamp(360px,58vh,620px)] w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (graph.error || !data) {
    const apiError = isApiError(graph.error) ? graph.error : null;
    return (
      <div className="flex flex-col gap-5">
        {header}
        <ErrorState
          title={
            apiError?.isNetworkError
              ? 'Backend not reachable'
              : 'The evidence graph could not be read'
          }
          error={graph.error}
          code={apiError?.code ?? 'UNKNOWN'}
          requestId={apiError?.requestId ?? null}
          onRetry={graph.refetch}
          retrying={graph.isFetching}
          statusHref="/system"
          retryLabel="Retry"
          details={
            <CodeBlock
              filename="GET /evidence-graph"
              code={`${API_BASE_URL}/evidence-graph?depth=${depth}`}
              language="txt"
              maxHeight={64}
            />
          }
        />
      </div>
    );
  }

  // Two empty states, because they are two different facts: nothing exists to draw yet, or a filter
  // the reader chose excluded everything (`graph-empty.tsx`).
  if (data.nodes.length === 0 && (data.totals.edges ?? 0) === 0) {
    return (
      <div className="flex flex-col gap-5">
        {header}
        <GraphEmptyState graph={data} onImported={graph.refetch} />
      </div>
    );
  }

  const summary = summarise(data);
  const filtered = hidden.size > 0 || minConfidence > 0;
  const unresolvedDeepLink =
    skillParam !== null && !selectedId && nodes.length > 0 ? skillParam : null;

  return (
    <div className="flex flex-col gap-4">
      {header}

      {unresolvedDeepLink ? (
        <p role="status" className="text-weak text-[11px]">
          Nothing in the graph matches{' '}
          <span className="font-mono">?skill={unresolvedDeepLink}</span>. The canvas is showing the
          whole graph instead — a stale link is not an error.
        </p>
      ) : null}

      <GraphSummaryStrip
        summary={summary}
        searchTerm={search.term}
        matched={search.matched.size}
        dimmed={search.dimmed.size}
        scope={scope}
        filtered={filtered}
        onClearScope={() => {
          setScope(null);
          update({ focus: null });
        }}
      />

      {nodes.length === 0 ? (
        <FilteredOutState
          hidden={hidden}
          onClear={() => update({ hide: null, minConfidence: null })}
        />
      ) : null}

      <GraphDisplayControls
        showEdgeLabels={showEdgeLabels}
        onToggleEdgeLabels={() => setShowEdgeLabels((value) => !value)}
        canvasShown={forceCanvas}
        onToggleCanvas={() => setForceCanvas((value) => !value)}
      />

      {nodes.length > 0 ? (
        <Card className="overflow-hidden">
          <div
            className={cn(
              'h-[clamp(360px,58vh,620px)] w-full',
              forceCanvas ? 'block' : 'hidden lg:block',
            )}
          >
            <GraphCanvas
              nodes={nodes}
              edges={edges}
              layout={layout}
              readouts={readouts}
              dimmedNodeIds={search.dimmed}
              dimmedEdgeIds={dimEdges}
              searching={Boolean(search.term)}
              selectedId={selectedId}
              showEdgeLabels={showEdgeLabels}
              command={command}
              onSelect={selectNode}
            />
          </div>
          <div
            className={cn(
              'border-subtle items-start gap-2 border-t px-3 py-2',
              forceCanvas ? 'flex' : 'hidden lg:flex',
            )}
          >
            <p className="text-tertiary shrink-0 font-mono text-[10px] uppercase tracking-[0.14em]">
              Left to right
            </p>
            <div className="flex flex-col gap-0.5">
              <p className="text-tertiary text-[11px]">
                Candidate → projects and experience → skills → evidence. Arrow keys move between
                nodes once the canvas has focus.
              </p>
              {/* Below `lg` the canvas is an overview: a 1220px graph in a 341px box cannot show
                  readable labels, and pretending otherwise is how a phone view ends up unusable. */}
              <p className="text-tertiary text-[11px] lg:hidden">
                At this width the canvas is an overview only — the node index below is the readable
                view, and every function here is reachable from it. Pinch or scroll to zoom in.
              </p>
            </div>
          </div>
        </Card>
      ) : null}

      <NodeList
        nodes={nodes}
        order={order}
        facts={facts}
        readouts={readouts}
        dimmed={search.dimmed}
        matched={search.matched}
        term={search.term}
        selectedId={selectedId}
        declaredSkills={declaredSkills}
        onSelect={selectNode}
      />

      <NodeDrawer
        node={selectedNode}
        facts={selectedId ? (facts.get(selectedId) ?? null) : null}
        readout={selectedId ? (readouts.get(selectedId) ?? null) : null}
        relations={selectedNode ? relationsOf(index, selectedNode) : null}
        edges={selectedId ? (index.incident.get(selectedId) ?? []) : []}
        labels={index.byId}
        declaredSkill={
          selectedNode && selectedNode.group
            ? (declaredSkills.get(selectedNode.group) ?? null)
            : null
        }
        profileState={
          graph.profile.isPending ? 'pending' : graph.profile.isError ? 'unavailable' : 'ready'
        }
        detail={detail.data ?? null}
        detailState={detail.isPending ? 'pending' : detail.isError ? 'unavailable' : 'ready'}
        trace={trace.data ?? null}
        traceState={trace.isPending ? 'pending' : trace.isError ? 'unavailable' : 'ready'}
        onFocusNode={focusOn}
        onSelect={selectNode}
        onClose={() => update({ node: null, skill: null })}
      />

      <RelationFooter summary={summary} />
    </div>
  );
}
