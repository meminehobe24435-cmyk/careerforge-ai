'use client';

import { Badge, cn } from '@careerforge/ui';

import type { EvidenceGraph } from '@/lib/graph-api';

import { ACCENT_CLASS, NODE_GROUPS, nodeStyle } from './graph-node-style';

/**
 * "How to read this graph" — the content of the popover.
 *
 * A popover and not a modal tour, because the whole point is to read it *while* looking at the
 * picture: the canvas stays visible and reachable behind it.
 *
 * Everything here is documentation of the API's own vocabulary, and each row states whether the
 * kind or relation is **present in the current view**. That distinction matters more than it
 * looks: the graph engine can emit eight relations and thirteen node types, but the read path
 * produces only the ones built from stored evidence links, and a legend that implied otherwise
 * would have the reader hunting for `GAP` edges that cannot exist yet.
 */

const NODE_NOTES: Record<string, string> = {
  candidate:
    'The account itself: the root every other node hangs from. It carries no confidence, because it is not evidence — it is whose evidence the rest is.',
  job: 'A stored posting the candidate matched against, with REQUIRES edges to the skills it asks for. It has no confidence of its own: a match is a verdict, and the verdict belongs to the job’s own page.',
  project:
    'A project from the stored profile, with the skills its own description and tech stack demonstrate. The number on it is how many skills it demonstrates.',
  experience:
    'A role from the stored profile — internship, full-time, and so on. It is evidence of context and time as much as of skill.',
  education:
    'A school or programme from the stored profile. It is context: the graph does not score it, and it has no confidence.',
  repository:
    'A code repository tied to the candidate’s work. Repositories arrive with GitHub ingestion; the kind is documented here whether or not one is in the current view.',
  skill:
    'A canonical skill from the taxonomy, joined by its id so two spellings cannot become two skills. The number on it is how many evidence sources support it.',
  evidence:
    'Uploaded material — a repository file, a commit, or a chunk of a document. Its number is a confidence computed from five factors, and the drawer shows all five.',
  claim:
    'A sentence that may be written into a résumé, appearing as evidence of kind llm_inference. It is the weakest tier by design, and the validator is what decides whether it may be used.',
  achievement:
    'An award or certification from the stored profile. It is only as strong as the document behind it, which is why it carries no confidence of its own.',
  interview:
    'A practice interview session and the material it produced. It is evidence of the candidate’s own account, not of the work itself.',
};

const RELATION_NOTES: { relation: string; note: string }[] = [
  {
    relation: 'HAS',
    note: 'The candidate owns this node — a project, an experience, or a skill their material mentions. It is structure rather than proof, which is why it is drawn dashed and quiet.',
  },
  {
    relation: 'DEMONSTRATES',
    note: 'A project or experience shows a skill, taken from that record’s own description and stack. This is the edge that connects something the candidate did to a claim about what they can do.',
  },
  {
    relation: 'EVIDENCED_BY',
    note: 'A skill is backed by this piece of evidence, and the edge carries that evidence’s confidence. These are the edges that turn a skill node from a declaration into something a reviewer can open.',
  },
  {
    relation: 'SUPPORTS',
    note: 'The material justifies the statement on the other end. The claim validator accepts nothing without at least one of these.',
  },
  {
    relation: 'REQUIRES',
    note: 'A posting asks for this skill, at the level it states. Each requirement carries the job-description sentence it came from, so nothing is demanded without a source.',
  },
  {
    relation: 'MATCHES',
    note: 'A required skill is present with evidence behind it. The relation says nothing about how strong that evidence is — the skill’s own confidence does.',
  },
  {
    relation: 'GAP',
    note: 'A posting requires this skill and the graph holds no evidence for it. A gap is an absence, reported as one, rather than a score of zero.',
  },
  {
    relation: 'DERIVED_FROM',
    note: 'One piece of evidence came from another instead of being observed directly. It exists so a summary of a file is never mistaken for the file.',
  },
];

function countOf(record: Record<string, number> | undefined, key: string): number {
  if (!record) return 0;
  return record[key] ?? 0;
}

export function HowToRead({ graph }: { graph: EvidenceGraph }) {
  const typeCounts = graph.stats.nodes_by_type ?? {};
  const relationCounts = graph.stats.edges_by_relation ?? {};

  return (
    <div className="flex flex-col gap-4">
      <section className="flex flex-col gap-1.5">
        <h2 className="text-secondary font-mono text-[10px] uppercase tracking-[0.14em]">
          Reading the picture
        </h2>
        <p className="text-secondary text-[11px] leading-relaxed">
          Columns run left to right along one flow:{' '}
          <span className="font-mono">
            Candidate → projects &amp; experience → skills → evidence
          </span>
          . Every node shows its kind by icon, border weight and surface — colour is reserved for
          confidence, so a green figure always means “evidenced”, never “project”. A dashed edge is
          structure; a solid one is a claim you can open.
        </p>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-secondary font-mono text-[10px] uppercase tracking-[0.14em]">
          Node kinds
        </h2>
        <ul className="flex flex-col gap-2">
          {NODE_GROUPS.map((entry) => {
            const style = nodeStyle(entry.types[0] ?? entry.group);
            const Icon = style.icon;
            const count = entry.types.reduce((total, type) => total + countOf(typeCounts, type), 0);
            return (
              <li key={entry.group} className="flex gap-2">
                <Icon
                  className={cn('mt-0.5 size-3.5 shrink-0', ACCENT_CLASS[style.accent])}
                  aria-hidden="true"
                />
                <div className="flex min-w-0 flex-col gap-0.5">
                  <p className="flex items-center gap-2">
                    <span className="text-primary text-[11px] font-medium">{entry.label}</span>
                    <Badge variant={count > 0 ? 'outline' : 'default'}>
                      {count > 0 ? `${count} in this view` : 'none in this view'}
                    </Badge>
                  </p>
                  <p className="text-tertiary text-[11px] leading-relaxed">
                    {NODE_NOTES[entry.group] ?? 'A node kind this page does not document yet.'}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-secondary font-mono text-[10px] uppercase tracking-[0.14em]">
          Edge labels
        </h2>
        <ul className="flex flex-col gap-2">
          {RELATION_NOTES.map((entry) => {
            const count = countOf(relationCounts, entry.relation);
            return (
              <li key={entry.relation} className="flex flex-col gap-0.5">
                <p className="flex items-center gap-2">
                  <span className="text-secondary font-mono text-[10px] uppercase tracking-wide">
                    {entry.relation}
                  </span>
                  <Badge variant={count > 0 ? 'outline' : 'default'}>
                    {count > 0 ? `${count} in this view` : 'none in this view'}
                  </Badge>
                </p>
                <p className="text-tertiary text-[11px] leading-relaxed">{entry.note}</p>
              </li>
            );
          })}
        </ul>
      </section>

      <section className="border-subtle flex flex-col gap-1.5 border-t pt-3">
        <h2 className="text-secondary font-mono text-[10px] uppercase tracking-[0.14em]">
          Navigating
        </h2>
        <p className="text-tertiary text-[11px] leading-relaxed">
          Click a node to open its details; Escape closes them. With the canvas focused, the arrow
          keys move between nodes, Enter opens one, and the node index under the canvas lists the
          same nodes as buttons. The address bar keeps the selection —{' '}
          <span className="font-mono">?skill=free_rtos</span> or{' '}
          <span className="font-mono">?node=…</span> — so a refresh or a shared link opens the same
          node.
        </p>
      </section>
    </div>
  );
}
