import { api } from './api';
import { nullableNum, nullableStr, reader } from './interview-api';

/**
 * The two non-interview reads `/app/interview` depends on: the target job (`/jobs`) and the
 * deployment's own limitations (`/ai/capabilities`).
 *
 * They are here rather than in `./interview-api` because they belong to different endpoints with
 * different owners — `/jobs` is `docs/API.md` §2.6 and speaks camelCase, while `/ai/interview/*`
 * speaks snake_case. Keeping them apart is what stops one of them drifting into the other's
 * conventions, and it keeps both modules under the 500-line rule.
 */

export interface JobSummary {
  id: string;
  role: string;
  company: string | null;
  parseStatus: string;
  parseConfidence: number;
  matchScore: number | null;
  requiredCount: number;
  preferredCount: number;
  bonusCount: number;
  createdAt: string | null;
}

export interface JobList {
  items: JobSummary[];
  /** How many postings the account owns — a page of 20 must not read as "all of them". */
  total: number;
}

export interface JobSkill {
  canonicalId: string | null;
  rawText: string;
  requirement: string;
}

export interface JobDetail extends JobSummary {
  /**
   * The parser's own output, verbatim. This is what `StartInterviewRequest.job` wants — but the
   * *stored* copy, read through `GET /jobs/{id}`: the `POST /jobs/analyze` response injects a
   * `warnings` key into this object, and `JDAnalysis` is `extra="forbid"`.
   */
  analysis: Record<string, unknown>;
  skills: JobSkill[];
}

export interface SkillTree {
  jobId: string;
  role: string;
  required: JobSkill[];
  preferred: JobSkill[];
  bonus: JobSkill[];
  /** Requirements the taxonomy could not normalise: real, and never a question topic. */
  unmatchedCount: number;
}

export interface InterviewCapabilities {
  provider: string;
  providerChain: string[];
  degraded: boolean;
  retrievalAvailable: boolean;
  sessionStore: string;
  activeInterviewSessions: number;
  limitations: string[];
}

function parseJobSummary(value: unknown, path: string, body: unknown): JobSummary {
  const r = reader(path, body);
  const job = r.obj('items[]', value);
  return {
    id: r.str('items[].id', job['id']),
    role: r.str('items[].role', job['role']),
    company: nullableStr(job['company']),
    parseStatus: nullableStr(job['parseStatus']) ?? '',
    parseConfidence: nullableNum(job['parseConfidence']) ?? 0,
    matchScore: nullableNum(job['matchScore']),
    requiredCount: nullableNum(job['requiredCount']) ?? 0,
    preferredCount: nullableNum(job['preferredCount']) ?? 0,
    bonusCount: nullableNum(job['bonusCount']) ?? 0,
    createdAt: nullableStr(job['createdAt']),
  };
}

function parseJobSkill(value: unknown, field: string, path: string, body: unknown): JobSkill {
  const r = reader(path, body);
  const skill = r.obj(field, value);
  return {
    canonicalId: nullableStr(skill['canonicalId']),
    rawText: r.str(`${field}.rawText`, skill['rawText']),
    requirement: nullableStr(skill['requirement']) ?? 'required',
  };
}

export const interviewTargetApi = {
  /** `GET /jobs` — the postings this account has already analysed. */
  async targetJobs(limit = 20): Promise<JobList> {
    const path = 'GET /jobs';
    const data = await api.get<unknown>('/jobs', { query: { limit } });
    const r = reader(path, data);
    const body = r.obj('jobs', data);
    return {
      items: r.arr('items', body['items']).map((item) => parseJobSummary(item, path, body)),
      total: nullableNum(body['total']) ?? 0,
    };
  },

  /**
   * `GET /jobs/{id}` — the *stored* analysis, which is what the interview endpoint accepts.
   * The `POST /jobs/analyze` response carries the same object plus an injected `warnings` key,
   * and `JDAnalysis` refuses unknown fields, so this read is not optional.
   */
  async jobDetail(jobId: string): Promise<JobDetail> {
    const path = 'GET /jobs/{id}';
    const data = await api.get<unknown>(`/jobs/${jobId}`);
    const r = reader(path, data);
    const body = r.obj('job', data);
    return {
      ...parseJobSummary(body, path, body),
      analysis: r.obj('analysis', body['analysis']),
      skills: r
        .arr('skills', body['skills'])
        .map((item) => parseJobSkill(item, 'skills[]', path, body)),
    };
  },

  /** `POST /jobs/analyze` — a pasted posting becomes a selectable target, and is stored. */
  async analyseJob(text: string): Promise<JobSummary> {
    const path = 'POST /jobs/analyze';
    const data = await api.post<unknown>('/jobs/analyze', { text, source: 'paste' });
    return parseJobSummary(data, path, data);
  },

  /** `GET /jobs/{id}/skill-tree` — the requirements this session's questions are drawn from. */
  async skillTree(jobId: string): Promise<SkillTree> {
    const path = 'GET /jobs/{id}/skill-tree';
    const data = await api.get<unknown>(`/jobs/${jobId}/skill-tree`);
    const r = reader(path, data);
    const body = r.obj('skill-tree', data);
    return {
      jobId: r.str('jobId', body['jobId']),
      role: nullableStr(body['role']) ?? '',
      required: r
        .arr('required', body['required'])
        .map((item) => parseJobSkill(item, 'required[]', path, body)),
      preferred: r
        .arr('preferred', body['preferred'])
        .map((item) => parseJobSkill(item, 'preferred[]', path, body)),
      bonus: r
        .arr('bonus', body['bonus'])
        .map((item) => parseJobSkill(item, 'bonus[]', path, body)),
      unmatchedCount: nullableNum(body['unmatchedCount']) ?? 0,
    };
  },

  /** `GET /ai/capabilities` — provider, degradation and the deployment's stated limits. */
  async capabilities(): Promise<InterviewCapabilities> {
    const path = 'GET /ai/capabilities';
    const data = await api.get<unknown>('/ai/capabilities');
    const r = reader(path, data);
    const body = r.obj('capabilities', data);
    return {
      provider: r.str('provider', body['provider']),
      providerChain: r.strs('provider_chain', body['provider_chain']),
      degraded: r.bool('degraded', body['degraded']),
      retrievalAvailable: r.bool('retrieval_available', body['retrieval_available']),
      sessionStore: r.str('session_store', body['session_store']),
      activeInterviewSessions: r.num(
        'active_interview_sessions',
        body['active_interview_sessions'],
      ),
      limitations: r.strs('limitations', body['limitations']),
    };
  },
} as const;
