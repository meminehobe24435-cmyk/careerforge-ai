'use client';

import { Badge } from '@careerforge/ui';

import { formatConfidence } from './graph-node-style';
import type { GraphSummary } from './graph-model';

/**
 * The summary strip: what is on the canvas, said in numbers the canvas can back up.
 *
 * Four things are kept apart on purpose, because merging them is how a summary starts lying about
 * the picture underneath it:
 *
 * * **in view** — counted from this response, so it always matches the canvas;
 * * **not in view** — nodes in the account that this slice does not contain, and the reason they
 *   are missing is only stated when the payload proves it (no edge was dropped, so the extras have
 *   no evidence link);
 * * **dimmed** — nodes the search dimmed but did not remove, said out loud so nobody thinks the
 *   filter deleted data;
 * * **unavailable** — an em dash for a mean that has no measurements behind it, and a sentence for
 *   nodes an edge references but no table holds.
 */
export interface GraphSummaryStripProps {
  summary: GraphSummary;
  searchTerm: string;
  matched: number;
  dimmed: number;
  scope: string | null;
  filtered: boolean;
  onClearScope: () => void;
}

export function GraphSummaryStrip({
  summary,
  searchTerm,
  matched,
  dimmed,
  scope,
  filtered,
  onClearScope,
}: GraphSummaryStripProps) {
  return (
    <div className="border-default bg-surface flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border px-3 py-2">
      <dl className="flex flex-wrap items-center gap-x-6 gap-y-1">
        <div className="flex items-baseline gap-1.5">
          <dt className="text-tertiary text-[11px]">Nodes in view</dt>
          <dd className="text-primary font-mono text-[11px] tabular-nums">{summary.nodes}</dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <dt className="text-tertiary text-[11px]">Edges in view</dt>
          <dd className="text-primary font-mono text-[11px] tabular-nums">{summary.edges}</dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <dt className="text-tertiary text-[11px]">Mean confidence</dt>
          <dd className="text-primary font-mono text-[11px] tabular-nums">
            {summary.meanConfidence === null ? '—' : summary.meanConfidence.toFixed(2)}
          </dd>
        </div>
        {scope ? (
          <div className="flex items-baseline gap-1.5">
            <dt className="text-tertiary text-[11px]">Scoped to</dt>
            <dd className="text-primary font-mono text-[11px]">
              {scope}
              <button
                type="button"
                onClick={onClearScope}
                className="text-tertiary hover:text-primary ml-2 underline-offset-4 hover:underline"
              >
                clear
              </button>
            </dd>
          </div>
        ) : null}
      </dl>

      <div className="text-tertiary flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
        {searchTerm ? (
          <span>
            <span className="text-secondary font-mono">{matched}</span> match
            {matched === 1 ? '' : 'es'} for “{searchTerm}” ·{' '}
            <span className="font-mono">{dimmed}</span> node{dimmed === 1 ? '' : 's'} dimmed, none
            removed
          </span>
        ) : null}
        {summary.hiddenNodes > 0 ? (
          <span>
            {summary.hiddenNodes} more node{summary.hiddenNodes === 1 ? '' : 's'} exist in the
            account
            {summary.hiddenAreUnconnected ? ' and are not connected to any evidence link' : ''}.
          </span>
        ) : null}
        {summary.truncated ? (
          <span className="text-weak">
            The API truncated this view at its node limit; hide a kind or lower the depth.
          </span>
        ) : null}
        {summary.unresolved > 0 ? (
          <span className="text-weak">
            {summary.unresolved} node{summary.unresolved === 1 ? '' : 's'} referenced by an edge has
            no stored row (unresolved), so it is drawn as a placeholder rather than dropped.
          </span>
        ) : null}
        {filtered ? <Badge variant="signal">filters applied</Badge> : null}
      </div>
    </div>
  );
}

/**
 * The relation tally under the canvas: the real edge names with their counts.
 *
 * The names are the product's vocabulary (`EVIDENCED_BY`, `DEMONSTRATES`, …) and reading them next
 * to their counts is how a reader learns the graph without opening the legend. The mean confidence
 * on the right is the one figure that says "unavailable" in words rather than printing `0.00`.
 */
export function RelationFooter({ summary }: { summary: GraphSummary }) {
  return (
    <div className="border-default bg-surface flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border px-3 py-2">
      {summary.relations.length === 0 ? (
        <span className="text-tertiary text-[11px]">
          This view contains no edges, so no relation is listed here.
        </span>
      ) : (
        summary.relations.map((entry) => (
          <span key={entry.relation} className="text-tertiary font-mono text-[11px]">
            <span className="text-secondary">{entry.relation}</span>{' '}
            <span className="tabular-nums">{entry.count}</span>
          </span>
        ))
      )}
      <span className="text-tertiary ml-auto text-[11px]">
        {summary.meanConfidence === null
          ? 'No confidence in this view: nothing here has been scored yet.'
          : `${formatConfidence(summary.meanConfidence)} mean confidence across ${
              summary.withConfidence
            } measured node${summary.withConfidence === 1 ? '' : 's'}`}
      </span>
    </div>
  );
}
