'use client';

import { Button, Input, cn } from '@careerforge/ui';
import { HelpCircle, Maximize2, RotateCcw, Search, SlidersHorizontal, X } from 'lucide-react';
import type { ReactNode } from 'react';

import { GraphPopover } from './graph-popover';

/**
 * The page header: what this is, which endpoint is behind it, and the five controls on the right —
 * Search, Filter, Fit view, Reset view and "How to read this graph".
 *
 * The endpoint line is printed in mono because the page is a *reading* of an API response: a
 * reader who wants to check a number can copy the URL, and the parameters shown are the ones the
 * page actually sent (focus, depth, types, minConfidence), not a generic path.
 */
export interface GraphHeaderProps {
  query: string;
  onQueryChange: (value: string) => void;
  onFit: () => void;
  onReset: () => void;
  filterSlot: ReactNode;
  readSlot: ReactNode;
  /** The exact request the current view came from. */
  endpointLine?: string;
  searchDisabled?: boolean;
}

export function GraphHeader({
  query,
  onQueryChange,
  onFit,
  onReset,
  filterSlot,
  readSlot,
  endpointLine,
  searchDisabled,
}: GraphHeaderProps) {
  return (
    <header className="flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-primary text-lg font-semibold tracking-tight">
            Career Evidence Graph
          </h1>
          <p className="text-secondary text-xs leading-relaxed">
            Explore how skills, projects, repositories, documents and claims are connected.
          </p>
          {endpointLine ? (
            <p className="text-tertiary break-all font-mono text-[11px]">{endpointLine}</p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              className="text-tertiary pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2"
              aria-hidden="true"
            />
            <Input
              type="search"
              value={query}
              disabled={searchDisabled}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Search nodes"
              aria-label="Search nodes"
              className={cn('w-44 pl-7', query ? 'pr-7' : 'pr-2')}
            />
            {query ? (
              <button
                type="button"
                onClick={() => onQueryChange('')}
                aria-label="Clear search"
                className="text-tertiary hover:text-primary absolute right-1.5 top-1/2 -translate-y-1/2"
              >
                <X className="size-3.5" />
              </button>
            ) : null}
          </div>

          {filterSlot}

          <Button
            variant="ghost"
            size="sm"
            onClick={onFit}
            aria-label="Fit the graph to the canvas"
          >
            <Maximize2 className="size-3.5" aria-hidden="true" />
            Fit view
          </Button>
          <Button variant="ghost" size="sm" onClick={onReset} aria-label="Reset the view">
            <RotateCcw className="size-3.5" aria-hidden="true" />
            Reset view
          </Button>

          {readSlot}
        </div>
      </div>
    </header>
  );
}

/** The Filter trigger, wired to the panel the page renders. */
export function FilterTrigger({ children }: { children: ReactNode }) {
  return (
    <GraphPopover
      label="Filter"
      title="Filter the graph"
      icon={<SlidersHorizontal className="size-3.5" aria-hidden="true" />}
      triggerClassName="gap-1.5"
    >
      {children}
    </GraphPopover>
  );
}

/** The "How to read this graph" trigger. */
export function ReadTrigger({ children }: { children: ReactNode }) {
  return (
    <GraphPopover
      label="How to read this graph"
      title="How to read this graph"
      panelClassName="w-[min(94vw,40rem)]"
      icon={<HelpCircle className="size-3.5" aria-hidden="true" />}
    >
      {children}
    </GraphPopover>
  );
}

/**
 * The row above the canvas: edge labels, and — below `lg`, where the canvas is hidden by default —
 * the button that reveals it.
 *
 * "Show graph" is why this row exists on a phone: the node index is the primary mobile view, but
 * every function the desktop layout has must stay reachable, and the canvas is a function as much
 * as it is a picture. "Fit view" reveals it too, so the two cannot drift apart.
 */
export function GraphDisplayControls({
  showEdgeLabels,
  onToggleEdgeLabels,
  canvasShown,
  onToggleCanvas,
}: {
  showEdgeLabels: boolean;
  onToggleEdgeLabels: () => void;
  canvasShown: boolean;
  onToggleCanvas: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        size="sm"
        variant={showEdgeLabels ? 'secondary' : 'ghost'}
        aria-pressed={showEdgeLabels}
        onClick={onToggleEdgeLabels}
      >
        Edge labels
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="lg:hidden"
        aria-pressed={canvasShown}
        onClick={onToggleCanvas}
      >
        {canvasShown ? 'Hide graph' : 'Show graph'}
      </Button>
      <p className="text-tertiary text-[11px]">
        {showEdgeLabels
          ? 'Every edge is labelled with its relation.'
          : 'Labels appear on the selected node’s edges; switch them on for all of them.'}
      </p>
    </div>
  );
}
