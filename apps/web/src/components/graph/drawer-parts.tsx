'use client';

import { Badge, cn } from '@careerforge/ui';
import type { ReactNode } from 'react';

import type { EvidenceGraphEdge, EvidenceGraphNode } from '@/lib/graph-api';

import {
  ACCENT_CLASS,
  CONFIDENCE_BADGE,
  CONFIDENCE_TEXT_CLASS,
  confidenceBand,
  formatConfidence,
  nodeStyle,
} from './graph-node-style';

/** Shared building blocks for the three drawer bodies. Small on purpose — one drawer, one voice. */

export function DrawerSection({
  title,
  hint,
  children,
  action,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="border-subtle flex flex-col gap-2 border-t pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-secondary font-mono text-[10px] uppercase tracking-[0.14em]">
          {title}
        </h3>
        {action}
      </div>
      {hint ? <p className="text-tertiary text-[11px] leading-relaxed">{hint}</p> : null}
      {children}
    </section>
  );
}

export function FactRow({
  label,
  children,
  mono = false,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-tertiary shrink-0 text-[11px]">{label}</dt>
      <dd
        className={cn(
          'text-primary min-w-0 text-right text-[11px]',
          mono && 'font-mono tabular-nums',
        )}
      >
        {children}
      </dd>
    </div>
  );
}

/** A fact the API did not supply. `—` plus the reason, never a zero standing in for "unknown". */
export function Unavailable({ children }: { children: ReactNode }) {
  return (
    <span className="text-tertiary">
      <span aria-hidden="true">— </span>
      {children}
    </span>
  );
}

export function CompactList({
  items,
  render,
  empty,
}: {
  items: EvidenceGraphNode[];
  render: (node: EvidenceGraphNode) => ReactNode;
  empty: string;
}) {
  if (items.length === 0) {
    return <p className="text-tertiary text-[11px] leading-relaxed">{empty}</p>;
  }
  return (
    <ul className="flex flex-col gap-1">
      {items.map((node) => (
        <li key={node.id}>{render(node)}</li>
      ))}
    </ul>
  );
}

/** One node, rendered as a button so every list in the drawer is a way to navigate the graph. */
export function NodeLink({
  node,
  detail,
  onSelect,
}: {
  node: EvidenceGraphNode;
  detail?: string;
  onSelect: (id: string) => void;
}) {
  const style = nodeStyle(node.type);
  const Icon = style.icon;
  const band = confidenceBand(node.confidence);
  return (
    <button
      type="button"
      onClick={() => onSelect(node.id)}
      className={cn(
        'border-subtle bg-surface hover:border-default hover:bg-hover flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left',
        'transition-colors duration-[var(--dur-fast)]',
      )}
    >
      <Icon className={cn('size-3.5 shrink-0', ACCENT_CLASS[style.accent])} aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className="text-primary block truncate text-[11px]">{node.label}</span>
        <span className="text-tertiary block truncate font-mono text-[10px]">
          {style.label}
          {detail ? ` · ${detail}` : ''}
        </span>
      </span>
      {node.confidence !== null ? (
        <span className={cn('font-mono text-[11px] tabular-nums', CONFIDENCE_TEXT_CLASS[band])}>
          {formatConfidence(node.confidence)}
        </span>
      ) : null}
    </button>
  );
}

export function ConfidenceLine({ value }: { value: number | null }) {
  const band = confidenceBand(value);
  return (
    <span className="flex items-center justify-end gap-2">
      <span className={cn('font-mono text-[11px] tabular-nums', CONFIDENCE_TEXT_CLASS[band])}>
        {formatConfidence(value)}
      </span>
      <Badge variant={CONFIDENCE_BADGE[band]}>
        {band === 'none'
          ? 'no score'
          : band === 'high'
            ? '≥ 0.75'
            : band === 'medium'
              ? '≥ 0.45'
              : '< 0.45'}
      </Badge>
    </span>
  );
}

/**
 * Every edge that touches the node, with the relation name the API uses.
 *
 * The names are the point: `EVIDENCED_BY` means something different from `DEMONSTRATES`, and a
 * drawer that showed "3 connections" would throw away the only part of the graph that is not
 * obvious from the picture.
 */
export function RelationList({
  nodeId,
  edges,
  labels,
  onSelect,
}: {
  nodeId: string;
  edges: EvidenceGraphEdge[];
  labels: Map<string, EvidenceGraphNode>;
  onSelect: (id: string) => void;
}) {
  if (edges.length === 0) {
    return <p className="text-tertiary text-[11px]">No edge touches this node in the view.</p>;
  }
  const sorted = [...edges].sort(
    (a, b) => a.relation.localeCompare(b.relation) || a.id.localeCompare(b.id),
  );
  return (
    <ul className="flex flex-col gap-1">
      {sorted.map((edge) => {
        const outgoing = edge.source === nodeId;
        const otherId = outgoing ? edge.target : edge.source;
        const other = labels.get(otherId);
        return (
          <li key={edge.id} className="flex items-baseline gap-2">
            <span className="text-secondary shrink-0 font-mono text-[10px] uppercase tracking-wide">
              {edge.relation}
            </span>
            <span className="text-tertiary shrink-0 text-[10px]" aria-hidden="true">
              {outgoing ? '→' : '←'}
            </span>
            <button
              type="button"
              onClick={() => onSelect(otherId)}
              className="text-primary min-w-0 truncate text-left text-[11px] underline-offset-4 hover:underline focus-visible:underline"
            >
              {other?.label ?? otherId.slice(0, 8)}
            </button>
            <span className="text-tertiary ml-auto shrink-0 font-mono text-[10px] tabular-nums">
              {formatConfidence(edge.confidence)}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
