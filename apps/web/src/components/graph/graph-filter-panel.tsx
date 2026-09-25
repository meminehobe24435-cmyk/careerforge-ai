'use client';

import { Button, cn } from '@careerforge/ui';
import { RotateCcw } from 'lucide-react';

import type { EvidenceGraph, GraphNodeType } from '@/lib/graph-api';

import { filterOptions } from './graph-model';
import { nodeStyle } from './graph-node-style';

/**
 * The Filter popover's body: node kinds, neighbourhood depth and a confidence floor.
 *
 * Two decisions are visible here.
 *
 * **Kinds are filtered by the API, not by the page.** They go out as `?types=`, so the counts and
 * the `truncated` flag in the summary strip describe exactly the slice on the canvas. Hiding nodes
 * in React would leave the strip counting nodes nobody can see.
 *
 * **The confidence floor keeps unmeasured nodes.** `?minConfidence=` drops a node whose confidence
 * was *measured* below the threshold; a node with no confidence at all is unknown, not failing, and
 * a filter that removed it would turn "we never scored this" into "this did not make the cut".
 */
export const DEPTHS = [1, 2, 3] as const;

export const MIN_CONFIDENCES = [
  { value: 0, label: 'Any' },
  { value: 0.45, label: '≥ 0.45' },
  { value: 0.75, label: '≥ 0.75' },
] as const;

export interface GraphFilterPanelProps {
  graph: EvidenceGraph;
  hidden: Set<string>;
  onToggleGroup: (types: GraphNodeType[], shown: boolean) => void;
  depth: number;
  onDepthChange: (depth: number) => void;
  minConfidence: number;
  onMinConfidenceChange: (value: number) => void;
  onClear: () => void;
}

export function GraphFilterPanel({
  graph,
  hidden,
  onToggleGroup,
  depth,
  onDepthChange,
  minConfidence,
  onMinConfidenceChange,
  onClear,
}: GraphFilterPanelProps) {
  const options = filterOptions(graph);
  const filtered = hidden.size > 0 || minConfidence > 0;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1.5">
        <p className="text-tertiary font-mono text-[10px] uppercase tracking-[0.14em]">
          Node kinds in the picture
        </p>
        <ul className="flex flex-col gap-1">
          {options.map((option) => {
            const shown = option.types.some((type) => !hidden.has(type));
            const style = nodeStyle(option.types[0] ?? 'candidate');
            const Icon = style.icon;
            return (
              <li key={option.group}>
                <button
                  type="button"
                  aria-pressed={shown}
                  disabled={option.count === 0}
                  onClick={() => onToggleGroup(option.types, shown)}
                  className={cn(
                    'border-subtle flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left',
                    shown ? 'bg-surface text-primary' : 'text-tertiary opacity-60',
                    option.count === 0 ? 'cursor-not-allowed' : 'hover:border-default',
                  )}
                >
                  <Icon className="size-3.5 shrink-0" aria-hidden="true" />
                  <span className="text-[11px]">{option.label}</span>
                  <span className="ml-auto font-mono text-[10px] tabular-nums">
                    {option.count === 0 ? 'none in graph' : `${option.count} in graph`}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
        <p className="text-tertiary text-[11px] leading-relaxed">
          Counts are the whole graph&apos;s, so a kind that is switched off keeps its own toggle.
        </p>
      </div>

      <div className="border-subtle flex flex-col gap-1.5 border-t pt-3">
        <p className="text-tertiary font-mono text-[10px] uppercase tracking-[0.14em]">
          Neighbourhood depth
        </p>
        <div role="group" aria-label="Neighbourhood depth" className="flex items-center gap-1">
          {DEPTHS.map((value) => (
            <Button
              key={value}
              size="sm"
              variant={value === depth ? 'secondary' : 'ghost'}
              aria-pressed={value === depth}
              onClick={() => onDepthChange(value)}
            >
              {value} hop{value === 1 ? '' : 's'}
            </Button>
          ))}
        </div>
        <p className="text-tertiary text-[11px] leading-relaxed">
          Depth applies when the canvas is scoped to a node (Focus, or a{' '}
          <span className="font-mono">?skill=</span> link). Without a scope the API returns the
          whole graph.
        </p>
      </div>

      <div className="border-subtle flex flex-col gap-1.5 border-t pt-3">
        <p className="text-tertiary font-mono text-[10px] uppercase tracking-[0.14em]">
          Minimum confidence
        </p>
        <div role="group" aria-label="Minimum confidence" className="flex flex-wrap gap-1">
          {MIN_CONFIDENCES.map((option) => (
            <Button
              key={option.value}
              size="sm"
              variant={option.value === minConfidence ? 'secondary' : 'ghost'}
              aria-pressed={option.value === minConfidence}
              onClick={() => onMinConfidenceChange(option.value)}
            >
              {option.label}
            </Button>
          ))}
        </div>
        <p className="text-tertiary text-[11px] leading-relaxed">
          Nodes with no computed confidence are kept: the floor drops measured values below it, it
          does not turn “unmeasured” into “fails”.
        </p>
      </div>

      {filtered ? (
        <Button variant="ghost" size="sm" onClick={onClear} className="self-start">
          <RotateCcw className="size-3.5" aria-hidden="true" />
          Clear filters
        </Button>
      ) : null}
    </div>
  );
}
