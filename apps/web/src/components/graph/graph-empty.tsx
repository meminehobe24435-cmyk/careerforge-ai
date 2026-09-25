'use client';

import { Button, EmptyState } from '@careerforge/ui';
import { Network } from 'lucide-react';

import type { EvidenceGraph } from '@/lib/graph-api';

import { ImportEvidencePanel } from './import-evidence-panel';

/**
 * The two ways this page can be empty, kept apart because they mean different things.
 *
 * **Nothing there yet** is the account's state: the graph builder has no evidence to link, so the
 * page owes the reader the sentence that explains what would fill it *and* an action that does it.
 * The action runs the real import pipeline rather than linking to a profile route that does not
 * exist yet.
 *
 * **Everything hidden** is the reader's own filter: the API is still returning a graph, and telling
 * them to import a profile would be a lie about why the canvas is blank.
 */
export function GraphEmptyState({
  graph,
  onImported,
}: {
  graph: EvidenceGraph;
  onImported: () => void;
}) {
  return (
    <div className="flex flex-col gap-5">
      <EmptyState
        icon={<Network className="size-5" />}
        title="No evidence links yet"
        description="Your graph is built from your resume, projects and repositories. Import a profile to start connecting evidence."
        hint={`GET /evidence-graph → ${graph.totals.nodes} nodes, 0 edges`}
      />
      <ImportEvidencePanel onImported={onImported} />
    </div>
  );
}

export function FilteredOutState({
  hidden,
  onClear,
}: {
  hidden: Set<string>;
  onClear: () => void;
}) {
  return (
    <EmptyState
      icon={<Network className="size-5" />}
      title="Every node kind is hidden"
      description="The filters exclude every kind this graph contains. The API is still returning the graph — clear the filters to see it."
      action={
        <Button size="sm" variant="secondary" onClick={onClear}>
          Clear filters
        </Button>
      }
      hint={`hide=${[...hidden].join(',')}`}
    />
  );
}
