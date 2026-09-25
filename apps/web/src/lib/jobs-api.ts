/**
 * `/jobs` — JD analysis, the skill tree and the match (docs/API.md §2.6).
 *
 * One typed fetcher per endpoint, each with a runtime guard that throws `ApiError` carrying
 * `code: 'INVALID_RESPONSE'` and naming the field it expected — the same contract
 * `lib/api.ts` keeps for the other phases' endpoints, so a page that renders a wrong shape
 * is impossible and a shape regression fails loudly instead of showing a plausible zero.
 *
 * The shapes below were captured from the live API (`.tmp/jobs_probe/*.json`) rather than
 * copied from the doc's examples, which differ in one place that matters: the examples show
 * `dimensions[*].matched` / `.missed`, and the wire has `key` / `label` / `score` / `weight`
 * / `weighted` / `formula` / `notes` / `evidenceIds` instead. Per-skill verdicts travel in
 * the three top-level lists (`strengths`, `gaps`, `unknowns`), not inside the dimensions.
 *
 * Requests go through `api.get` / `api.post` from `lib/api.ts` — the client that owns the
 * envelope unwrapping, the `Authorization` header and the `ApiError` mapping. Wiring `/jobs`
 * into `api`'s named methods would mean editing `lib/api.ts`, which this workstream does not
 * own, so the documented escape hatch is used instead of a second client instance that could
 * drift from it.
 */

import { isNullableNumber } from '@careerforge/shared';

import { ApiError, api } from '@/lib/api';

/* ------------------------------------------------------------------ *
 * Wire types (camelCase, exactly what the API serialises)
 * ------------------------------------------------------------------ */

/** One requirement row, with the JD sentence that justifies it. */
export interface JobSkill {
  canonicalId: string | null;
  rawText: string;
  /** The requirement level the engine assigned: `required` | `preferred` | `bonus`. */
  requirement: string;
  weight: number;
  jdEvidence: string;
  mentions: number;
}

export interface JobDetail {
  id: string;
  company: string | null;
  role: string;
  level: string | null;
  location: string | null;
  educationRequirement: string | null;
  yearsExperienceMin: number | null;
  parseStatus: string;
  parseConfidence: number;
  source: string;
  requiredCount: number;
  preferredCount: number;
  bonusCount: number;
  matchScore: number | null;
  createdAt: string | null;
  responsibilities: string[];
  niceToHave: string[];
  keywords: string[];
  skills: JobSkill[];
  /**
   * The parser's own output, verbatim. `warnings` is injected into it by
   * `POST /jobs/analyze` only, so a re-read through `GET /jobs/{id}` has the analysis but
   * not the warnings that came with it.
   */
  analysis: Record<string, unknown>;
  descriptionChars: number;
}

export interface SkillTree {
  jobId: string;
  role: string;
  company: string | null;
  required: JobSkill[];
  preferred: JobSkill[];
  bonus: JobSkill[];
  /** Requirements the taxonomy could not normalise — excluded from scoring by the engine. */
  unmatchedCount: number;
}

export interface MatchDimension {
  key: string;
  label: string;
  /** 0–100, the dimension's raw score. */
  score: number;
  /** 0–1 share of the total; the engine's own weight. */
  weight: number;
  /** `score × weight` — the dimension's contribution to the match score. */
  weighted: number;
  formula: string;
  notes: string[] | null;
  evidenceIds: string[] | null;
}

/** A requirement the engine counts as met, and what is behind it. */
export interface MatchStrength {
  canonicalId: string;
  displayName: string;
  requirement: string;
  userLevel: string;
  evidenceCount: number;
  confidence: number | null;
  reason: string;
}

export interface MatchGap {
  canonicalId: string;
  displayName: string;
  requirement: string;
  /** `high` | `medium` | `low`, derived from the requirement level. */
  severity: string;
  jdEvidence: string;
}

export interface MatchUnknown {
  canonicalId: string;
  displayName: string;
  requirement: string;
  reason: string;
  askUser: string;
}

export interface MatchWhy {
  formula: string;
  algorithmVersion: string;
  evidenceUsed: string[];
  notes: string[];
  explanation: string;
  computedAt: string | null;
}

export interface JobMatch {
  jobId: string;
  score: number;
  dimensions: Record<string, MatchDimension>;
  strengths: MatchStrength[];
  gaps: MatchGap[];
  unknowns: MatchUnknown[];
  why: MatchWhy;
  /** 0–1. See `job-match-view.ts`: the stored-match read does not populate this. */
  evidenceCoverage: number | null;
  confidence: number;
  degraded: boolean;
  narrative: string;
  warnings: string[] | null;
}

export interface AnalyzeJobInput {
  /** The posting text as it will be sent — the API parses this and nothing else. */
  text: string;
  /** `paste` | `upload` | `url` | `manual`. */
  source?: string;
  /** Stored with the analysis as a reference. Nothing is fetched from it. */
  sourceUrl?: string;
}

/** Stable render order for the five dimensions (the payload is a map, so order is ours). */
export const DIMENSION_ORDER = ['skill', 'experience', 'project', 'education', 'evidence'] as const;

/* ------------------------------------------------------------------ *
 * Guards
 * ------------------------------------------------------------------ */

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isNullableString(value: unknown): value is string | null {
  return value === null || isString(value);
}

/** A list of strings, or 
ull/absent when the stage that would produce it never ran. */
function isNullableStringArray(value: unknown): value is string[] | null | undefined {
  if (value === null || value === undefined) return true;
  return isStringArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(isString);
}

function invalidResponse(path: string, expectation: string, body: unknown): ApiError {
  return new ApiError({
    code: 'INVALID_RESPONSE',
    message: `${path} 返回的结构与 docs/API.md §2.6 不一致（${expectation}）`,
    requestId: null,
    status: 200,
    body,
  });
}

function isJobSkill(value: unknown): value is JobSkill {
  if (!isRecord(value)) return false;
  return (
    isNullableString(value['canonicalId']) &&
    isString(value['rawText']) &&
    isString(value['requirement']) &&
    isNumber(value['weight'])
  );
}

function isSkillArray(value: unknown): value is JobSkill[] {
  return Array.isArray(value) && value.every(isJobSkill);
}

/** `GET /jobs/{id}` — the stored analysis, with every requirement row. */
function isJobDetail(value: unknown): value is JobDetail {
  if (!isRecord(value)) return false;
  const role = value['role'];
  if (!isString(role)) return false;
  if (!isNumber(value['parseConfidence'])) return false;
  if (!isString(value['parseStatus'])) return false;
  if (!isNumber(value['descriptionChars'])) return false;
  if (!isStringArray(value['responsibilities'])) return false;
  if (!Array.isArray(value['skills']) || !value['skills'].every(isJobSkill)) return false;
  return isNumber(value['requiredCount']) && isNumber(value['preferredCount']);
}

/** `GET /jobs/{id}/skill-tree` — the three documented levels. */
function isSkillTree(value: unknown): value is SkillTree {
  if (!isRecord(value)) return false;
  if (!isString(value['jobId'])) return false;
  if (!isNumber(value['unmatchedCount'])) return false;
  return (
    isSkillArray(value['required']) &&
    isSkillArray(value['preferred']) &&
    isSkillArray(value['bonus'])
  );
}

function isMatchDimension(value: unknown): value is MatchDimension {
  if (!isRecord(value)) return false;
  return (
    isString(value['key']) &&
    isString(value['label']) &&
    isNumber(value['score']) &&
    isNumber(value['weight']) &&
    // `weighted` is what `Why N%?` adds up to the total; a payload missing it cannot be
    // rendered as an explanation, so it is required rather than defaulted to zero.
    isNumber(value['weighted'])
  );
}

function isMatchStrength(value: unknown): value is MatchStrength {
  if (!isRecord(value)) return false;
  return (
    isString(value['canonicalId']) &&
    isString(value['displayName']) &&
    isString(value['userLevel']) &&
    isNumber(value['evidenceCount']) &&
    isNumber(value['confidence'])
  );
}

function isMatchGap(value: unknown): value is MatchGap {
  if (!isRecord(value)) return false;
  return (
    isString(value['canonicalId']) && isString(value['displayName']) && isString(value['severity'])
  );
}

function isMatchUnknown(value: unknown): value is MatchUnknown {
  if (!isRecord(value)) return false;
  return (
    isString(value['canonicalId']) && isString(value['displayName']) && isString(value['reason'])
  );
}

/**
 * `POST /jobs/{id}/match` and `GET /jobs/{id}/match`.
 *
 * All five dimensions are required. A match panel that quietly drew four bars because the
 * fifth key was renamed would still *look* like an explanation of the score, and the scores
 * it left out would be invisible rather than wrong — the failure mode this guard exists for.
 */
function isJobMatch(value: unknown): value is JobMatch {
  if (!isRecord(value)) return false;
  if (!isString(value['jobId']) || !isNumber(value['score'])) return false;
  const dimensions = value['dimensions'];
  if (!isRecord(dimensions)) return false;
  for (const key of DIMENSION_ORDER) {
    const dimension = dimensions[key];
    // Tolerates extra dimensions (a future key), refuses to lose a documented one.
    if (dimension !== undefined && !isMatchDimension(dimension)) return false;
    if (dimension === undefined) return false;
  }
  if (!Array.isArray(value['strengths']) || !value['strengths'].every(isMatchStrength)) {
    return false;
  }
  if (!Array.isArray(value['gaps']) || !value['gaps'].every(isMatchGap)) return false;
  if (!Array.isArray(value['unknowns']) || !value['unknowns'].every(isMatchUnknown)) return false;
  const why = value['why'];
  if (!isRecord(why) || !isString(why['formula'])) return false;
  // `null` is a legal answer for these three and means *the stage did not run*, which is a different
  // fact from a measured zero. `GET /jobs/{id}/match` returns them as null while `POST` fills them in,
  // so requiring a number here made the stored-match path throw and the Match figures panel never
  // mount — a guard that was already inconsistent with the component that prints `—` for this case.
  // A wrong *type* is still refused: `undefined` would be a missing key, not an unavailable value.
  if (!isNullableNumber(value['evidenceCoverage'])) return false;
  if (!isNullableNumber(value['confidence'])) return false;
  return isNullableStringArray(value['warnings']);
}

/* ------------------------------------------------------------------ *
 * Fetchers
 * ------------------------------------------------------------------ */

/** `POST /jobs/analyze` — synchronous parse; re-pasting the same text updates one job. */
export async function analyzeJob(input: AnalyzeJobInput): Promise<JobDetail> {
  const body: Record<string, unknown> = { text: input.text, source: input.source ?? 'paste' };
  if (input.sourceUrl) body['sourceUrl'] = input.sourceUrl;
  const data = await api.post<unknown>('/jobs/analyze', body);
  if (!isJobDetail(data)) {
    throw invalidResponse('POST /jobs/analyze', '缺少 role/parseStatus 或要求行不是技能行', data);
  }
  return data;
}

/** `GET /jobs/{id}` — the stored analysis. */
export async function fetchJob(jobId: string): Promise<JobDetail> {
  const data = await api.get<unknown>(`/jobs/${jobId}`);
  if (!isJobDetail(data)) {
    throw invalidResponse('GET /jobs/{id}', '缺少 role/skills/parseConfidence 之一', data);
  }
  return data;
}

/** `GET /jobs/{id}/skill-tree` — required / preferred / bonus, each with its JD sentence. */
export async function fetchSkillTree(jobId: string): Promise<SkillTree> {
  const data = await api.get<unknown>(`/jobs/${jobId}/skill-tree`);
  if (!isSkillTree(data)) {
    throw invalidResponse(
      'GET /jobs/{id}/skill-tree',
      '三层 required/preferred/bonus 不完整',
      data,
    );
  }
  return data;
}

/** `POST /jobs/{id}/match` — computes against the stored evidence graph and keeps the row. */
export async function computeMatch(jobId: string): Promise<JobMatch> {
  const data = await api.post<unknown>(`/jobs/${jobId}/match`);
  if (!isJobMatch(data)) {
    throw invalidResponse(
      'POST /jobs/{id}/match',
      '五个维度不全或 strengths/gaps/unknowns 缺字段',
      data,
    );
  }
  return data;
}

/**
 * `GET /jobs/{id}/match` — the newest stored match.
 *
 * `404 NOT_FOUND` ("This job has not been matched yet") is a **state, not a failure**, so it
 * resolves to `null` instead of surfacing as an error the page would have to special-case.
 * Any other error still throws.
 */
export async function fetchStoredMatch(jobId: string): Promise<JobMatch | null> {
  let data: unknown;
  try {
    data = await api.get<unknown>(`/jobs/${jobId}/match`);
  } catch (error) {
    if (error instanceof ApiError && error.code === 'NOT_FOUND') return null;
    throw error;
  }
  if (!isJobMatch(data)) {
    throw invalidResponse(
      'GET /jobs/{id}/match',
      '五个维度不全或 strengths/gaps/unknowns 缺字段',
      data,
    );
  }
  return data;
}
