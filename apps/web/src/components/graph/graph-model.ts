import type {
  EvidenceGraph,
  EvidenceGraphEdge,
  EvidenceGraphNode,
  GraphNodeType,
} from '@/lib/graph-api';

import { NODE_GROUPS, groupOf, type NodeFacts, type NodeGroup } from './graph-node-style';

/**
 * Everything the page derives from a graph response.
 *
 * **Why a model layer at all.** The API returns nodes and edges; a page needs *facts about a
 * node* — how many sources back this skill, which project demonstrates it, whether anything in
 * this view requires it. Every one of those is a count or a set computed from the edges that came
 * back, never an assumption about what the API probably meant. Two consequences follow, and both
 * are deliberate:
 *
 * 1. **A number is scoped to the view.** `GET /evidence-graph` returns a depth-limited slice, so
 *    a skill with two sources here may have five in the whole graph. The UI says "in this view"
 *    wherever that is the case instead of implying a total it cannot see.
 * 2. **`null` stays `null`.** A skill whose confidence could not be read from any edge is
 *    `null`, and every consumer renders a dash — the strip does not average it into a zero.
 */

export interface GraphIndex {
  byId: Map<string, EvidenceGraphNode>;
  /** Every node in the view, in payload order. */
  nodes: EvidenceGraphNode[];
  /** Every edge in the view, in payload order. */
  edges: EvidenceGraphEdge[];
  /** Every edge that touches a node, in either direction. */
  incident: Map<string, EvidenceGraphEdge[]>;
  /** Edges by `from → to` relation, for the directional questions below. */
  incoming: Map<string, EvidenceGraphEdge[]>;
  outgoing: Map<string, EvidenceGraphEdge[]>;
}

export function indexGraph(nodes: EvidenceGraphNode[], edges: EvidenceGraphEdge[]): GraphIndex {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const incident = new Map<string, EvidenceGraphEdge[]>();
  const incoming = new Map<string, EvidenceGraphEdge[]>();
  const outgoing = new Map<string, EvidenceGraphEdge[]>();
  const push = (
    map: Map<string, EvidenceGraphEdge[]>,
    key: string,
    edge: EvidenceGraphEdge,
  ): void => {
    const list = map.get(key);
    if (list) list.push(edge);
    else map.set(key, [edge]);
  };
  for (const edge of edges) {
    push(incident, edge.source, edge);
    if (edge.target !== edge.source) push(incident, edge.target, edge);
    push(outgoing, edge.source, edge);
    if (edge.target !== edge.source) push(incoming, edge.target, edge);
  }
  return { byId, nodes, edges, incident, incoming, outgoing };
}

function neighboursOf(index: GraphIndex, id: string, relation?: string): EvidenceGraphNode[] {
  const seen = new Map<string, EvidenceGraphNode>();
  for (const edge of index.incident.get(id) ?? []) {
    if (relation && edge.relation !== relation) continue;
    const otherId = edge.source === id ? edge.target : edge.source;
    const node = index.byId.get(otherId);
    if (node) seen.set(otherId, node);
  }
  return [...seen.values()];
}

function mean(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function confidencesOf(edges: EvidenceGraphEdge[]): number[] {
  return edges
    .map((edge) => edge.confidence)
    .filter((value): value is number => typeof value === 'number');
}

export type NodeFactsResult = NodeFacts;

/**
 * The facts the node card and the drawer both read.
 *
 * A skill's confidence comes from the `candidate --HAS--> skill` edge, which the builder writes
 * with the skill's mean evidence confidence on it. When that edge carries nothing (a declared
 * skill nothing supports) the fallback is the mean of its own `EVIDENCED_BY` edges, and when
 * there are none either the answer is `null` — "no evidence" and "confidence 0.00" are different
 * statements and this function refuses to merge them.
 */
export function factsFor(index: GraphIndex, node: EvidenceGraphNode): NodeFacts {
  const group = groupOf(node.type);
  const outgoing = index.outgoing.get(node.id) ?? [];
  const incoming = index.incoming.get(node.id) ?? [];

  if (group === 'skill') {
    const sources = outgoing.filter((edge) => edge.relation === 'EVIDENCED_BY');
    const declared = incoming.filter((edge) => edge.relation === 'HAS');
    return {
      evidenceCount: sources.length,
      demonstratedSkills: 0,
      requirements: 0,
      confidence:
        mean(confidencesOf(declared)) ??
        mean(confidencesOf(sources)) ??
        (node.confidence === null ? null : node.confidence),
    };
  }

  if (group === 'candidate') {
    return {
      evidenceCount: index.edges.filter((edge) => edge.relation === 'EVIDENCED_BY').length,
      demonstratedSkills: 0,
      requirements: 0,
      confidence: null,
    };
  }

  if (group === 'job') {
    const requires = outgoing.filter((edge) => edge.relation === 'REQUIRES');
    const matched = outgoing.filter((edge) => ['MATCHES', 'GAP'].includes(edge.relation));
    return {
      evidenceCount: 0,
      demonstratedSkills: matched.filter((edge) => edge.relation === 'MATCHES').length,
      requirements: requires.length,
      confidence: mean(confidencesOf([...requires, ...matched])),
    };
  }

  if (['project', 'experience', 'education', 'achievement', 'repository'].includes(group)) {
    const demonstrates = outgoing.filter((edge) => edge.relation === 'DEMONSTRATES');
    return {
      evidenceCount: demonstrates.length,
      demonstratedSkills: new Set(demonstrates.map((edge) => edge.target)).size,
      requirements: 0,
      confidence: mean(
        confidencesOf(
          index.incident.get(node.id)?.filter((edge) => edge.relation === 'EVIDENCED_BY') ?? [],
        ),
      ),
    };
  }

  // Evidence leaves: the candidate's material, a claim, or an interview record.
  const supports = incoming.filter((edge) => edge.relation === 'EVIDENCED_BY');
  const citedBy = incoming.filter((edge) => edge.relation === 'SUPPORTS');
  return {
    evidenceCount: supports.length + citedBy.length,
    demonstratedSkills: 0,
    requirements: 0,
    confidence: node.confidence ?? mean(confidencesOf(index.incident.get(node.id) ?? [])),
  };
}

export function factsForAll(
  index: GraphIndex,
  nodes: EvidenceGraphNode[],
): Map<string, NodeFactsResult> {
  return new Map(nodes.map((node) => [node.id, factsFor(index, node)]));
}

/* ── search: dim, never delete ─────────────────────────────────────────────── */

export interface SearchResult {
  /** The term actually searched for, lowercased and trimmed. Empty means "no search". */
  term: string;
  matched: Set<string>;
  /** Matched nodes plus their direct neighbours: the shape stays readable around a hit. */
  lit: Set<string>;
  dimmed: Set<string>;
}

function haystack(node: EvidenceGraphNode): string {
  const meta = node.meta ?? {};
  const parts = [
    node.label,
    node.group ?? '',
    node.type,
    String(meta['kind'] ?? ''),
    String(meta['category'] ?? ''),
    String(meta['filename'] ?? ''),
    String(meta['path'] ?? ''),
    String(
      meta['locator'] !== undefined && typeof meta['locator'] === 'object'
        ? Object.values(meta['locator'] as Record<string, unknown>).join(' ')
        : '',
    ),
    (meta['tech_stack'] as unknown[] | undefined)?.join(' ') ?? '',
  ];
  return parts.join(' ').toLowerCase();
}

/**
 * Search **dims** rather than removes.
 *
 * Deleting the non-matches would leave two nodes and no shape: the reader could no longer see
 * what the hit connects to, which is the only reason to search a graph rather than a list. So the
 * hits and their direct neighbours stay lit and everything else drops to a low-contrast state
 * that is still legible and still clickable.
 */
export function searchGraph(
  nodes: EvidenceGraphNode[],
  edges: EvidenceGraphEdge[],
  query: string,
): SearchResult {
  const term = query.trim().toLowerCase();
  const matched = new Set<string>();
  if (term) {
    for (const node of nodes) {
      if (haystack(node).includes(term)) matched.add(node.id);
    }
  }

  const lit = new Set(matched);
  if (term) {
    for (const edge of edges) {
      if (matched.has(edge.source)) lit.add(edge.target);
      if (matched.has(edge.target)) lit.add(edge.source);
    }
  }

  const dimmed = new Set<string>();
  if (term) {
    for (const node of nodes) if (!lit.has(node.id)) dimmed.add(node.id);
  }
  return { term, matched, lit, dimmed };
}

/** An edge is dimmed only when *both* ends are: a hit keeps its own connections visible. */
export function dimmedEdges(
  edges: EvidenceGraphEdge[],
  dimmed: Set<string>,
  term: string,
): Set<string> {
  const result = new Set<string>();
  if (!term) return result;
  for (const edge of edges) {
    if (dimmed.has(edge.source) && dimmed.has(edge.target)) result.add(edge.id);
  }
  return result;
}

/* ── the summary strip ─────────────────────────────────────────────────────── */

export interface RelationCount {
  relation: string;
  count: number;
}

export interface TypeCount {
  type: string;
  count: number;
}

export interface GraphSummary {
  nodes: number;
  edges: number;
  /** How many nodes actually carry a confidence value — the denominator of the mean. */
  withConfidence: number;
  /** `null` when not one node in the view has a confidence. Never `0`. */
  meanConfidence: number | null;
  relations: RelationCount[];
  types: TypeCount[];
  truncated: boolean;
  unresolved: number;
  totalsNodes: number;
  /**
   * Whole-graph nodes that the view does not show. Only labelled as *unconnected* when no edge
   * was dropped, which is what makes the claim provable from the payload rather than assumed.
   */
  hiddenNodes: number;
  hiddenAreUnconnected: boolean;
}

export function summarise(graph: EvidenceGraph): GraphSummary {
  const withConfidence = graph.nodes.filter((node) => node.confidence !== null).length;
  const relations = Object.entries(graph.stats.edges_by_relation ?? {})
    .map(([relation, count]) => ({ relation, count }))
    .sort((a, b) => b.count - a.count || a.relation.localeCompare(b.relation));
  const types = Object.entries(graph.stats.nodes_by_type ?? {})
    .map(([type, count]) => ({ type, count }))
    .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type));
  const hiddenNodes = Math.max(0, (graph.totals.nodes ?? 0) - (graph.stats.nodes ?? 0));
  return {
    nodes: graph.stats.nodes,
    edges: graph.stats.edges,
    withConfidence,
    meanConfidence: withConfidence > 0 ? graph.stats.mean_confidence : null,
    relations,
    types,
    truncated: graph.truncated,
    unresolved: graph.unresolvedNodeCount,
    totalsNodes: graph.totals.nodes ?? graph.stats.nodes,
    hiddenNodes,
    hiddenAreUnconnected: hiddenNodes > 0 && graph.totals.edges === graph.stats.edges,
  };
}

/**
 * The filter toggles, built from the **whole** graph's type counts.
 *
 * Building them from the current view's counts is the bug to avoid: switching a kind off would
 * remove its own toggle, and the reader could never switch it back on.
 */
export function filterOptions(graph: EvidenceGraph): {
  group: NodeGroup;
  label: string;
  types: GraphNodeType[];
  count: number;
}[] {
  const counts = graph.totals.nodes_by_type ?? {};
  return NODE_GROUPS.map((entry) => ({
    ...entry,
    count: entry.types.reduce((total, type) => total + (counts[type] ?? 0), 0),
  })).filter((entry) => entry.count > 0 || entry.group === 'candidate');
}

/* ── drawer derivations ────────────────────────────────────────────────────── */

export interface DrawerRelations {
  projects: EvidenceGraphNode[];
  experiences: EvidenceGraphNode[];
  repositories: EvidenceGraphNode[];
  skills: EvidenceGraphNode[];
  evidence: EvidenceGraphNode[];
  jobs: EvidenceGraphNode[];
}

/**
 * Who is connected to this node, and how.
 *
 * Direction matters. A skill's *sources* are the `EVIDENCED_BY` targets; the projects that back
 * it are the `DEMONSTRATES` sources; repositories sit either next to the skill or next to its
 * evidence. Nothing here reaches further than one hop in each of those directions, so the lists
 * are exactly what the canvas shows rather than a second, invisible query.
 */
export function relationsOf(index: GraphIndex, node: EvidenceGraphNode): DrawerRelations {
  const group = groupOf(node.type);
  const outgoing = index.outgoing.get(node.id) ?? [];
  const incoming = index.incoming.get(node.id) ?? [];
  const collect = (ids: string[]): EvidenceGraphNode[] => {
    const out: EvidenceGraphNode[] = [];
    const seen = new Set<string>();
    for (const id of ids) {
      const found = index.byId.get(id);
      if (found && !seen.has(id)) {
        seen.add(id);
        out.push(found);
      }
    }
    return out.sort((a, b) => a.label.localeCompare(b.label));
  };

  if (group === 'skill') {
    const sources = collect(
      outgoing.filter((edge) => edge.relation === 'EVIDENCED_BY').map((edge) => edge.target),
    );
    return {
      projects: collect(
        incoming.filter((edge) => edge.relation === 'DEMONSTRATES').map((edge) => edge.source),
      ),
      experiences: [],
      repositories: collect(
        sources
          .filter((source) => groupOf(source.type) === 'repository')
          .map((source) => source.id),
      ),
      skills: [],
      evidence: sources,
      jobs: collect(
        (index.incident.get(node.id) ?? [])
          .filter((edge) => ['REQUIRES', 'MATCHES', 'GAP'].includes(edge.relation))
          .map((edge) => (edge.source === node.id ? edge.target : edge.source)),
      ),
    };
  }

  if (group === 'evidence' || group === 'claim') {
    const skills = collect(
      incoming.filter((edge) => edge.relation === 'EVIDENCED_BY').map((edge) => edge.source),
    );
    const projects = new Set<string>();
    for (const skill of skills) {
      for (const edge of index.incoming.get(skill.id) ?? []) {
        if (edge.relation === 'DEMONSTRATES') projects.add(edge.source);
      }
    }
    const repositories = new Set<string>();
    for (const candidate of [...skills, ...neighboursOf(index, node.id)]) {
      if (groupOf(candidate.type) === 'repository') repositories.add(candidate.id);
    }
    return {
      projects: collect([...projects]),
      experiences: [],
      repositories: collect([...repositories]),
      skills,
      evidence: [],
      jobs: collect(
        skills.flatMap((skill) =>
          (index.incident.get(skill.id) ?? [])
            .filter((edge) => edge.relation === 'REQUIRES' || edge.relation === 'MATCHES')
            .map((edge) => (edge.source === skill.id ? edge.target : edge.source)),
        ),
      ),
    };
  }

  if (group === 'candidate') {
    return {
      projects: collect(neighboursOf(index, node.id, 'HAS').map((item) => item.id)),
      experiences: [],
      repositories: [],
      skills: collect(
        neighboursOf(index, node.id)
          .filter((item) => groupOf(item.type) === 'skill')
          .map((item) => item.id),
      ),
      evidence: [],
      jobs: collect(
        neighboursOf(index, node.id)
          .filter((item) => groupOf(item.type) === 'job')
          .map((item) => item.id),
      ),
    };
  }

  // project / experience / education / achievement / repository / job
  const skills = collect(
    (index.incident.get(node.id) ?? [])
      .filter((edge) => ['DEMONSTRATES', 'REQUIRES', 'MATCHES', 'GAP'].includes(edge.relation))
      .map((edge) => (edge.source === node.id ? edge.target : edge.source)),
  );
  const evidence = new Set<string>();
  for (const skill of skills) {
    for (const edge of index.outgoing.get(skill.id) ?? []) {
      if (edge.relation === 'EVIDENCED_BY') evidence.add(edge.target);
    }
  }
  return {
    projects: [],
    experiences: [],
    repositories: collect(
      neighboursOf(index, node.id)
        .filter((item) => groupOf(item.type) === 'repository')
        .map((item) => item.id),
    ),
    skills,
    evidence: collect([...evidence]),
    jobs: collect(
      neighboursOf(index, node.id)
        .filter((item) => groupOf(item.type) === 'job')
        .map((item) => item.id),
    ),
  };
}
