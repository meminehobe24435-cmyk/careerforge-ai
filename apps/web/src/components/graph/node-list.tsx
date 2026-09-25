'use client';

import { Badge, cn } from '@careerforge/ui';

import type { EvidenceGraphNode, ProfileSkill } from '@/lib/graph-api';

import {
  ACCENT_CLASS,
  CONFIDENCE_TEXT_CLASS,
  nodeStyle,
  type NodeFacts,
  type NodeReadout,
} from './graph-node-style';

/**
 * The node index: every node, as a real list, operable by keyboard.
 *
 * The brief requires "an accessible node list as an equivalent navigation path (a real list of
 * nodes with roles, not a decorative `aria-hidden` canvas)". This is that, and it is not a
 * fallback bolted on afterwards — it is the *primary* view below 1024px, where a pan-and-zoom
 * canvas at 375px is a worse tool than a list, and a secondary view above it, where it doubles as
 * a way to find a node whose label you cannot read at the current zoom.
 *
 * Dimming is mirrored here (`data-dimmed`, plus a `sr-only` note), so a screen-reader user gets
 * the same information the canvas conveys with opacity: the node is still here, it just does not
 * match the search.
 */
export interface NodeListProps {
  nodes: EvidenceGraphNode[];
  /** Reading order from the layout, so the list and the picture agree. */
  order: string[];
  facts: Map<string, NodeFacts>;
  readouts: Map<string, NodeReadout>;
  dimmed: Set<string>;
  matched: Set<string>;
  term: string;
  selectedId: string | null;
  declaredSkills: Map<string, ProfileSkill>;
  onSelect: (id: string) => void;
}

export function NodeList({
  nodes,
  order,
  facts,
  readouts,
  dimmed,
  matched,
  term,
  selectedId,
  declaredSkills,
  onSelect,
}: NodeListProps) {
  const rank = new Map(order.map((id, index) => [id, index]));
  const rows = [...nodes].sort((a, b) => {
    const left = rank.get(a.id);
    const right = rank.get(b.id);
    if (left !== undefined && right !== undefined) return left - right;
    if (left !== undefined) return -1;
    if (right !== undefined) return 1;
    return a.label.localeCompare(b.label);
  });

  return (
    <section
      aria-labelledby="graph-node-index-heading"
      className="border-default bg-surface flex flex-col rounded-lg border"
      data-testid="node-index"
    >
      <header className="border-subtle flex flex-wrap items-baseline justify-between gap-2 border-b px-3 py-2">
        <div className="flex flex-col gap-0.5">
          <h2
            id="graph-node-index-heading"
            className="text-primary text-xs font-semibold tracking-tight"
          >
            Node index
          </h2>
          <p className="text-tertiary text-[11px] leading-relaxed">
            The same nodes the canvas draws, in reading order. Every row is a button: selecting one
            opens its details, exactly as clicking it on the canvas does.
            {term ? ' Non-matching nodes stay in the list and are marked as dimmed.' : ''}
          </p>
        </div>
        <span className="text-tertiary font-mono text-[11px] tabular-nums">
          {rows.length} nodes
          {term ? ` · ${matched.size} matched` : ''}
        </span>
      </header>

      <ul className="divide-subtle divide-y">
        {rows.map((node) => {
          const style = nodeStyle(node.type);
          const Icon = style.icon;
          const isDimmed = dimmed.has(node.id);
          const isSelected = node.id === selectedId;
          const readout = readouts.get(node.id);
          const fact = facts.get(node.id);
          const declared =
            style.group === 'skill' && node.group ? declaredSkills.get(node.group) : undefined;
          return (
            <li key={node.id}>
              <button
                type="button"
                data-testid="node-index-row"
                data-node-id={node.id}
                data-node-type={node.type}
                data-dimmed={isDimmed ? 'true' : 'false'}
                aria-current={isSelected ? 'true' : undefined}
                onClick={() => onSelect(node.id)}
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-2 text-left',
                  'transition-colors duration-[var(--dur-fast)]',
                  isSelected ? 'bg-active' : 'hover:bg-hover',
                  isDimmed ? 'opacity-45' : 'opacity-100',
                )}
              >
                <Icon
                  className={cn('size-3.5 shrink-0', ACCENT_CLASS[style.accent])}
                  aria-hidden="true"
                />
                <span className="min-w-0 flex-1">
                  <span className="text-primary block truncate text-[11px]">{node.label}</span>
                  <span className="text-tertiary block truncate font-mono text-[10px]">
                    {style.label}
                    {declared ? ` · declared ${declared.level}` : ''}
                    {node.group && style.group === 'skill' ? ` · ${node.group}` : ''}
                  </span>
                </span>
                {readout ? (
                  <span className="flex shrink-0 items-baseline gap-1 font-mono text-[11px] tabular-nums">
                    <span className="text-tertiary text-[9px] uppercase">{readout.metric}</span>
                    <span className={CONFIDENCE_TEXT_CLASS[readout.band]}>{readout.value}</span>
                  </span>
                ) : null}
                {term ? (
                  <Badge variant={matched.has(node.id) ? 'signal' : 'default'}>
                    {matched.has(node.id) ? 'match' : 'dimmed'}
                  </Badge>
                ) : null}
                <span className="sr-only">
                  {isDimmed ? 'Dimmed by the current search.' : ''}
                  {fact && fact.confidence === null ? ' Confidence unavailable.' : ''}
                  {isSelected ? ' Currently selected.' : ''}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
