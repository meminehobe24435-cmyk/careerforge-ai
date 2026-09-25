import type {
  EvidenceDetail,
  EvidenceGraph,
  EvidenceGraphEdge,
  EvidenceGraphNode,
  EvidenceGraphStats,
  EvidenceTrace,
  Profile,
} from '@/lib/graph-api';

/**
 * Test fixtures shaped exactly like the live payloads.
 *
 * Copied from a real `GET /evidence-graph` on the phase-13 stack (32 nodes, 67 edges, six node
 * kinds) and then cut down to a readable miniature: candidate + 3 skills + 1 project + 2 document
 * chunks. Keeping the *shapes* — `meta.locator` nested snake_case, `confidence: null` on skills,
 * `edges_by_relation` in snake_case — is the point: a fixture that drifted from the wire format
 * would let the guards rot silently.
 *
 * Test-only. Nothing in the app imports this file.
 */

const CANDIDATE = '11111111-1111-5555-8111-111111111111';
const SKILL_FREERTOS = '22222222-2222-5555-8222-222222222222';
const SKILL_CAN = '33333333-3333-5555-8333-333333333333';
const SKILL_LINUX = '44444444-4444-5555-8444-444444444444';
const PROJECT_CAR = '55555555-5555-5555-8555-555555555555';
const EVIDENCE_RESUME = '66666666-6666-5555-8666-666666666666';
const EVIDENCE_NOTES = '77777777-7777-5555-8777-777777777777';

export const ids = {
  candidate: CANDIDATE,
  freeRtos: SKILL_FREERTOS,
  can: SKILL_CAN,
  linux: SKILL_LINUX,
  project: PROJECT_CAR,
  resume: EVIDENCE_RESUME,
  notes: EVIDENCE_NOTES,
};

const nodes: EvidenceGraphNode[] = [
  {
    id: CANDIDATE,
    type: 'candidate',
    label: 'Embedded & AI Application Engineer',
    confidence: null,
    group: null,
    meta: { slug: 'alex' },
  },
  {
    id: PROJECT_CAR,
    type: 'project',
    label: 'Balance Robot 2022',
    confidence: null,
    group: 'pb-1',
    meta: { role: '', tech_stack: ['STM32', 'FreeRTOS'] },
  },
  {
    id: SKILL_FREERTOS,
    type: 'skill',
    label: 'FreeRTOS',
    confidence: null,
    group: 'free_rtos',
    meta: { category: 'embedded', canonicalId: 'free_rtos' },
  },
  {
    id: SKILL_CAN,
    type: 'skill',
    label: 'CAN',
    confidence: null,
    group: 'can',
    meta: { category: 'embedded', canonicalId: 'can' },
  },
  {
    id: SKILL_LINUX,
    type: 'skill',
    label: 'Linux',
    confidence: null,
    group: 'linux',
    meta: { category: 'devops', canonicalId: 'linux' },
  },
  {
    id: EVIDENCE_RESUME,
    type: 'document',
    label: 'resume.txt',
    confidence: 0.8,
    group: null,
    meta: {
      kind: 'document_chunk',
      locator: { char_start: 0, char_end: 406 },
      filename: 'resume.txt',
      chunkIndex: 0,
      corroboration: 2,
    },
  },
  {
    id: EVIDENCE_NOTES,
    type: 'document',
    label: 'balance_car.md',
    confidence: 0.8,
    group: null,
    meta: {
      kind: 'document_chunk',
      locator: { char_start: 0, char_end: 290 },
      filename: 'balance_car.md',
      chunkIndex: 0,
      corroboration: 2,
    },
  },
];

const edges: EvidenceGraphEdge[] = [
  {
    id: 'e-has-project',
    source: CANDIDATE,
    target: PROJECT_CAR,
    relation: 'HAS',
    confidence: null,
    rationale: null,
  },
  {
    id: 'e-has-freertos',
    source: CANDIDATE,
    target: SKILL_FREERTOS,
    relation: 'HAS',
    confidence: 0.8,
    rationale: null,
  },
  {
    id: 'e-has-can',
    source: CANDIDATE,
    target: SKILL_CAN,
    relation: 'HAS',
    confidence: 0.8,
    rationale: null,
  },
  {
    id: 'e-has-linux',
    source: CANDIDATE,
    target: SKILL_LINUX,
    relation: 'HAS',
    confidence: null,
    rationale: null,
  },
  {
    id: 'e-demo-freertos',
    source: PROJECT_CAR,
    target: SKILL_FREERTOS,
    relation: 'DEMONSTRATES',
    confidence: 0.8,
    rationale: 'project mentions free_rtos',
  },
  {
    id: 'e-demo-can',
    source: PROJECT_CAR,
    target: SKILL_CAN,
    relation: 'DEMONSTRATES',
    confidence: 0.8,
    rationale: 'project mentions can',
  },
  {
    id: 'e-ev-freertos-a',
    source: SKILL_FREERTOS,
    target: EVIDENCE_RESUME,
    relation: 'EVIDENCED_BY',
    confidence: 0.8,
    rationale: 'from resume.txt',
  },
  {
    id: 'e-ev-freertos-b',
    source: SKILL_FREERTOS,
    target: EVIDENCE_NOTES,
    relation: 'EVIDENCED_BY',
    confidence: 0.8,
    rationale: 'from balance_car.md',
  },
  {
    id: 'e-ev-can-a',
    source: SKILL_CAN,
    target: EVIDENCE_RESUME,
    relation: 'EVIDENCED_BY',
    confidence: 0.8,
    rationale: 'from resume.txt',
  },
];

function statsFor(
  nodeList: EvidenceGraphNode[],
  edgeList: EvidenceGraphEdge[],
): EvidenceGraphStats {
  const nodesByType: Record<string, number> = {};
  for (const node of nodeList) nodesByType[node.type] = (nodesByType[node.type] ?? 0) + 1;
  const edgesByRelation: Record<string, number> = {};
  for (const edge of edgeList) {
    edgesByRelation[edge.relation] = (edgesByRelation[edge.relation] ?? 0) + 1;
  }
  const confidences = nodeList
    .map((node) => node.confidence)
    .filter((value): value is number => value !== null);
  return {
    nodes: nodeList.length,
    edges: edgeList.length,
    nodes_by_type: nodesByType,
    edges_by_relation: edgesByRelation,
    mean_confidence:
      confidences.length === 0
        ? 0
        : Math.round((confidences.reduce((a, b) => a + b, 0) / confidences.length) * 10000) / 10000,
    high_confidence: confidences.filter((value) => value >= 0.75).length,
    low_confidence: confidences.filter((value) => value < 0.45).length,
  };
}

export function graphFixture(overrides: Partial<EvidenceGraph> = {}): EvidenceGraph {
  const nodeList = overrides.nodes ?? nodes;
  const edgeList = overrides.edges ?? edges;
  return {
    nodes: nodeList,
    edges: edgeList,
    focus: null,
    depth: 2,
    truncated: false,
    nodeCount: nodeList.length,
    edgeCount: edgeList.length,
    stats: statsFor(nodeList, edgeList),
    // 127 nodes exist in the account (the taxonomy's skills, most unconnected); the read path
    // drops the unconnected ones, which is what `hiddenAreUnconnected` reports.
    totals: { ...statsFor([...nodeList, ...unconnectedSkills()], edgeList) },
    unresolvedNodeCount: 0,
    ...overrides,
  };
}

function unconnectedSkills(): EvidenceGraphNode[] {
  return Array.from({ length: 120 }, (_, index) => ({
    id: `unconnected-${index}`,
    type: 'skill',
    label: `Unused skill ${index}`,
    confidence: null,
    group: `unused_${index}`,
    meta: { category: 'tool' },
  }));
}

/** The demo account after a fresh seed: one candidate node, a taxonomy, and not one link. */
export function emptyGraphFixture(): EvidenceGraph {
  const nodeList: EvidenceGraphNode[] = [
    {
      id: CANDIDATE,
      type: 'candidate',
      label: 'Demo Candidate',
      confidence: null,
      group: null,
      meta: { slug: 'demo' },
    },
    ...unconnectedSkills(),
  ];
  return {
    nodes: [],
    edges: [],
    focus: null,
    depth: 2,
    truncated: false,
    nodeCount: 0,
    edgeCount: 0,
    stats: statsFor([], []),
    totals: statsFor(nodeList, []),
    unresolvedNodeCount: 0,
  };
}

export const evidenceItems: EvidenceDetail[] = [
  {
    id: EVIDENCE_RESUME,
    kind: 'document_chunk',
    title: 'resume.txt',
    snippet:
      '实习经历 某某科技 嵌入式软件实习生 2022-07 至 2022-12 使用 STM32 与 FreeRTOS 开发电机控制固件，负责 CAN 总线节点通信调试。',
    locator: {
      path: null,
      line: null,
      url: null,
      sha: null,
      page: null,
      charStart: 0,
      charEnd: 406,
      section: null,
    },
    confidence: 0.8,
    factors: {
      sourceAuthority: 0.8,
      recency: 1.0,
      specificity: 0.7,
      corroboration: 0.6,
      extractionQuality: 1.0,
      corroborationSources: 1,
      recomputed: 0.8,
      formulaVersion: 'confidence@1.0.0',
    },
    occurredAt: '2026-09-25T16:28:48.167651Z',
    documentChunkId: 'chunk-1',
    metadata: { filename: 'resume.txt', chunkIndex: 0 },
    citedByCount: 2,
  },
];

export const traceFixture: EvidenceTrace = {
  evidenceId: EVIDENCE_RESUME,
  citedBy: [
    {
      relation: 'EVIDENCED_BY',
      fromType: 'skill',
      fromId: SKILL_FREERTOS,
      rationale: '来自 resume.txt',
    },
    {
      relation: 'EVIDENCED_BY',
      fromType: 'skill',
      fromId: SKILL_CAN,
      rationale: '来自 resume.txt',
    },
  ],
};

export const profileFixture: Profile = {
  id: 'p-1',
  slug: 'alex',
  headline: 'Embedded & AI Application Engineer',
  summary: '',
  yearsExperience: 3,
  projects: [],
  skills: [
    {
      canonicalId: 'free_rtos',
      displayName: 'FreeRTOS',
      category: 'embedded',
      level: 'strong',
      evidenceCount: 2,
      evidenceScore: 0.8,
      isTarget: false,
      origin: 'import',
    },
  ],
};
