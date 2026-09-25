import {
  ApiError,
  DEFAULT_API_BASE_URL,
  createApiClient,
  isApiError,
  isNumber,
  isRecord,
  isString,
} from '@careerforge/shared';

import { clearSession, getAccessToken } from './auth';

/**
 * The Claim Validator's API surface (`docs/API.md` §2.5, `POST /evidence/validate`).
 *
 * ## Why this endpoint and not `POST /ai/validate/claim`
 *
 * Both run the same gate (`careerforge_ai.agents.validator`), but only this one can *cite* the
 * candidate's stored evidence. `/ai/validate/claim` reads a retriever off `app.state.retriever`,
 * which nothing ever sets, so on a live deployment it retrieves nothing, returns `sources: []`,
 * reports `confidence: 0.0`, and (with an empty evidence pool the rules never see) calls a claim
 * its own résumé plainly supports `unsupported` with `no_evidence_match`. This endpoint goes
 * through `ResumeService.validate`, which builds a real hybrid retriever over the `evidence`
 * table and supplies the candidate's material to the rules phase — so the verdict, the citations
 * and the confidence are all real. Measured both ways on the live stack: see the report.
 *
 * ## Shape
 *
 * `POST /evidence/validate` returns `{ claimId, claim }` in camelCase, which is *not* the shape
 * of `/ai/validate/claim` (that one returns `status`/`sources`/`meta` at the top level and no
 * `claimId`). The guard below names the field it expected, so a backend that changes the shape
 * fails loudly here instead of rendering a verdict with no reasons.
 */

const client = createApiClient({
  baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL,
  getToken: () => getAccessToken(),
  // A stale/expired token is dropped locally so the auth guard can bounce to /login.
  onUnauthorized: () => clearSession(),
});

export const VALIDATOR_API_BASE_URL: string = client.baseUrl;

/** `ClaimStatus` (packages/ai/careerforge_ai/schemas/common.py §Claims). */
export const CLAIM_STATUSES = [
  'pending',
  'supported',
  'partially_supported',
  'unsupported',
  'contradicted',
] as const;
export type ClaimStatus = (typeof CLAIM_STATUSES)[number];

/** `RetrievalChannel` (schemas/common.py). The gate reports how a source was found. */
export const RETRIEVAL_CHANNELS = ['semantic', 'keyword', 'both', 'metadata', 'manual'] as const;
export type RetrievalChannel = (typeof RETRIEVAL_CHANNELS)[number];

/** `CLAIM_SECTIONS` (apps/api .../models/resume.py) — accepted by `section`. */
export const CLAIM_SECTIONS = ['summary', 'experience', 'project', 'skill', 'education'] as const;
export type ClaimSection = (typeof CLAIM_SECTIONS)[number];

export interface ClaimReason {
  rule: string;
  severity: string;
  message: string;
  evidenceIds: string[];
}

export interface ClaimSource {
  evidenceId: string;
  title: string;
  kind: string;
  /** How well this source matched the claim (`0..1`), as retrieval reported it. */
  relevance: number;
  channel: string;
  /** Human-readable location, e.g. `motor_control.c:42`; `—` when the evidence has none. */
  locator: string;
  url: string | null;
  snippet: string;
}

export interface SafeRewrite {
  text: string;
  removedClaims: string[];
  rationale: string;
}

export interface ClaimValidation {
  claim: string;
  status: ClaimStatus;
  confidence: number;
  reasons: ClaimReason[];
  sources: ClaimSource[];
  safeRewrite: SafeRewrite | null;
  unknowns: string[];
  hasQuantifiedClaim: boolean;
  independentSourceCount: number;
  ruleVersion: string;
  model: string | null;
}

export interface ValidatedClaim {
  claimId: string;
  claim: ClaimValidation;
}

/** One row of `GET /evidence`, reduced to what the result panel needs. */
export interface EvidenceRecord {
  id: string;
  kind: string;
  title: string;
  /** The evidence's own confidence (`confidence@1.0.0`), as stored. */
  confidence: number;
}

export interface EvidenceIndex {
  byId: Record<string, EvidenceRecord>;
  /** How many rows this read returned. `GET /evidence` reports `total = len(items)`. */
  count: number;
  /** `true` when the read hit its own limit, so `count` is a floor and not the real size. */
  truncated: boolean;
}

/** The largest page `GET /evidence` accepts (`MAX_LIST_LIMIT` in routers/evidence.py). */
export const EVIDENCE_PAGE_LIMIT = 200;

function isStatus(value: unknown): value is ClaimStatus {
  return isString(value) && (CLAIM_STATUSES as readonly string[]).includes(value);
}

/**
 * The first field this build needs that the response does not have, or `null`.
 *
 * A *field name* rather than a boolean, because `ApiError.code = 'INVALID_RESPONSE'` is only
 * useful if the message says which field was expected — "invalid response" alone sends the
 * reader to the network tab with no hypothesis.
 */
export function findInvalidClaimField(value: unknown): string | null {
  if (!isRecord(value)) return 'data (object)';
  if (!isString(value['claimId'])) return 'data.claimId';
  const claim = value['claim'];
  if (!isRecord(claim)) return 'data.claim';
  if (!isString(claim['claim'])) return 'data.claim.claim';
  if (!isStatus(claim['status'])) return `data.claim.status (${CLAIM_STATUSES.join(' | ')})`;
  if (!isNumber(claim['confidence'])) return 'data.claim.confidence';
  if (!isNumber(claim['independentSourceCount'])) return 'data.claim.independentSourceCount';
  if (typeof claim['hasQuantifiedClaim'] !== 'boolean') return 'data.claim.hasQuantifiedClaim';
  if (!Array.isArray(claim['unknowns'])) return 'data.claim.unknowns';

  if (!Array.isArray(claim['reasons'])) return 'data.claim.reasons';
  for (const [index, reason] of claim['reasons'].entries()) {
    if (!isRecord(reason)) return `data.claim.reasons[${index}]`;
    if (!isString(reason['rule'])) return `data.claim.reasons[${index}].rule`;
    if (!isString(reason['severity'])) return `data.claim.reasons[${index}].severity`;
    if (!isString(reason['message'])) return `data.claim.reasons[${index}].message`;
  }

  if (!Array.isArray(claim['sources'])) return 'data.claim.sources';
  for (const [index, source] of claim['sources'].entries()) {
    if (!isRecord(source)) return `data.claim.sources[${index}]`;
    if (!isString(source['evidenceId'])) return `data.claim.sources[${index}].evidenceId`;
    if (!isString(source['title'])) return `data.claim.sources[${index}].title`;
    if (!isString(source['kind'])) return `data.claim.sources[${index}].kind`;
    if (!isNumber(source['relevance'])) return `data.claim.sources[${index}].relevance`;
    if (!isString(source['channel'])) return `data.claim.sources[${index}].channel`;
  }

  const rewrite = claim['safeRewrite'];
  if (rewrite !== null && rewrite !== undefined) {
    if (!isRecord(rewrite)) return 'data.claim.safeRewrite (object | null)';
    if (!isString(rewrite['text'])) return 'data.claim.safeRewrite.text';
    if (!Array.isArray(rewrite['removedClaims'])) return 'data.claim.safeRewrite.removedClaims';
  }

  return null;
}

function invalidResponse(path: string, expectation: string, body: unknown): ApiError {
  return new ApiError({
    code: 'INVALID_RESPONSE',
    message: `${path} 返回的结构与它声明的契约不一致（缺少 ${expectation}）`,
    requestId: null,
    status: 200,
    body,
  });
}

function asReasons(value: unknown): ClaimReason[] {
  return (value as Record<string, unknown>[]).map((reason) => ({
    rule: String(reason['rule']),
    severity: String(reason['severity']),
    message: String(reason['message']),
    evidenceIds: Array.isArray(reason['evidenceIds']) ? reason['evidenceIds'].filter(isString) : [],
  }));
}

function asSources(value: unknown): ClaimSource[] {
  return (value as Record<string, unknown>[]).map((source) => ({
    evidenceId: String(source['evidenceId']),
    title: String(source['title']),
    kind: String(source['kind']),
    relevance: Number(source['relevance']),
    channel: String(source['channel']),
    locator: isString(source['locator']) ? source['locator'] : '',
    url: isString(source['url']) ? source['url'] : null,
    snippet: isString(source['snippet']) ? source['snippet'] : '',
  }));
}

/**
 * Run the gate over one sentence, against the candidate's stored evidence.
 *
 * No `evidence_text` is sent: the service supplies the candidate's own material, and a client
 * that supplied its own would be judging the claim against something the user cannot see.
 */
export async function validateClaim(input: {
  text: string;
  section?: ClaimSection;
}): Promise<ValidatedClaim> {
  const data = await client.post<unknown>('/evidence/validate', {
    text: input.text,
    section: input.section ?? 'summary',
  });

  const invalid = findInvalidClaimField(data);
  if (invalid !== null) {
    throw invalidResponse(
      'POST /evidence/validate',
      `${invalid}（docs/API.md §2.5 的 ClaimValidation）`,
      data,
    );
  }

  const record = data as Record<string, unknown>;
  const claim = record['claim'] as Record<string, unknown>;
  const rewrite = claim['safeRewrite'];

  return {
    claimId: record['claimId'] as string,
    claim: {
      claim: claim['claim'] as string,
      status: claim['status'] as ClaimStatus,
      confidence: Number(claim['confidence']),
      reasons: asReasons(claim['reasons']),
      sources: asSources(claim['sources']),
      safeRewrite:
        isRecord(rewrite) && isString(rewrite['text']) && rewrite['text']
          ? {
              text: rewrite['text'],
              removedClaims: Array.isArray(rewrite['removedClaims'])
                ? rewrite['removedClaims'].filter(isString)
                : [],
              rationale: isString(rewrite['rationale']) ? rewrite['rationale'] : '',
            }
          : null,
      unknowns: (claim['unknowns'] as unknown[]).filter(isString),
      hasQuantifiedClaim: Boolean(claim['hasQuantifiedClaim']),
      independentSourceCount: Number(claim['independentSourceCount']),
      ruleVersion: isString(claim['ruleVersion']) ? claim['ruleVersion'] : '',
      model: isString(claim['model']) ? claim['model'] : null,
    },
  };
}

/**
 * The candidate's evidence base, indexed by id.
 *
 * The verdict's `sources` carry a *relevance* (how well retrieval matched) but no confidence;
 * confidence lives on the evidence row itself. Reading it is what lets the panel show the number
 * the product actually stores instead of omitting the field or implying a value. A row that is
 * missing from this read is reported as `unavailable`, never as `0`.
 */
export async function fetchEvidenceIndex(
  limit: number = EVIDENCE_PAGE_LIMIT,
): Promise<EvidenceIndex> {
  const data = await client.get<unknown>('/evidence', { query: { limit } });
  if (!isRecord(data) || !Array.isArray(data['items'])) {
    throw invalidResponse('GET /evidence', 'data.items[]', data);
  }

  const byId: Record<string, EvidenceRecord> = {};
  for (const item of data['items']) {
    // Tolerant per row on purpose: one malformed row must not blank out a page that can still
    // show the others. The verdict's own guard stays strict.
    if (!isRecord(item) || !isString(item['id']) || !isNumber(item['confidence'])) continue;
    byId[item['id']] = {
      id: item['id'],
      kind: isString(item['kind']) ? item['kind'] : 'unknown',
      title: isString(item['title']) ? item['title'] : '',
      confidence: Number(item['confidence']),
    };
  }

  const count = data['items'].length;
  return { byId, count, truncated: count >= limit };
}

export { ApiError, isApiError };
