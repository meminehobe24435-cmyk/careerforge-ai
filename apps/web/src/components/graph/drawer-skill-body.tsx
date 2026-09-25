'use client';

import { Badge } from '@careerforge/ui';

import type { EvidenceGraphEdge, EvidenceGraphNode, ProfileSkill } from '@/lib/graph-api';

import {
  CompactList,
  ConfidenceLine,
  DrawerSection,
  FactRow,
  NodeLink,
  RelationList,
  Unavailable,
} from './drawer-parts';
import { kindLabel, sourceOf } from './graph-evidence';
import type { DrawerRelations } from './graph-model';
import type { NodeFacts } from './graph-node-style';

/**
 * The skill drawer: a skill, its strength, and *which* material backs it.
 *
 * The brief asks for skill, strength, evidence count, projects, repositories, evidence sources,
 * related jobs and confidence with its breakdown. Two of those cannot be answered the way the
 * brief assumes, and the drawer says so instead of filling the gap:
 *
 * * **Strength is not in the graph.** The graph's skill node carries a category and a canonical id
 *   and nothing else (`EvidenceService.nodes_and_edges`), so strength is read from the *declared*
 *   profile skill via `GET /profile` and labelled "declared" — a self-report next to a measured
 *   confidence, never blended into one number.
 * * **The API returns no per-skill confidence breakdown.** Confidence is computed per evidence
 *   item, so the drawer shows the mean of the sources (the number the `HAS` edge carries) and
 *   sends the reader one click down to a source, where all five factors are printed.
 *
 * Every list is scoped to "this view": the graph is a depth-limited slice, and a sentence that
 * claimed a total it cannot see would be a fabricated number.
 */
export interface SkillDrawerBodyProps {
  node: EvidenceGraphNode;
  facts: NodeFacts;
  relations: DrawerRelations;
  edges: EvidenceGraphEdge[];
  labels: Map<string, EvidenceGraphNode>;
  declared: ProfileSkill | null;
  profileState: 'pending' | 'ready' | 'unavailable';
  onSelect: (id: string) => void;
}

export function SkillDrawerBody({
  node,
  facts,
  relations,
  edges,
  labels,
  declared,
  profileState,
  onSelect,
}: SkillDrawerBodyProps) {
  const canonicalId = typeof node.group === 'string' ? node.group : null;
  const category = typeof node.meta?.['category'] === 'string' ? node.meta['category'] : null;

  return (
    <>
      <DrawerSection title="Skill">
        <dl className="flex flex-col gap-1.5">
          <FactRow label="Kind">
            <Badge variant="signal">Skill</Badge>
          </FactRow>
          <FactRow label="Canonical id" mono>
            {canonicalId ?? <Unavailable>not recorded on this node</Unavailable>}
          </FactRow>
          <FactRow label="Category">{category ?? <Unavailable>uncategorised</Unavailable>}</FactRow>
        </dl>
      </DrawerSection>

      <DrawerSection
        title="Strength (declared)"
        hint="How the candidate's own profile rates this skill. It is a self-report, which is why it is kept apart from the measured confidence below."
      >
        {profileState === 'pending' ? (
          <p className="text-tertiary text-[11px]">Reading the declared profile…</p>
        ) : profileState === 'unavailable' ? (
          <FactRow label="Level">
            <Unavailable>declared profile unavailable — GET /profile did not return</Unavailable>
          </FactRow>
        ) : declared ? (
          <dl className="flex flex-col gap-1.5">
            <FactRow label="Level">
              <Badge variant={declared.level === 'none' ? 'default' : 'outline'}>
                {declared.level}
              </Badge>
            </FactRow>
            <FactRow label="Evidence score" mono>
              {declared.evidenceScore.toFixed(2)}
            </FactRow>
            <FactRow label="Recorded by">{declared.origin}</FactRow>
            {declared.isTarget ? (
              <FactRow label="Target">
                <Badge variant="signal">target skill</Badge>
              </FactRow>
            ) : null}
          </dl>
        ) : (
          <FactRow label="Level">
            <Unavailable>
              not declared in the profile — this skill is in the graph because material mentions it
            </Unavailable>
          </FactRow>
        )}
      </DrawerSection>

      <DrawerSection
        title="Evidence"
        hint="Confidence is computed per piece of evidence and averaged here; the API returns no per-skill breakdown, so open a source to see all five factors."
      >
        <dl className="flex flex-col gap-1.5">
          <FactRow label="Sources in this view" mono>
            {facts.evidenceCount}
          </FactRow>
          <FactRow label="Mean confidence">
            <ConfidenceLine value={facts.confidence} />
          </FactRow>
        </dl>
      </DrawerSection>

      <DrawerSection title="Projects demonstrating it">
        <CompactList
          items={relations.projects}
          empty="No project in this view demonstrates this skill. A project appears here when its own description or tech stack mentions the skill."
          render={(project) => <NodeLink node={project} onSelect={onSelect} />}
        />
      </DrawerSection>

      <DrawerSection title="Repositories">
        <CompactList
          items={relations.repositories}
          empty="No repository is connected to this skill in this view. Repositories arrive with GitHub ingestion; the graph draws them as soon as one exists."
          render={(repository) => <NodeLink node={repository} onSelect={onSelect} />}
        />
      </DrawerSection>

      <DrawerSection title="Evidence sources">
        <CompactList
          items={relations.evidence}
          empty="No evidence supports this skill yet. That is an absence, not a score of zero — the confidence above is unavailable rather than 0."
          render={(item) => (
            <NodeLink
              node={item}
              detail={`${kindLabel(String(item.meta?.['kind'] ?? item.type))} · ${sourceOf(item)}`}
              onSelect={onSelect}
            />
          )}
        />
      </DrawerSection>

      <DrawerSection title="Related jobs">
        <CompactList
          items={relations.jobs}
          empty="No job in this view requires or matches this skill. Jobs are attached to the graph when a posting is analysed against it."
          render={(job) => <NodeLink node={job} onSelect={onSelect} />}
        />
      </DrawerSection>

      <DrawerSection title="Relations">
        <RelationList nodeId={node.id} edges={edges} labels={labels} onSelect={onSelect} />
      </DrawerSection>
    </>
  );
}
