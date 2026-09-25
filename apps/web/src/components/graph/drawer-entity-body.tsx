'use client';

import { Badge } from '@careerforge/ui';

import type { EvidenceGraphEdge, EvidenceGraphNode } from '@/lib/graph-api';

import {
  CompactList,
  ConfidenceLine,
  DrawerSection,
  FactRow,
  NodeLink,
  RelationList,
  Unavailable,
} from './drawer-parts';
import { kindLabel, locatorText } from './graph-evidence';
import type { DrawerRelations } from './graph-model';
import type { NodeFacts, NodeStyle } from './graph-node-style';

/**
 * The drawer for everything that is neither a skill nor a piece of evidence: the candidate, a
 * project, an experience, an education record, an achievement, a repository, a job.
 *
 * These nodes exist to carry *structure*, so the drawer shows structure: what they demonstrate,
 * what evidence sits behind that, and which statements (jobs) point at them. A project's drawer
 * does not pretend to have a confidence of its own — the number on it is how many skills its own
 * description demonstrates, and the confidence belongs to the evidence underneath.
 */
export interface EntityDrawerBodyProps {
  node: EvidenceGraphNode;
  style: NodeStyle;
  facts: NodeFacts;
  relations: DrawerRelations;
  edges: EvidenceGraphEdge[];
  labels: Map<string, EvidenceGraphNode>;
  onSelect: (id: string) => void;
}

export function EntityDrawerBody({
  node,
  style,
  facts,
  relations,
  edges,
  labels,
  onSelect,
}: EntityDrawerBodyProps) {
  const meta = node.meta ?? {};
  const techStack = Array.isArray(meta['tech_stack']) ? (meta['tech_stack'] as string[]) : [];
  const locator = locatorText(meta['locator'] as never);
  const slug = typeof meta['slug'] === 'string' ? meta['slug'] : null;
  const kind = typeof meta['kind'] === 'string' ? meta['kind'] : null;
  const role = typeof meta['role'] === 'string' ? meta['role'] : null;
  const unresolved = meta['unresolved'] === true;

  return (
    <>
      <DrawerSection title={style.label}>
        <dl className="flex flex-col gap-1.5">
          <FactRow label="Kind">
            <Badge variant="outline">{style.label}</Badge>
          </FactRow>
          {role ? <FactRow label="Role">{role}</FactRow> : null}
          {kind ? <FactRow label="Record">{kindLabel(kind)}</FactRow> : null}
          {slug ? (
            <FactRow label="Profile slug" mono>
              {slug}
            </FactRow>
          ) : null}
          {locator ? (
            <FactRow label="Locator" mono>
              {locator}
            </FactRow>
          ) : null}
          {unresolved ? (
            <p className="text-weak text-[11px] leading-relaxed">
              This node is a placeholder: an edge references it, but no stored row exists for it
              yet. The API reports it as unresolved rather than hiding the edge.
            </p>
          ) : null}
        </dl>
      </DrawerSection>

      <DrawerSection
        title={style.group === 'job' ? 'Requirements' : 'Demonstrates'}
        hint={
          style.group === 'job'
            ? 'The skills the posting asks for, taken from its own analysis.'
            : 'The skills this record shows on its own terms — its description and tech stack, not the candidate’s claims.'
        }
      >
        <CompactList
          items={relations.skills}
          empty={
            style.group === 'job'
              ? 'No requirement of this posting resolved to a skill in the graph.'
              : 'Nothing in this view demonstrates a skill through this record.'
          }
          render={(skill) => <NodeLink node={skill} onSelect={onSelect} />}
        />
      </DrawerSection>

      {techStack.length > 0 ? (
        <DrawerSection title="Tech stack (stored)">
          <ul className="flex flex-wrap gap-1">
            {techStack.map((item) => (
              <li key={item}>
                <Badge variant="default">{item}</Badge>
              </li>
            ))}
          </ul>
        </DrawerSection>
      ) : null}

      <DrawerSection title="Evidence behind it">
        <CompactList
          items={relations.evidence}
          empty="No evidence in this view sits behind this record."
          render={(item) => <NodeLink node={item} onSelect={onSelect} />}
        />
      </DrawerSection>

      <DrawerSection title="Numbers">
        <dl className="flex flex-col gap-1.5">
          <FactRow
            label={style.group === 'job' ? 'Requirements stated' : 'Skills demonstrated'}
            mono
          >
            {style.group === 'job' ? facts.requirements : facts.demonstratedSkills}
          </FactRow>
          <FactRow label="Evidence links in this view" mono>
            {facts.evidenceCount}
          </FactRow>
          <FactRow label="Confidence">
            {facts.confidence === null ? (
              <Unavailable>
                not computed for this node — the confidence belongs to the evidence under it
              </Unavailable>
            ) : (
              <ConfidenceLine value={facts.confidence} />
            )}
          </FactRow>
        </dl>
      </DrawerSection>

      {relations.jobs.length > 0 ? (
        <DrawerSection title="Related jobs">
          <CompactList
            items={relations.jobs}
            empty="No job in this view."
            render={(job) => <NodeLink node={job} onSelect={onSelect} />}
          />
        </DrawerSection>
      ) : null}

      <DrawerSection title="Relations">
        <RelationList nodeId={node.id} edges={edges} labels={labels} onSelect={onSelect} />
      </DrawerSection>
    </>
  );
}
