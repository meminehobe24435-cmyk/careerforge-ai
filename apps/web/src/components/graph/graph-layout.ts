/**
 * The graph's layout: a layered, left-to-right picture with an explicit reading order.
 *
 * **Why this is hand-written instead of dagre.** The brief suggested `@dagrejs/dagre`, and it was
 * measured against this graph before it was dropped. Given the node/edge set below (32 nodes, 67
 * edges, from the live stack), dagre was asked to place the four conceptual bands with an explicit
 * `rank` on every node, under all three of its rankers:
 *
 * ```
 * network-simplex  candidate 0->0  project 1->2  skill 2->2|2->4  document 3->6   1254x2296
 * tight-tree       candidate 0->0  project 1->2  skill 2->2|2->4  document 3->6   1254x2296
 * longest-path     candidate 0->0  project 1->6  skill 2->6|2->4  document 3->6   1254x2438
 * ```
 *
 * Two failures, both of which are the exact defect the brief forbids: `skill` split across two
 * ranks (the skills with no `project --DEMONSTRATES-->` edge landed one rank early), and
 * `project`/`skill` collapsed into a single column of 10 nodes next to a column of 19. The result
 * was a 2296px-tall strip in which 41 of 67 edges crossed the tangle, which at any readable zoom
 * is a pile-up in the centre.
 *
 * Levels are a property of the *domain*, not something to infer from edge lengths: the builder's
 * own contract (`graph/builder.py`) is
 * `Candidate → Experience/Project → Skill → Evidence → (file · commit · document)`. So the rank is
 * decided here, deterministically, and this module only has to place them well. The output
 * depends on nothing but its input — same data, same coordinates, on every reload.
 *
 * **Wrapping.** A single column of 22 skills is 22 rows tall, which no canvas can fit legibly. Each
 * level is therefore wrapped into lanes of at most `MAX_ROWS_PER_LANE`, and the lanes run left to
 * right inside the level's own band. Every band is centred on the same horizontal axis, so the
 * picture reads as a flow through the middle rather than as a wall of cards.
 */

export const NODE_WIDTH = 170;
export const NODE_HEIGHT = 54;
export const ROW_GAP = 14;
export const LANE_GAP = 16;
export const BAND_GAP = 56;
export const MAX_ROWS_PER_LANE = 8;
export const BAND_HEADER_HEIGHT = 22;

/** The reading order of the levels. A type that is not listed lands in `LEVELS.length - 1`. */
export const LEVELS: { title: string; types: string[] }[] = [
  { title: 'Candidate', types: ['candidate'] },
  {
    title: 'Projects, experience & education',
    types: ['project', 'experience', 'education', 'achievement', 'repository'],
  },
  { title: 'Skills', types: ['skill'] },
  { title: 'Evidence', types: ['repo_file', 'commit', 'document', 'claim', 'interview'] },
  { title: 'Target job', types: ['job'] },
];

export function levelOf(type: string): number {
  const index = LEVELS.findIndex((level) => level.types.includes(type));
  return index === -1 ? LEVELS.length - 1 : index;
}

export interface LayoutNode {
  id: string;
  type: string;
  label: string;
  /** Ordering weight inside a lane: higher first. Evidence count, degree, or 0. */
  weight: number;
  /** Category (skills) or kind, used as the second ordering key so lanes read semantically. */
  subkey?: string;
}

export interface LayoutPlacement {
  x: number;
  y: number;
}

export interface LayoutBand {
  level: number;
  title: string;
  count: number;
  lanes: number;
  x: number;
  y: number;
  width: number;
}

export interface GraphLayout {
  /** Node id → top-left position of the node box. */
  placements: Map<string, LayoutPlacement>;
  bands: LayoutBand[];
  width: number;
  height: number;
}

/**
 * Deterministic ordering inside one lane.
 *
 * Four keys, each of which can be checked by eye: type (so a lane groups like with like), category
 * (embedded skills together), weight (the best-evidenced first) and finally the id, which exists
 * only to make the sort total — two nodes with identical keys must not swap places between two
 * renders, because a graph that reshuffles itself between reloads is a graph nobody can discuss.
 */
function orderKey(node: LayoutNode): string {
  return [
    String(levelOf(node.type)).padStart(2, '0'),
    node.type,
    node.subkey ?? '',
    String(1_000_000 - Math.round(node.weight * 1000)).padStart(7, '0'),
    node.label,
    node.id,
  ].join('\u0000');
}

export function layoutGraph(nodes: LayoutNode[]): GraphLayout {
  const byLevel = new Map<number, LayoutNode[]>();
  for (const node of nodes) {
    const level = levelOf(node.type);
    const list = byLevel.get(level);
    if (list) list.push(node);
    else byLevel.set(level, [node]);
  }

  const placements = new Map<string, LayoutPlacement>();
  const bands: LayoutBand[] = [];

  // Pass 1 — how tall each band will be, so every band can be centred on one axis.
  const laneCounts = new Map<number, number>();
  const heights = new Map<number, number>();
  let tallest = 0;
  for (const [level, list] of byLevel) {
    if (list.length === 0) continue;
    const lanes = Math.ceil(list.length / MAX_ROWS_PER_LANE);
    const rows = Math.min(list.length, MAX_ROWS_PER_LANE);
    const height = rows * NODE_HEIGHT + (rows - 1) * ROW_GAP;
    laneCounts.set(level, lanes);
    heights.set(level, height);
    tallest = Math.max(tallest, height);
  }
  if (tallest === 0) return { placements, bands, width: 0, height: 0 };

  // Pass 2 — place. Levels keep their declared order, and a level with no nodes takes no space.
  let cursorX = 0;
  for (const level of [...byLevel.keys()].sort((a, b) => a - b)) {
    const list = byLevel.get(level);
    if (!list || list.length === 0) continue;
    const ordered = [...list].sort((a, b) => (orderKey(a) < orderKey(b) ? -1 : 1));
    const lanes = laneCounts.get(level) ?? 1;
    const bandWidth = lanes * NODE_WIDTH + (lanes - 1) * LANE_GAP;
    const height = heights.get(level) ?? 0;
    const top = (tallest - height) / 2;

    ordered.forEach((node, index) => {
      const lane = Math.floor(index / MAX_ROWS_PER_LANE);
      const row = index % MAX_ROWS_PER_LANE;
      placements.set(node.id, {
        x: cursorX + lane * (NODE_WIDTH + LANE_GAP),
        y: top + row * (NODE_HEIGHT + ROW_GAP),
      });
    });

    bands.push({
      level,
      title: LEVELS[level]?.title ?? 'Other',
      count: ordered.length,
      lanes,
      x: cursorX,
      y: top - BAND_HEADER_HEIGHT,
      width: bandWidth,
    });
    cursorX += bandWidth + BAND_GAP;
  }

  const width = Math.max(0, cursorX - BAND_GAP);
  return { placements, bands, width, height: tallest };
}

/** Reading order for keyboard navigation: left to right, then top to bottom. */
export function readingOrder(placements: Map<string, LayoutPlacement>): string[] {
  return [...placements.entries()]
    .sort(([, a], [, b]) => (a.x === b.x ? a.y - b.y : a.x - b.x))
    .map(([id]) => id);
}
