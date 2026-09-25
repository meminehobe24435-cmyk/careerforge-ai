import { describe, expect, it } from 'vitest';

import { MAX_ROWS_PER_LANE, NODE_HEIGHT, layoutGraph, levelOf, readingOrder } from './graph-layout';

/**
 * The layout is graded on read ability, but the property that can be *tested* is determinism:
 * the same data must produce the same coordinates, or a graph is a thing you cannot point at in a
 * conversation. The readability claims are asserted as invariants instead — one band per level,
 * a bounded number of rows per lane, evidence to the right of skills.
 */

function node(id: string, type: string, label = id, weight = 0) {
  return { id, type, label, weight };
}

describe('the layered layout', () => {
  it('puts the candidate left of projects, projects left of skills, skills left of evidence', () => {
    const layout = layoutGraph([
      node('c', 'candidate'),
      node('p', 'project'),
      node('s', 'skill'),
      node('e', 'document'),
    ]);

    const x = (id: string) => layout.placements.get(id)?.x ?? -1;
    expect(x('c')).toBeLessThan(x('p'));
    expect(x('p')).toBeLessThan(x('s'));
    expect(x('s')).toBeLessThan(x('e'));
  });

  it('is deterministic, and does not depend on the order the API returned the nodes in', () => {
    const nodes = [
      node('a', 'skill', 'Alpha'),
      node('b', 'skill', 'Beta'),
      node('c', 'candidate'),
      node('d', 'project', 'Delta'),
      node('e', 'document', 'Evidence'),
    ];
    const first = layoutGraph(nodes);
    const second = layoutGraph([...nodes].reverse());
    const third = layoutGraph([...nodes].sort((left, right) => right.id.localeCompare(left.id)));

    for (const id of ['a', 'b', 'c', 'd', 'e']) {
      expect(second.placements.get(id)).toEqual(first.placements.get(id));
      expect(third.placements.get(id)).toEqual(first.placements.get(id));
    }
    expect(readingOrder(second.placements)).toEqual(readingOrder(first.placements));
  });

  it('wraps a level into lanes instead of growing one column of 22 nodes', () => {
    const skills = Array.from({ length: 22 }, (_, index) =>
      node(`s${index}`, 'skill', `Skill ${index}`),
    );
    const layout = layoutGraph([node('c', 'candidate'), ...skills]);

    const band = layout.bands.find((entry) => entry.title === 'Skills');
    expect(band?.count).toBe(22);
    expect(band?.lanes).toBe(Math.ceil(22 / MAX_ROWS_PER_LANE));

    // Height is bounded by one lane, not by the node count.
    expect(layout.height).toBeLessThanOrEqual(MAX_ROWS_PER_LANE * (NODE_HEIGHT + 40));
    // The graph stays wide-and-short: a 22-node column would be ~2000px tall and unreadable at
    // any zoom that still shows the node labels.
    expect(layout.width).toBeGreaterThan(layout.height);
  });

  it('centres every band on one axis so the flow reads through the middle', () => {
    const layout = layoutGraph([
      node('c', 'candidate'),
      ...Array.from({ length: 9 }, (_, index) => node(`s${index}`, 'skill')),
      node('e', 'document'),
    ]);
    const candidate = layout.placements.get('c');
    const centre = (layout.height - NODE_HEIGHT) / 2;
    expect(candidate?.y).toBeCloseTo(centre, 5);
  });

  it('gives a level with no nodes no space at all', () => {
    const withJob = layoutGraph([node('c', 'candidate'), node('j', 'job')]);
    const without = layoutGraph([node('c', 'candidate')]);
    expect(without.width).toBeLessThan(withJob.width);
    expect(without.bands).toHaveLength(1);
  });

  it('orders the reading path left to right, then top to bottom', () => {
    const layout = layoutGraph([
      node('c', 'candidate'),
      node('s1', 'skill', 'One'),
      node('s2', 'skill', 'Two'),
      node('e', 'document'),
    ]);
    const order = readingOrder(layout.placements);
    expect(order[0]).toBe('c');
    expect(order[order.length - 1]).toBe('e');
    expect(order.indexOf('s1')).toBeLessThan(order.indexOf('e'));
  });

  it('maps every documented node type onto a level, including ones it has never seen', () => {
    expect(levelOf('candidate')).toBe(0);
    expect(levelOf('project')).toBe(1);
    expect(levelOf('experience')).toBe(1);
    expect(levelOf('skill')).toBe(2);
    expect(levelOf('document')).toBe(3);
    expect(levelOf('job')).toBe(4);
    // A kind the page does not know yet is placed last rather than dropped.
    expect(levelOf('something_new')).toBe(4);
  });
});
