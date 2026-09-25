'use client';

import { cn } from '@careerforge/ui';
import {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import '@xyflow/react/dist/style.css';

import type { EvidenceGraphEdge, EvidenceGraphNode } from '@/lib/graph-api';

import {
  BAND_HEADER_HEIGHT,
  NODE_HEIGHT,
  NODE_WIDTH,
  readingOrder,
  type GraphLayout,
} from './graph-layout';
import {
  ACCENT_CLASS,
  BORDER_CLASS,
  CONFIDENCE_TEXT_CLASS,
  SURFACE_CLASS,
  confidenceBand,
  formatConfidence,
  nodeStyle,
  type NodeReadout,
} from './graph-node-style';

/**
 * The canvas: `@xyflow/react`, layered left to right, positions from `graph-layout.ts`.
 *
 * This module is **not** part of the initial bundle. The page loads it with
 * `next/dynamic(..., { ssr: false })`, so the dashboard payload never carries a graph engine it
 * does not draw, and the server never tries to render a canvas that has no viewport.
 *
 * Colour here is semantic, not decorative: the accent on the icon chip says *what kind of thing
 * this is*, and the figure on the right is the node's one number in the token for its confidence
 * band. Nothing is coloured by type except through those three accents.
 */

const NODE_TYPE = 'evidenceNode';
const BAND_TYPE = 'bandLabel';

/** Structural edges are the quiet ones; the evidential chain is the loud one. */
interface RelationVisual {
  stroke: string;
  width: number;
  dash?: string;
  opacity: number;
  label: string;
}

const RELATION_STYLE: Record<string, RelationVisual> = {
  HAS: { stroke: 'var(--border-default)', width: 1, dash: '4 4', opacity: 0.5, label: 'HAS' },
  DEMONSTRATES: { stroke: 'var(--signal)', width: 1.4, opacity: 0.75, label: 'DEMONSTRATES' },
  EVIDENCED_BY: { stroke: 'var(--evidence)', width: 1.4, opacity: 0.7, label: 'EVIDENCED_BY' },
  SUPPORTS: { stroke: 'var(--evidence)', width: 1.4, opacity: 0.8, label: 'SUPPORTS' },
  REQUIRES: { stroke: 'var(--weak)', width: 1.4, opacity: 0.8, label: 'REQUIRES' },
  MATCHES: { stroke: 'var(--evidence)', width: 1.4, opacity: 0.8, label: 'MATCHES' },
  GAP: { stroke: 'var(--danger)', width: 1.4, opacity: 0.8, label: 'GAP' },
  DERIVED_FROM: { stroke: 'var(--border-strong)', width: 1.2, opacity: 0.7, label: 'DERIVED_FROM' },
};

const FALLBACK_STYLE: RelationVisual = {
  stroke: 'var(--border-strong)',
  width: 1.2,
  opacity: 0.6,
  label: 'RELATION',
};

export interface GraphCanvasCommand {
  kind: 'fit' | 'reset';
  /** Bumped by the header to re-run the command even when nothing else changed. */
  seq: number;
}

export interface GraphCanvasProps {
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
  /** Computed by the page and shared with the node index, so list order and picture agree. */
  layout: GraphLayout;
  readouts: Map<string, NodeReadout>;
  dimmedNodeIds: Set<string>;
  dimmedEdgeIds: Set<string>;
  searching: boolean;
  selectedId: string | null;
  showEdgeLabels: boolean;
  command: GraphCanvasCommand;
  onSelect: (id: string | null) => void;
}

interface CardData extends Record<string, unknown> {
  id: string;
  type: string;
  label: string;
  readout: NodeReadout;
  searchTerm: string;
  dimmed: boolean;
  roving: boolean;
  /**
   * The **application's** selection — the `?skill=` / `?node=` the page keeps in the URL.
   *
   * Deliberately not xyflow's own `selected`: the canvas is rendered with
   * `elementsSelectable={false}` (selection is URL state, and a canvas click must not fight the
   * node index for it), so xyflow's `selected` is `false` on every node forever. Binding
   * `aria-pressed` to it announced "not pressed" for the one node the reader had open — see
   * `PHASE 14` below.
   */
  selected: boolean;
}

interface BandData extends Record<string, unknown> {
  title: string;
  count: number;
  lanes: number;
}

const nodeTypes = { [NODE_TYPE]: NodeCard, [BAND_TYPE]: BandHeader };

/**
 * One node: icon chip, label, kind and the single number that decides something about it.
 *
 * The card carries `role="button"` and a roving `tabIndex`, so the canvas is one tab stop with
 * arrow-key movement inside it — the pattern a composite widget is supposed to use — instead of
 * thirty-two stops a keyboard user has to walk through to get past the graph.
 *
 * `aria-pressed` follows the application's selection (`data.selected`), not xyflow's `selected`
 * prop: the canvas sets `elementsSelectable={false}`, so xyflow's own selection is permanently
 * empty and the attribute used to read `"false"` on the selected card as well.
 */
function NodeCard({ data }: NodeProps) {
  const card = data as CardData;
  const style = nodeStyle(card.type);
  const Icon = style.icon;

  return (
    <div
      data-testid="graph-node"
      data-node-id={card.id}
      data-node-type={card.type}
      data-node-kind={style.group}
      data-dimmed={card.dimmed ? 'true' : 'false'}
      data-searched={card.searchTerm ? 'true' : 'false'}
      data-selected={card.selected ? 'true' : 'false'}
      tabIndex={card.roving ? 0 : -1}
      role="button"
      aria-pressed={card.selected}
      aria-label={`${style.label} ${card.label}. ${card.readout.label}.`}
      title={`${style.label} · ${card.label} — ${card.readout.label}`}
      className={cn(
        'flex h-full w-full cursor-pointer flex-col justify-between gap-1 rounded-md px-2 py-1.5',
        'shadow-sm transition-[opacity,border-color] duration-[var(--dur-fast)]',
        BORDER_CLASS[style.border],
        SURFACE_CLASS[style.surface],
        card.dimmed ? 'opacity-25' : 'opacity-100',
        card.selected ? 'border-brand ring-brand ring-2' : '',
      )}
    >
      <Handle
        type="target"
        position={Position.Left}
        isConnectable={false}
        className="size-1.5! border-0! bg-[var(--border-strong)]!"
      />
      <div className="flex min-w-0 items-center gap-1.5">
        <Icon className={cn('size-3.5 shrink-0', ACCENT_CLASS[style.accent])} aria-hidden="true" />
        <span className="text-primary truncate text-[12px] font-medium leading-tight">
          {card.label}
        </span>
      </div>
      <div className="flex items-center justify-between gap-1">
        <span className="text-tertiary font-mono text-[10px] uppercase tracking-wide">
          {card.readout.metric}
        </span>
        <span
          className={cn(
            'font-mono text-[12px] tabular-nums',
            CONFIDENCE_TEXT_CLASS[card.readout.band],
          )}
        >
          {card.readout.value}
        </span>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        isConnectable={false}
        className="size-1.5! border-0! bg-[var(--border-default)]!"
      />
    </div>
  );
}

/** A band caption, e.g. `SKILLS · 22`. Rendered as a node so it shares the canvas transform. */
function BandHeader({ data }: NodeProps) {
  const band = data as BandData;
  return (
    <div className="text-tertiary flex h-full items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]">
      <span className="text-secondary">{band.title}</span>
      <span className="tabular-nums">· {band.count}</span>
      {band.lanes > 1 ? <span className="text-tertiary/70">· {band.lanes} lanes</span> : null}
    </div>
  );
}

function CanvasInner(props: GraphCanvasProps) {
  const {
    nodes: graphNodes,
    edges: graphEdges,
    layout,
    readouts,
    dimmedNodeIds,
    dimmedEdgeIds,
    searching,
    selectedId,
    showEdgeLabels,
    command,
    onSelect,
  } = props;

  const { fitView } = useReactFlow();
  const wrapper = useRef<HTMLDivElement | null>(null);
  const [focusedId, setFocusedId] = useState<string | null>(null);

  const order = useMemo(() => readingOrder(layout.placements), [layout]);
  const activeId = focusedId && order.includes(focusedId) ? focusedId : (order[0] ?? null);

  const reactFlowNodes = useMemo<Node<CardData | BandData>[]>(() => {
    const bands: Node<BandData>[] = layout.bands.map((band) => ({
      id: `band-${band.level}`,
      type: BAND_TYPE,
      position: { x: band.x, y: band.y },
      data: { title: band.title, count: band.count, lanes: band.lanes },
      draggable: false,
      selectable: false,
      focusable: false,
      connectable: false,
      style: { width: band.width, height: BAND_HEADER_HEIGHT },
      // See the note on the cards below: without `measured`, xyflow renders the band
      // `visibility: hidden` for one frame after every re-render.
      measured: { width: band.width, height: BAND_HEADER_HEIGHT },
      zIndex: 0,
    }));

    const cards: Node<CardData>[] = graphNodes.map((node) => {
      const placement = layout.placements.get(node.id) ?? { x: 0, y: 0 };
      return {
        id: node.id,
        type: NODE_TYPE,
        position: placement,
        data: {
          id: node.id,
          type: node.type,
          label: node.label,
          readout:
            readouts.get(node.id) ??
            ({
              value: formatConfidence(node.confidence),
              label: 'confidence',
              metric: 'conf',
              band: confidenceBand(node.confidence),
            } as NodeReadout),
          searchTerm: searching ? 'active' : '',
          dimmed: dimmedNodeIds.has(node.id),
          roving: node.id === activeId,
          selected: node.id === selectedId,
        },
        /**
         * `nopan` is load-bearing, not cosmetic. A card is not draggable here
         * (`nodesDraggable={false}` and `draggable: false` per node), but xyflow only adds the
         * default `noPanClassName` to a node when that node is draggable — so without this class
         * a `mousedown` on a card starts the **pane's** d3-zoom pan gesture. That gesture calls
         * `stopImmediatePropagation()` on the `mousedown` and gives the pane the `dragging`
         * class, so React never sees the press either. A `role="button"` card must not double as
         * a drag surface: panning starts on the canvas background.
         */
        className: 'nopan',
        draggable: false,
        selectable: false,
        focusable: false,
        connectable: false,
        /**
         * Explicit geometry, declared **twice on purpose**: `style` sizes the element, and
         * `measured` tells xyflow the size is already known.
         *
         * `measured` is what makes a card a reliable click target, and leaving it out was the
         * PHASE 13 defect. xyflow renders a node `visibility: hidden` whenever it cannot find a
         * size (`nodeHasDimensions`: `measured?.width ?? width ?? initialWidth`), and it takes
         * `measured` from the node object it is handed. Every re-render of this memo hands it
         * fresh objects with no `measured`, so each re-render hides every node until the
         * ResizeObserver answers — measured on the live stack as a **22 ms** window
         * (`style="… visibility: hidden …"` → `visibility: visible`, timestamps 1896 ms → 1918 ms).
         *
         * A pointer released inside that window is not over the card any more: the browser
         * hit-tests `visibility: hidden` elements as absent, so `pointerup` retargets to the pane
         * and the `click` goes to the nearest common ancestor of the two targets — the pane. The
         * node's `onNodeClick` never ran and the pane's own click handler cleared the URL, which
         * is exactly the PHASE 13 symptom (`locator.click()` leaves `/app/evidence-graph`).
         * Declaring the size removes the window entirely.
         */
        style: { width: NODE_WIDTH, height: NODE_HEIGHT },
        measured: { width: NODE_WIDTH, height: NODE_HEIGHT },
        zIndex: 1,
        ariaLabel: `${nodeStyle(node.type).label} ${node.label}`,
      };
    });

    return [...bands, ...cards];
  }, [graphNodes, layout, readouts, dimmedNodeIds, searching, activeId, selectedId]);

  const reactFlowEdges = useMemo<Edge[]>(
    () =>
      graphEdges.map((edge) => {
        const style = RELATION_STYLE[edge.relation] ?? FALLBACK_STYLE;
        const incident =
          selectedId !== null && (edge.source === selectedId || edge.target === selectedId);
        const dimmed = dimmedEdgeIds.has(edge.id);
        // A label is worth the ink when the edge is part of the chain the reader is looking at,
        // or when the whole graph is small enough that 40 labels are still legible.
        const labelled = !dimmed && (incident || showEdgeLabels);
        return {
          id: edge.id,
          source: edge.source,
          target: edge.target,
          // Orthogonal routing rather than free curves: on a layered graph a bezier from lane 3 of
          // one band to the next sweeps across the lane in between, and the picture starts to read
          // as spaghetti. A step path stays in the gutters, which is what a technical diagram wants.
          type: 'smoothstep',
          pathOptions: { borderRadius: 6 },
          animated: false,
          label: labelled ? style.label : undefined,
          labelShowBg: true,
          labelBgPadding: [3, 1] as [number, number],
          labelBgBorderRadius: 3,
          labelBgStyle: { fill: 'var(--bg-base)', stroke: 'var(--border-subtle)' },
          labelStyle: {
            fill: incident ? 'var(--text-primary)' : 'var(--text-tertiary)',
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
          },
          style: {
            stroke: incident ? 'var(--brand)' : style.stroke,
            strokeWidth: incident ? style.width + 0.6 : style.width,
            strokeDasharray: style.dash,
            opacity: dimmed ? 0.12 : style.opacity,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 12,
            height: 12,
            color: incident ? 'var(--brand)' : style.stroke,
          },
        };
      }),
    [graphEdges, selectedId, showEdgeLabels, dimmedEdgeIds],
  );

  const focusNode = useCallback((id: string) => {
    setFocusedId(id);
    const element = wrapper.current?.querySelector<HTMLElement>(`[data-node-id="${id}"]`);
    element?.focus();
  }, []);

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (order.length === 0) return;
      const index = activeId ? order.indexOf(activeId) : -1;
      const step = (delta: number): void => {
        const next = order[Math.max(0, Math.min(order.length - 1, index + delta))];
        if (next) focusNode(next);
      };
      switch (event.key) {
        case 'ArrowRight':
        case 'ArrowDown':
          event.preventDefault();
          step(1);
          break;
        case 'ArrowLeft':
        case 'ArrowUp':
          event.preventDefault();
          step(-1);
          break;
        case 'Home':
          event.preventDefault();
          if (order.length > 0) focusNode(order[0] as string);
          break;
        case 'End':
          event.preventDefault();
          if (order.length > 0) focusNode(order[order.length - 1] as string);
          break;
        case 'Enter':
        case ' ':
          if (activeId) {
            event.preventDefault();
            onSelect(activeId);
          }
          break;
        default:
          break;
      }
    },
    [activeId, focusNode, onSelect, order],
  );

  // Fit on first paint and whenever the shape changes: a reader must never be handed a graph
  // that starts somewhere in the middle of itself.
  const shapeKey = `${layout.width}x${layout.height}:${order.length}`;
  useEffect(() => {
    const id = window.setTimeout(() => {
      void fitView({ padding: 0.08, duration: 200, maxZoom: 1 });
    }, 60);
    return () => window.clearTimeout(id);
  }, [shapeKey, fitView]);

  useEffect(() => {
    if (command.seq === 0) return;
    void fitView({ padding: 0.08, duration: 200, maxZoom: 1 });
    // `command.seq` is the trigger: the header bumps it for every press, so pressing Fit twice
    // fits twice even though nothing about the graph changed.
  }, [command.seq, command.kind, fitView]);

  return (
    <div
      ref={wrapper}
      data-testid="graph-canvas"
      role="application"
      aria-label="Evidence graph canvas"
      aria-describedby="graph-canvas-help"
      onKeyDown={onKeyDown}
      // Focus is tracked from the wrapper because the cards are rendered by the canvas, not by
      // this component: `focusin` bubbles, so one listener is enough.
      onFocus={(event) => {
        const element = (event.target as HTMLElement).closest?.('[data-node-id]');
        const id = element?.getAttribute('data-node-id');
        if (id) setFocusedId(id);
      }}
      className="h-full w-full"
    >
      <p id="graph-canvas-help" className="sr-only">
        Use the arrow keys to move between nodes, Enter to open the selected node&apos;s details,
        and Escape to close them. The node index below the canvas lists the same nodes as a table
        and is an equivalent way to navigate.
      </p>
      <ReactFlow
        nodes={reactFlowNodes}
        edges={reactFlowEdges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => {
          if (node.id.startsWith('band-')) return;
          onSelect(node.id);
        }}
        onPaneClick={() => onSelect(null)}
        nodesConnectable={false}
        nodesDraggable={false}
        nodesFocusable={false}
        edgesFocusable={false}
        elementsSelectable={false}
        minZoom={0.2}
        maxZoom={2.5}
        fitView
        fitViewOptions={{ padding: 0.08, maxZoom: 1 }}
        proOptions={{ hideAttribution: true }}
        className="bg-base"
      >
        <Background variant={BackgroundVariant.Lines} gap={32} color="var(--grid-line)" />
      </ReactFlow>
    </div>
  );
}

export const GraphCanvas = memo(function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
});
