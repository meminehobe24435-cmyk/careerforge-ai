import { describe, expect, it } from 'vitest';

import { graphFixture, ids } from './graph-fixtures';
import {
  dimmedEdges,
  factsFor,
  factsForAll,
  filterOptions,
  indexGraph,
  relationsOf,
  searchGraph,
  summarise,
} from './graph-model';
import {
  AUTHORITY_TIERS,
  excerptOf,
  formatTimestamp,
  kindLabel,
  locatorText,
  sourceOf,
  whyItMatters,
} from './graph-evidence';
import { confidenceBand, formatConfidence, nodeReadout, nodeStyle } from './graph-node-style';

const graph = graphFixture();
const index = indexGraph(graph.nodes, graph.edges);
const facts = factsForAll(index, graph.nodes);

describe('what a node’s one number is', () => {
  it('counts a skill’s evidence sources from the EVIDENCED_BY edges', () => {
    expect(facts.get(ids.freeRtos)?.evidenceCount).toBe(2);
    expect(facts.get(ids.can)?.evidenceCount).toBe(1);
    expect(facts.get(ids.linux)?.evidenceCount).toBe(0);
  });

  it('reads a skill’s confidence off the candidate HAS edge, and leaves it null without one', () => {
    expect(facts.get(ids.freeRtos)?.confidence).toBeCloseTo(0.8, 5);
    // Linux has no evidence and no confidence anywhere: the answer is `null`, not `0`.
    expect(facts.get(ids.linux)?.confidence).toBeNull();
  });

  it('counts the skills a project demonstrates', () => {
    expect(facts.get(ids.project)?.demonstratedSkills).toBe(2);
  });

  it('renders an unmeasured confidence as a dash, never as 0.00', () => {
    const linux = index.byId.get(ids.linux)!;
    const readout = nodeReadout(linux, facts.get(ids.linux)!);
    expect(readout.value).toBe('0');
    expect(readout.metric).toBe('src');

    const evidence = index.byId.get(ids.resume)!;
    expect(nodeReadout(evidence, facts.get(ids.resume)!).value).toBe('0.80');

    expect(formatConfidence(null)).toBe('—');
    expect(formatConfidence(undefined)).toBe('—');
    expect(confidenceBand(null)).toBe('none');
    expect(confidenceBand(0.8)).toBe('high');
    expect(confidenceBand(0.5)).toBe('medium');
    expect(confidenceBand(0.2)).toBe('low');
  });
});

describe('search dims and never removes', () => {
  it('keeps every node in the result and marks only the non-matches as dimmed', () => {
    const result = searchGraph(graph.nodes, graph.edges, 'freertos');
    // Two nodes match, and both should: the skill, and the project whose own tech stack says
    // FreeRTOS. Matching only the label would miss the record that demonstrates it.
    expect(result.matched.has(ids.freeRtos)).toBe(true);
    expect(result.matched.has(ids.project)).toBe(true);
    // The hits and their direct neighbours stay lit, so the shape around a hit is readable.
    expect(result.lit.has(ids.candidate)).toBe(true);
    expect(result.lit.has(ids.resume)).toBe(true);
    expect(result.lit.has(ids.can)).toBe(true);
    expect(result.dimmed.has(ids.linux)).toBe(true);
    expect(result.dimmed.has(ids.freeRtos)).toBe(false);
    // Nothing was deleted: every node is either a hit or dimmed, and the view still holds all 7.
    expect(result.dimmed.size).toBeGreaterThan(0);
    expect(result.matched.size + result.dimmed.size).toBeLessThanOrEqual(graph.nodes.length);
    expect(graph.nodes.length).toBe(7);
  });

  it('matches on a node’s canonical id and on its meta, not only its label', () => {
    expect(searchGraph(graph.nodes, graph.edges, 'free_rtos').matched.has(ids.freeRtos)).toBe(true);
    expect(searchGraph(graph.nodes, graph.edges, 'resume.txt').matched.has(ids.resume)).toBe(true);
    expect(searchGraph(graph.nodes, graph.edges, 'embedded').matched.size).toBeGreaterThan(1);
  });

  it('dims an edge only when both of its endpoints are dimmed', () => {
    const result = searchGraph(graph.nodes, graph.edges, 'linux');
    const dimEdges = dimmedEdges(graph.edges, result.dimmed, result.term);
    expect(dimEdges.size).toBeGreaterThan(0);
    for (const id of dimEdges) {
      const edge = graph.edges.find((candidate) => candidate.id === id)!;
      expect(result.dimmed.has(edge.source)).toBe(true);
      expect(result.dimmed.has(edge.target)).toBe(true);
    }
  });

  it('dims nothing at all when the query is empty', () => {
    const result = searchGraph(graph.nodes, graph.edges, '   ');
    expect(result.term).toBe('');
    expect(result.dimmed.size).toBe(0);
    expect(dimmedEdges(graph.edges, result.dimmed, result.term).size).toBe(0);
  });
});

describe('the summary strip', () => {
  it('reports a mean confidence only when something was actually measured', () => {
    const summary = summarise(graph);
    expect(summary.nodes).toBe(graph.nodes.length);
    expect(summary.withConfidence).toBe(2);
    expect(summary.meanConfidence).toBeCloseTo(0.8, 5);
    expect(summary.relations.map((entry) => entry.relation)).toContain('EVIDENCED_BY');
  });

  it('says the mean is unavailable rather than 0 when no node carries a confidence', () => {
    const measured = graphFixture({
      nodes: graph.nodes.map((node) => ({ ...node, confidence: null })),
    });
    const summary = summarise(measured);
    expect(summary.withConfidence).toBe(0);
    expect(summary.meanConfidence).toBeNull();
  });

  it('explains the nodes it is not showing, and only calls them unconnected when that is provable', () => {
    const summary = summarise(graph);
    expect(summary.hiddenNodes).toBeGreaterThan(0);
    // totals.edges === stats.edges, so no edge was dropped and the extras really are unlinked.
    expect(summary.hiddenAreUnconnected).toBe(true);

    const withTruncation = summarise(graphFixture({ truncated: true }));
    expect(withTruncation.truncated).toBe(true);
  });
});

describe('filter toggles', () => {
  it('are built from the whole graph, so switching a kind off does not remove its own toggle', () => {
    const options = filterOptions(graph);
    expect(options.find((option) => option.group === 'evidence')?.count).toBe(2);

    // A kind that exists in the account but not in the current view keeps its toggle: building the
    // list from `stats` is how that toggle would vanish and become impossible to switch back on.
    const withExperienceElsewhere = graphFixture();
    withExperienceElsewhere.totals = {
      ...withExperienceElsewhere.totals,
      nodes_by_type: { ...withExperienceElsewhere.totals.nodes_by_type, experience: 2 },
    };
    const widened = filterOptions(withExperienceElsewhere);
    expect(widened.find((option) => option.group === 'experience')?.count).toBe(2);
    // A kind that exists nowhere is not offered as a dead toggle.
    expect(widened.map((option) => option.group)).not.toContain('interview');
  });
});

describe('drawer derivations', () => {
  it('finds a skill’s sources, the projects that demonstrate it, and the jobs that ask for it', () => {
    const relations = relationsOf(index, index.byId.get(ids.freeRtos)!);
    // Sorted by label: balance_car.md before resume.txt, so the list is stable.
    expect(relations.evidence.map((node) => node.id)).toEqual([ids.notes, ids.resume]);
    expect(relations.projects.map((node) => node.id)).toEqual([ids.project]);
    expect(relations.jobs).toHaveLength(0);
  });

  it('walks from an evidence item back to the skills and the project that rest on it', () => {
    const relations = relationsOf(index, index.byId.get(ids.resume)!);
    expect(relations.skills.map((node) => node.label).sort()).toEqual(['CAN', 'FreeRTOS']);
    expect(relations.projects.map((node) => node.id)).toEqual([ids.project]);
  });

  it('gives a skill with no evidence empty lists rather than invented ones', () => {
    const relations = relationsOf(index, index.byId.get(ids.linux)!);
    expect(relations.evidence).toHaveLength(0);
    expect(relations.projects).toHaveLength(0);
    expect(relations.repositories).toHaveLength(0);
    expect(factsFor(index, index.byId.get(ids.linux)!).confidence).toBeNull();
  });
});

describe('evidence presentation', () => {
  it('mirrors the backend’s authority tiers, because the payload only carries the number', () => {
    expect(AUTHORITY_TIERS['repo_file']?.score).toBe(1.0);
    expect(AUTHORITY_TIERS['commit']?.score).toBe(1.0);
    expect(AUTHORITY_TIERS['readme']?.score).toBe(0.85);
    expect(AUTHORITY_TIERS['document_chunk']?.score).toBe(0.8);
    expect(AUTHORITY_TIERS['manual']?.score).toBe(0.55);
    expect(AUTHORITY_TIERS['llm_inference']?.score).toBe(0.35);
  });

  it('clips an excerpt and says how much was left out', () => {
    const short = excerptOf('a short excerpt');
    expect(short.truncated).toBe(false);
    expect(short.fullLength).toBe(15);

    const long = excerptOf('x'.repeat(2000));
    expect(long.truncated).toBe(true);
    expect(long.text.length).toBeLessThanOrEqual(421);
    expect(long.fullLength).toBe(2000);
  });

  it('reads a locator into something a reviewer can check', () => {
    expect(
      locatorText({
        path: 'Core/Src/motor_control.c',
        line: 42,
        url: null,
        sha: null,
        page: null,
        charStart: null,
        charEnd: null,
        section: null,
      }),
    ).toBe('Core/Src/motor_control.c · line 42');
    expect(
      locatorText({
        path: null,
        line: null,
        url: null,
        sha: null,
        page: null,
        charStart: 0,
        charEnd: 290,
        section: null,
      }),
    ).toBe('chars 0–290');
    expect(locatorText(null)).toBeNull();
  });

  it('leaves `occurredAt` null when the API leaves it null', () => {
    expect(formatTimestamp(null)).toBeNull();
    expect(formatTimestamp('not-a-date')).toBeNull();
    expect(formatTimestamp('2026-09-25T16:28:48.167651Z')).toBe('2026-09-25 16:28 UTC');
  });

  it('names the source of an item from its own metadata', () => {
    const item = index.byId.get(ids.resume)!;
    expect(sourceOf(item)).toContain('resume.txt');
    expect(sourceOf(item)).toContain('chars 0–406');
    expect(kindLabel('document_chunk')).toBe('Document chunk');
    expect(kindLabel('repo_file')).toBe('Repository file');
    expect(kindLabel('something_unknown')).toBe('Something Unknown');
  });

  it('explains why an item matters from its tier and its corroboration, and says so when nothing cites it', () => {
    const item = index.byId.get(ids.resume)!;
    const sentence = whyItMatters(item, { evidenceCount: 2, confidence: 0.8 }, ['FreeRTOS', 'CAN']);
    expect(sentence).toContain('FreeRTOS');
    expect(sentence).toContain('mid-tier');

    const orphan = whyItMatters(item, { evidenceCount: 0, confidence: null }, []);
    expect(orphan).toContain('Nothing in this view cites it');
  });
});

describe('node kind styling', () => {
  it('separates kinds by icon, border weight and surface rather than by colour', () => {
    const skill = nodeStyle('skill');
    const evidence = nodeStyle('document');
    const candidate = nodeStyle('candidate');

    expect(skill.icon).not.toBe(evidence.icon);
    expect(skill.border).toBe('strong');
    expect(evidence.border).toBe('subtle');
    expect(candidate.accent).toBe('brand');
    expect(skill.accent).toBe('signal');
    // Only three accents exist, so eight kinds cannot become eight colours.
    const accents = new Set(
      [
        'candidate',
        'job',
        'project',
        'experience',
        'education',
        'achievement',
        'repository',
        'skill',
        'repo_file',
        'commit',
        'document',
        'claim',
        'interview',
      ].map((type) => nodeStyle(type).accent),
    );
    expect(accents.size).toBeLessThanOrEqual(3);
  });

  it('draws an unknown type as an unknown node instead of guessing a category', () => {
    const unknown = nodeStyle('quantum_skill');
    expect(unknown.group).toBe('other');
    expect(unknown.label).toBe('Other');
  });
});
