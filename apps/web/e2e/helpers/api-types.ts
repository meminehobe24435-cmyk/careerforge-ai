/**
 * The wire shapes these specs assert against, mirroring `docs/API.md` §2.
 *
 * Kept apart from `api.ts` (the client) so each file has one reason to change: this one when the
 * contract moves, that one when the calls do. The types are declarative on purpose — they describe
 * what the API sends, not what the UI happens to read, so a spec can assert on a field the UI has
 * not rendered yet.
 *
 * Only the fields these specs actually use are declared. A field that is absent here is not a claim
 * that it is absent from the payload.
 */

/** Every response is enveloped (`docs/API.md` §1.1). */
export interface Envelope<T> {
  success: boolean;
  data: T | null;
  error: { code: string; message: string; details?: unknown } | null;
  requestId: string;
}

export interface DemoUser {
  id: string;
  email: string;
  displayName: string;
  isDemo?: boolean;
}

/** `data` of `POST /auth/demo` — also the shape the browser stores in `localStorage`. */
export interface SessionPayload {
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
  user: DemoUser;
}

export interface DashboardStats {
  evidenceCoverage: number;
  skillCoverage: number;
  resumeMatch: number;
  applications: number;
  interviews: number;
  offers: number;
}

export interface DashboardRecentJob {
  jobId: string;
  company: string | null;
  role: string;
  matchScore: number | null;
  status: string;
}

export interface DashboardResponse {
  stats: DashboardStats;
  profileStrength: { score: number | null; delta7d: number | null };
  recentJobs: DashboardRecentJob[];
  nextActions: Array<{ type: string; title: string; at: string }>;
  meta?: {
    tookMs?: number;
    cacheHit?: boolean;
    unavailable?: Record<string, string>;
    definitions?: Record<string, string>;
  };
}

export interface JobRequirement {
  canonicalId: string | null;
  rawText: string;
  requirement: string;
  weight: number;
  jdEvidence: string;
  mentions: number;
}

export interface JobDetail {
  id: string;
  company: string | null;
  role: string;
  requiredCount: number;
  preferredCount: number;
  bonusCount: number;
  matchScore: number | null;
  parseStatus: string;
  parseConfidence: number;
  skills: JobRequirement[];
}

export interface SkillTree {
  jobId: string;
  role: string;
  company: string | null;
  required: JobRequirement[];
  preferred: JobRequirement[];
  bonus: JobRequirement[];
  unmatchedCount: number;
}

export interface MatchedSkill {
  canonicalId: string;
  displayName: string;
  requirement: string;
  userLevel: string;
  evidenceCount: number;
  confidence: number;
  reason: string;
}

export interface MissedSkill {
  canonicalId: string;
  displayName: string;
  requirement: string;
  severity: string;
  jdEvidence?: string;
}

export interface MatchResult {
  jobId: string;
  score: number;
  dimensions: Record<
    string,
    { key: string; label: string; score: number; weight: number; weighted: number }
  >;
  strengths: MatchedSkill[];
  gaps: MissedSkill[];
  unknowns: Array<{
    canonicalId: string;
    displayName: string;
    requirement: string;
    reason: string;
    askUser: string;
  }>;
  evidenceCoverage: number;
  confidence: number;
  degraded: boolean;
  narrative: string;
  warnings: string[];
  why: {
    formula: string;
    algorithmVersion: string;
    evidenceUsed: string[];
    notes: string[];
    computedAt: string | null;
  };
}

export interface DocumentAccepted {
  documentId: string;
  taskId: string;
  status: string;
  streamUrl: string;
  deduplicated: boolean;
}

export interface TaskStatus {
  taskId: string;
  kind: string;
  status: string;
  progress: number;
  stage: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  attempts: number;
}

export interface DocumentAnalysis {
  documentId: string;
  evidenceCreated: number;
  evidenceUpdated: number;
  linksWritten: number;
  skillCount: number;
  nodeCount: number;
  edgeCount: number;
  meanConfidence: number;
  warnings: string[];
}

export interface EvidenceRow {
  id: string;
  kind: string;
  title: string;
  snippet: string;
  locator: Record<string, unknown>;
  confidence: number;
  factors: { sourceAuthority: number; corroborationSources: number; recomputed: number } | null;
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  confidence: number | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  relation: string;
  confidence: number | null;
}

export interface EvidenceGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  focus: string | null;
  depth: number;
  truncated: boolean;
  nodeCount: number;
  edgeCount: number;
  stats: Record<string, unknown>;
  totals: Record<string, unknown>;
  unresolvedNodeCount: number;
}

export interface ClaimReason {
  rule: string;
  severity: string;
  message: string;
}

export interface ClaimValidation {
  status: 'supported' | 'partially_supported' | 'unsupported' | 'contradicted';
  confidence: number;
  allows_resume_inclusion: boolean;
  is_blocking: boolean;
  reasons: ClaimReason[];
  unknowns: string[];
  independent_source_count: number;
  /** Retrieval hits. Empty on this deployment: see `Capabilities.retrieval_available`. */
  sources: unknown[];
  meta: { provider: string; degraded: boolean; workflow: string | null };
}

export interface InterviewQuestion {
  turn_index: number;
  content: string;
  topic: string | null;
  level: string | null;
}

export interface InterviewTurn extends InterviewQuestion {
  role: string;
  /**
   * Per-answer score. `null` on interviewer turns and on turns that were never scored.
   *
   * `GET /ai/interview/{id}` returns only the score per turn (see `_session_payload`); the full
   * evaluation of a turn comes from the `answer` response and is not persisted, which is why the
   * page's evaluation panel says so after a refresh.
   */
  score: number | null;
}

export interface InterviewEvaluation {
  turn_index: number;
  score: number;
  technical_accuracy: number;
  depth: number;
  communication: number;
  problem_solving: number;
  engineering_thinking: number;
  confidence: number;
  feedback: string;
  strong_points: string[];
  follow_up_topics: string[];
  missing_knowledge: string[];
}

export interface InterviewSession {
  session_id: string;
  mode: string;
  status: string;
  current_level: string;
  plan: Array<{
    topic: string;
    label: string;
    target_level: string;
    reason: string;
    source: string;
    covered: boolean;
  }>;
  turns: InterviewTurn[];
  scorecard: Record<string, unknown> | null;
}

export interface InterviewTurnResult {
  session_id: string;
  status: string;
  current_level: string;
  evaluation: InterviewEvaluation | null;
  difficulty_change: { from_level: string; to_level: string; reason: string } | null;
  next_question: InterviewQuestion | null;
}

export interface AiRun {
  id: string;
  agent: string;
  workflow: string;
  model: string | null;
  provider: string | null;
  status: string;
  stepCount: number;
  totalTokens: number;
  costUsd: number;
  latencyMs: number | null;
  cacheHit: boolean;
  startedAt: string;
}

export interface AiRunDetail extends AiRun {
  steps: Array<{
    name: string;
    status: string;
    latencyMs: number | null;
    provider: string | null;
    attempts: number;
    cacheHit: boolean;
    tokens: number;
    inputDigest: string;
    outputDigest: string;
    errorCode: string | null;
  }>;
  calls: Array<{
    id: string;
    operation: string;
    provider: string;
    model: string;
    totalTokens: number;
    costUsd: number;
    latencyMs: number | null;
    createdAt: string;
  }>;
}

export interface Capabilities {
  provider: string;
  provider_chain: string[];
  degraded: boolean;
  retrieval_available: boolean;
  session_store: string;
  limitations: string[];
}

export interface PublicSkill {
  canonicalId: string;
  displayName: string;
  category: string;
  confidence: number;
  evidenceCount: number;
  corroboration: number;
}

export interface PublicCandidate {
  displayName: string;
  headline: string;
  summary: string;
  skills: PublicSkill[];
  projects: Array<{ name: string; summary: string; techStack: string[] }>;
  highlights: string[];
  interviewTopics: string[];
  meta: {
    slug: string;
    evidenceCoverage: number;
    profileStrength: number;
    hiddenSections: string[];
    viewCount: number;
  };
}

export interface PublicEvidence {
  evidenceId: string;
  title: string;
  kind: string;
  locator: string;
  url: string | null;
  confidence: number;
}

/** The result of a document upload plus the analysis that turns it into evidence. */
export interface EvidenceSetup {
  documentId: string;
  deduplicated: boolean;
  analysis: DocumentAnalysis;
}

/**
 * `POST /evidence/validate` — the *stored-evidence* gate behind `/app/validator`.
 *
 * Deliberately spelled out separately from {@link ClaimValidation} above rather than reusing it:
 * that one is the shape of `/ai/validate/claim`, which takes the material in the request body and
 * has no retriever. This one retrieves over the account's own evidence, which is why it can reach
 * `supported`, and it reports camelCase fields plus the five-factor `sources` the page renders.
 */
export interface ValidatorReason {
  rule: string;
  severity: string;
  message: string;
  evidenceIds: string[];
}

export interface ValidatorSource {
  evidenceId: string;
  title: string;
  kind: string;
  relevance: number;
  channel: string;
  locator: string;
  url: string | null;
  snippet: string;
}

export interface ValidatorClaim {
  claim: string;
  status: 'supported' | 'partially_supported' | 'unsupported' | 'contradicted';
  confidence: number;
  reasons: ValidatorReason[];
  sources: ValidatorSource[];
  safeRewrite: { text: string; removedClaims: string[]; rationale: string } | null;
  unknowns: string[];
  hasQuantifiedClaim: boolean;
  independentSourceCount: number;
  ruleVersion: string;
  model: string | null;
}

/** The envelope of `POST /evidence/validate`: the stored claim id plus the verdict. */
export interface ValidatedClaim {
  claimId: string;
  claim: ValidatorClaim;
}
