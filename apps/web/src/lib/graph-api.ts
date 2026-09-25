import { ApiError } from '@careerforge/shared';

import { API_BASE_URL, api } from './api';

/**
 * Reads for the Career Evidence Graph (`docs/API.md` §2.5).
 *
 * Why this is its own module rather than another entry in `lib/api.ts`: the envelope types and
 * their guards for `/evidence*` do not exist in `@careerforge/shared` yet, and a page that ships
 * a graph must not ship an unvalidated one. Every response is checked here before it reaches the
 * canvas, and a shape that disagrees with the API is refused with `INVALID_RESPONSE` naming the
 * field that was expected — the same contract `lib/api.ts` keeps for the endpoints it owns.
 *
 * Requests go through `api.get` / `api.request` so this shares one client: same base URL, same
 * bearer token, same `requestId` correlation, same `ApiError` on failure.
 */

/* ── node kinds and relations, as the API defines them ─────────────────────── */

export const GRAPH_NODE_TYPES = [
  'candidate',
  'education',
  'experience',
  'project',
  'achievement',
  'repository',
  'repo_file',
  'commit',
  'document',
  'skill',
  'claim',
  'job',
  'interview',
] as const;

export type GraphNodeType = (typeof GRAPH_NODE_TYPES)[number];

/** `careerforge_ai.schemas.common.EvidenceRelation` — the wire carries the name verbatim. */
export const EVIDENCE_RELATIONS = [
  'HAS',
  'DEMONSTRATES',
  'EVIDENCED_BY',
  'SUPPORTS',
  'REQUIRES',
  'MATCHES',
  'GAP',
  'DERIVED_FROM',
] as const;

export type EvidenceRelation = (typeof EVIDENCE_RELATIONS)[number];

export const EVIDENCE_KINDS = [
  'repo_file',
  'commit',
  'readme',
  'document_chunk',
  'experience',
  'project',
  'achievement',
  'manual',
  'llm_inference',
] as const;

export interface EvidenceGraphNode {
  id: string;
  type: string;
  label: string;
  /** `null` means *no confidence was computed* — never render it as `0`. */
  confidence: number | null;
  group: string | null;
  meta: Record<string, unknown>;
}

export interface EvidenceGraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  confidence: number | null;
  rationale: string | null;
}

export interface EvidenceGraphStats {
  nodes: number;
  edges: number;
  /** snake_case on the wire: `graph_stats` returns a plain dict (`docs/API.md` §2.5). */
  nodes_by_type: Record<string, number>;
  edges_by_relation: Record<string, number>;
  mean_confidence: number;
  high_confidence: number;
  low_confidence: number;
}

export interface EvidenceGraph {
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
  focus: string | null;
  depth: number;
  truncated: boolean;
  nodeCount: number;
  edgeCount: number;
  /** What this response contains. */
  stats: EvidenceGraphStats;
  /** The whole graph — the two must never be confused in one sentence. */
  totals: EvidenceGraphStats;
  unresolvedNodeCount: number;
}

export interface EvidenceLocator {
  path: string | null;
  line: number | null;
  url: string | null;
  sha: string | null;
  page: number | null;
  charStart: number | null;
  charEnd: number | null;
  section: string | null;
}

export interface ConfidenceFactors {
  sourceAuthority: number;
  recency: number;
  specificity: number;
  corroboration: number;
  extractionQuality: number;
  corroborationSources: number;
  recomputed: number;
  formulaVersion: string;
}

export interface EvidenceItem {
  id: string;
  kind: string;
  title: string;
  snippet: string;
  locator: EvidenceLocator;
  confidence: number;
  factors: ConfidenceFactors | null;
  occurredAt: string | null;
  documentChunkId: string | null;
  metadata: Record<string, unknown>;
}

export interface EvidenceDetail extends EvidenceItem {
  citedByCount: number;
}

export interface EvidenceTraceEntry {
  relation: string;
  fromType: string;
  fromId: string;
  rationale: string | null;
}

export interface EvidenceTrace {
  evidenceId: string;
  citedBy: EvidenceTraceEntry[];
}

export interface ProfileSkill {
  canonicalId: string;
  displayName: string;
  category: string;
  level: string;
  evidenceCount: number;
  evidenceScore: number;
  isTarget: boolean;
  origin: string;
}

export interface ProfileProject {
  id: string | null;
  name: string;
  role: string | null;
  summary: string;
  description: string;
  techStack: string[];
  links: Record<string, string>;
  evidenceStrength: number;
  origin: string;
}

export interface Profile {
  id: string | null;
  slug: string | null;
  headline: string;
  summary: string;
  yearsExperience: number | null;
  projects: ProfileProject[];
  skills: ProfileSkill[];
}

export interface ImportOutcome {
  counts: Record<string, number>;
  skillsNormalised: Record<string, string>;
  unmappedSkills: string[];
  warnings: string[];
  degraded: boolean;
}

/* ── guards ────────────────────────────────────────────────────────────────── */

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isFiniteNumberOrNull(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isFinite(value));
}

function isNode(value: unknown): value is EvidenceGraphNode {
  if (!isRecord(value)) return false;
  return (
    typeof value['id'] === 'string' &&
    typeof value['type'] === 'string' &&
    typeof value['label'] === 'string' &&
    isFiniteNumberOrNull(value['confidence']) &&
    (value['group'] === null || typeof value['group'] === 'string')
  );
}

function isEdge(value: unknown): value is EvidenceGraphEdge {
  if (!isRecord(value)) return false;
  return (
    typeof value['id'] === 'string' &&
    typeof value['source'] === 'string' &&
    typeof value['target'] === 'string' &&
    typeof value['relation'] === 'string' &&
    isFiniteNumberOrNull(value['confidence'])
  );
}

function isStats(value: unknown): value is EvidenceGraphStats {
  if (!isRecord(value)) return false;
  return (
    typeof value['nodes'] === 'number' &&
    typeof value['edges'] === 'number' &&
    typeof value['mean_confidence'] === 'number' &&
    isRecord(value['nodes_by_type']) &&
    isRecord(value['edges_by_relation'])
  );
}

export function isEvidenceGraph(value: unknown): value is EvidenceGraph {
  if (!isRecord(value)) return false;
  const nodes = value['nodes'];
  const edges = value['edges'];
  if (!Array.isArray(nodes) || !nodes.every(isNode)) return false;
  if (!Array.isArray(edges) || !edges.every(isEdge)) return false;
  return isStats(value['stats']) && isStats(value['totals']);
}

function isLocator(value: unknown): boolean {
  return value === undefined || isRecord(value);
}

function isEvidenceItem(value: unknown): value is EvidenceItem {
  if (!isRecord(value)) return false;
  return (
    typeof value['id'] === 'string' &&
    typeof value['kind'] === 'string' &&
    typeof value['title'] === 'string' &&
    typeof value['confidence'] === 'number' &&
    isLocator(value['locator'])
  );
}

export function isEvidenceList(value: unknown): value is { items: EvidenceItem[]; total: number } {
  if (!isRecord(value)) return false;
  const items = value['items'];
  return Array.isArray(items) && items.every(isEvidenceItem) && typeof value['total'] === 'number';
}

export function isEvidenceDetail(value: unknown): value is EvidenceDetail {
  return isEvidenceItem(value);
}

export function isEvidenceTrace(value: unknown): value is EvidenceTrace {
  if (!isRecord(value)) return false;
  const citedBy = value['citedBy'];
  return (
    typeof value['evidenceId'] === 'string' &&
    Array.isArray(citedBy) &&
    citedBy.every(
      (entry) =>
        isRecord(entry) &&
        typeof entry['relation'] === 'string' &&
        typeof entry['fromId'] === 'string',
    )
  );
}

export function isProfile(value: unknown): value is Profile {
  if (!isRecord(value)) return false;
  return (
    typeof value['headline'] === 'string' &&
    Array.isArray(value['skills']) &&
    Array.isArray(value['projects'])
  );
}

export function isImportOutcome(value: unknown): value is ImportOutcome {
  if (!isRecord(value)) return false;
  return isRecord(value['counts']) && Array.isArray(value['warnings']);
}

export function invalidResponse(path: string, expectation: string, body: unknown): ApiError {
  return new ApiError({
    code: 'INVALID_RESPONSE',
    message: `${path} 返回的结构与 docs/API.md §2.5 不一致（${expectation}）`,
    requestId: null,
    status: 200,
    body,
  });
}

/* ── reads ─────────────────────────────────────────────────────────────────── */

export interface GraphQuery {
  /** `skill:stm32`, `project:<uuid>` or a raw node id — resolved leniently by the API. */
  focus?: string | null;
  depth?: number;
  types?: string[];
  minConfidence?: number;
  limit?: number;
}

/**
 * The request a view came from, as the page prints it under its title.
 *
 * Built from the parameters that were actually sent, so the line above the canvas and the request
 * behind it cannot disagree: a reader who wants to check a number can copy the URL, and one who
 * wonders why the picture is small can see the `depth` or `types` that caused it.
 */
export function evidenceGraphUrl(query: GraphQuery): string {
  const parts: string[] = [];
  if (query.focus) {
    parts.push(`focus=${query.focus}`);
    parts.push(`depth=${query.depth ?? 2}`);
  }
  if (query.types && query.types.length > 0) parts.push(`types=${query.types.join(',')}`);
  if (query.minConfidence) parts.push(`minConfidence=${query.minConfidence}`);
  return `GET ${API_BASE_URL}/evidence-graph${parts.length > 0 ? `?${parts.join('&')}` : ''}`;
}

export async function fetchEvidenceGraph(query: GraphQuery = {}): Promise<EvidenceGraph> {
  const data = await api.get<unknown>('/evidence-graph', {
    query: {
      focus: query.focus ?? undefined,
      depth: query.depth,
      types: query.types && query.types.length > 0 ? query.types.join(',') : undefined,
      minConfidence: query.minConfidence,
      limit: query.limit,
    },
  });
  if (!isEvidenceGraph(data)) {
    throw invalidResponse('GET /evidence-graph', '缺少 nodes/edges 或 stats/totals', data);
  }
  return data;
}

export async function fetchEvidenceList(
  params: { kind?: string; minConfidence?: number; limit?: number } = {},
): Promise<EvidenceItem[]> {
  const data = await api.get<unknown>('/evidence', {
    query: { kind: params.kind, minConfidence: params.minConfidence, limit: params.limit ?? 200 },
  });
  if (!isEvidenceList(data)) {
    throw invalidResponse('GET /evidence', '缺少 items/total 或某条证据缺少 id/kind/title', data);
  }
  return data.items;
}

export async function fetchEvidenceDetail(id: string): Promise<EvidenceDetail> {
  const data = await api.get<unknown>(`/evidence/${encodeURIComponent(id)}`);
  if (!isEvidenceDetail(data)) {
    throw invalidResponse('GET /evidence/{id}', '缺少 id/kind/title/confidence', data);
  }
  return data;
}

export async function fetchEvidenceTrace(id: string): Promise<EvidenceTrace> {
  const data = await api.get<unknown>(`/evidence/${encodeURIComponent(id)}/trace`);
  if (!isEvidenceTrace(data)) {
    throw invalidResponse('GET /evidence/{id}/trace', '缺少 citedBy', data);
  }
  return data;
}

export async function fetchProfile(): Promise<Profile> {
  const data = await api.get<unknown>('/profile');
  if (!isProfile(data)) {
    throw invalidResponse('GET /profile', '缺少 headline/skills/projects', data);
  }
  return data;
}
