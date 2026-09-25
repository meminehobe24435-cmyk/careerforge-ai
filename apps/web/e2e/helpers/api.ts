import { expect, type APIRequestContext, type APIResponse } from '@playwright/test';

import type {
  AiRun,
  AiRunDetail,
  Capabilities,
  ClaimValidation,
  DashboardResponse,
  DocumentAccepted,
  DocumentAnalysis,
  Envelope,
  EvidenceGraph,
  EvidenceRow,
  EvidenceSetup,
  InterviewSession,
  InterviewTurnResult,
  JobDetail,
  MatchResult,
  PublicCandidate,
  PublicEvidence,
  SessionPayload,
  SkillTree,
  TaskStatus,
  ValidatedClaim,
} from './api-types';

/**
 * A typed client for the real API, used for *setup* and for the flows whose UI does not exist yet.
 *
 * The specs are end-to-end tests of a running stack, not unit tests of a mock: every call here goes
 * over HTTP to the API the browser itself talks to, with the same bearer token the app stores. Two
 * consequences are worth stating because they shape the specs:
 *
 * * setup is **idempotent** — re-uploading the same résumé bytes returns the existing document,
 *   re-importing the same profile text updates the same rows, re-analysing the same posting updates
 *   the same job, and publishing keeps the slug — so specs can each create what they need without
 *   depending on the order they ran in;
 * * nothing here is invented to make a test pass. Where an endpoint is absent or a route is not
 *   shipped, the spec says so instead of stubbing it.
 *
 * The wire shapes live in `api-types.ts`; this file is only the calling.
 */
export const API_BASE_URL = (
  process.env.E2E_API_URL?.trim() || 'http://127.0.0.1:8318/api/v1'
).replace(/\/+$/, '');

export class Api {
  constructor(
    private readonly request: APIRequestContext,
    private readonly session: SessionPayload,
  ) {}

  private headers(): Record<string, string> {
    return { Authorization: `Bearer ${this.session.accessToken}`, Accept: 'application/json' };
  }

  async response(
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
    path: string,
    data?: unknown,
  ): Promise<APIResponse> {
    return this.request.fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: this.headers(),
      ...(data === undefined ? {} : { data }),
    });
  }

  /**
   * `POST`/`PATCH` that waits out a rate limit instead of failing on it.
   *
   * Three buckets bound this suite and they are all per *user*, not per test: `upload` is 20 per
   * **hour** (`POST /profile/import`, `POST /documents`), `ai` is a handful per **minute**
   * (`_AI_MARKERS` in `middleware/ratelimit.py`: `/analyze`, `/match`, `/interview`, …), and
   * `write` is 60 per minute. A browser suite legitimately fires several `/jobs/analyze` and
   * `/jobs/{id}/match` calls in a few seconds, and the API's answer is a precise `429` that says
   * how long to wait — so the honest client behaviour is to wait and retry, not to make the spec
   * flaky or to lower what it asks for.
   *
   * The wait is read from the API's own message (`retry in 3s`), capped at 10s, and attempted at
   * most twice; anything that is still `429` after that is a real failure and is reported as one.
   */
  private async requestWithBackoff(
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
    path: string,
    data?: unknown,
  ): Promise<APIResponse> {
    for (let attempt = 0; ; attempt += 1) {
      const response = await this.response(method, path, data);
      if (response.status() !== 429 || attempt >= 2) return response;
      const body = (await response.json().catch(() => null)) as Envelope<unknown> | null;
      const hint = /retry in (\d+)s/.exec(body?.error?.message ?? '')?.[1];
      const waitMs = Math.min(10, Math.max(1, Number(hint ?? 2))) * 1000;
      await new Promise((resolve) => setTimeout(resolve, waitMs));
    }
  }

  /** Unwrap the envelope, failing with the API's own error code rather than `undefined`. */
  async json<T>(
    method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
    path: string,
    data?: unknown,
  ): Promise<T> {
    const response = await this.requestWithBackoff(method, path, data);
    const body = (await response.json()) as Envelope<T>;
    if (!response.ok() || body.success !== true || body.data === null) {
      throw new Error(
        `${method} ${path} → HTTP ${response.status()} ` +
          `${body.error ? `${body.error.code}: ${body.error.message}` : 'no data'} ` +
          `(requestId ${body.requestId ?? 'unknown'})`,
      );
    }
    return body.data;
  }

  // ── reads ────────────────────────────────────────────────────────────────

  dashboard(): Promise<DashboardResponse> {
    return this.json<DashboardResponse>('GET', '/dashboard');
  }

  capabilities(): Promise<Capabilities> {
    return this.json<Capabilities>('GET', '/ai/capabilities');
  }

  evidenceGraph(query = '?depth=2'): Promise<EvidenceGraph> {
    return this.json<EvidenceGraph>('GET', `/evidence-graph${query}`);
  }

  evidenceList(limit = 50): Promise<{ items: EvidenceRow[]; total: number }> {
    return this.json('GET', `/evidence?limit=${limit}`);
  }

  skillTree(jobId: string): Promise<SkillTree> {
    return this.json<SkillTree>('GET', `/jobs/${jobId}/skill-tree`);
  }

  task(taskId: string): Promise<TaskStatus> {
    return this.json<TaskStatus>('GET', `/tasks/${taskId}`);
  }

  newestRun(workflow: string): Promise<AiRun> {
    return this.json<{ items: AiRun[]; total: number }>(
      'GET',
      `/ai-runs?workflow=${encodeURIComponent(workflow)}&limit=1`,
    ).then((page) => {
      const run = page.items[0];
      if (!run) {
        throw new Error(`no ${workflow} run was recorded — the traced operation did not happen`);
      }
      return run;
    });
  }

  aiRun(runId: string): Promise<AiRunDetail> {
    return this.json<AiRunDetail>('GET', `/ai-runs/${runId}`);
  }

  publicCandidate(slug: string): Promise<PublicCandidate> {
    return this.json<PublicCandidate>('GET', `/public/candidate/${slug}`);
  }

  publicSkillEvidence(slug: string, skillId: string): Promise<PublicEvidence[]> {
    return this.json<PublicEvidence[]>(
      'GET',
      `/public/candidate/${slug}/evidence/${encodeURIComponent(skillId)}`,
    );
  }

  // ── idempotent setup ─────────────────────────────────────────────────────

  /** `POST /profile/import` is synchronous and merges by dedupe key, so re-running is safe. */
  async importProfile(text: string): Promise<void> {
    await this.json<{ counts: Record<string, number> }>('POST', '/profile/import', { text });
  }

  /** `POST /documents` → 202; identical bytes return the existing document with `deduplicated`. */
  async uploadResume(text: string, filename = 'resume.txt'): Promise<DocumentAccepted> {
    const response = await this.request.fetch(`${API_BASE_URL}/documents`, {
      method: 'POST',
      headers: { ...this.headers(), Accept: 'application/json' },
      multipart: {
        file: { name: filename, mimeType: 'text/plain', buffer: Buffer.from(text, 'utf8') },
        kind: 'resume',
      },
    });
    const body = (await response.json()) as Envelope<DocumentAccepted>;
    if (!response.ok() || !body.data) {
      throw new Error(`POST /documents → HTTP ${response.status()} ${JSON.stringify(body.error)}`);
    }
    return body.data;
  }

  /**
   * Wait for a background job to reach a terminal state, using `expect.poll` rather than a fixed
   * sleep: the assertion retries on the task's own state and fails with the task's own error.
   */
  async waitForTask(taskId: string): Promise<TaskStatus> {
    await expect
      .poll(async () => (await this.task(taskId)).status, {
        message: `task ${taskId} (document.ingest) should reach a terminal state`,
        timeout: 20_000,
        intervals: [50, 100, 200, 400, 800],
      })
      .toMatch(/^(succeeded|failed|cancelled)$/);
    const task = await this.task(taskId);
    expect(task.status, `task ${taskId} ended as ${task.status}: ${task.error ?? ''}`).toBe(
      'succeeded',
    );
    return task;
  }

  /**
   * Upload a résumé, let the worker ingest it, then build evidence from it.
   *
   * An existing résumé document is **reused** rather than re-uploaded, and re-analysed instead.
   * `POST /documents`, `POST /documents/{id}/analyze` and `POST /profile/import` all share the
   * `upload` rate-limit bucket (20 requests per *hour* per user, `middleware/ratelimit.py`), so a
   * setup helper that re-uploads on every call would exhaust an hourly budget the product's own
   * flows need. Analysis is idempotent — evidence de-duplicates on content hash — so re-analysing is
   * both cheaper and equivalent.
   */
  async ensureEvidence(resume: string): Promise<EvidenceSetup> {
    await this.importProfile(resume);

    const existing = await this.json<{
      items: Array<{ id: string; filename: string }>;
      total: number;
    }>('GET', '/documents?kind=resume&limit=20');
    const reusable = existing.items[0];
    let documentId: string;
    let deduplicated: boolean;
    if (reusable) {
      documentId = reusable.id;
      deduplicated = true;
    } else {
      const accepted = await this.uploadResume(resume);
      if (!accepted.deduplicated && accepted.taskId) await this.waitForTask(accepted.taskId);
      documentId = accepted.documentId;
      deduplicated = accepted.deduplicated;
    }

    const analysis = await this.json<DocumentAnalysis>('POST', `/documents/${documentId}/analyze`);
    return { documentId, deduplicated, analysis };
  }

  /** `POST /jobs/analyze` de-duplicates on the posting text, so the same JD updates one job. */
  analyzeJob(text: string): Promise<JobDetail> {
    return this.json<JobDetail>('POST', '/jobs/analyze', { text, source: 'paste' });
  }

  /**
   * `POST /evidence` — add evidence by hand (`kind: 'manual'`).
   *
   * The claim gate needs **two independent evidence kinds** before it will call a sentence
   * `supported`, and a locally uploaded résumé only produces `document_chunk`. So the specs that
   * exercise the validator's highest verdict store one manual row as well; the confidence of that
   * row is computed by the server from the same five factors as everything else and is never
   * supplied here.
   */
  addManualEvidence(input: {
    title: string;
    snippet: string;
    evidenceLocator?: { path?: string | null; line?: number | null };
  }): Promise<{ id: string; kind: string; confidence: number; title: string }> {
    return this.json('POST', '/evidence', {
      title: input.title,
      snippet: input.snippet,
      ...(input.evidenceLocator ? { locator: input.evidenceLocator } : {}),
    });
  }

  /**
   * `POST /evidence/validate` — the same gate the `/app/validator` page runs.
   *
   * Note the field names: this endpoint takes `text`, where `/ai/validate/claim` takes `claim`.
   * The two are different services over the same rules (`lib/validator-api.ts` explains why), and
   * a spec that mixed them up would be asserting against the other one's answer.
   */
  validateClaim(
    text: string,
    section: 'summary' | 'experience' | 'project' | 'skill' | 'education' = 'summary',
  ): Promise<ValidatedClaim> {
    return this.json('POST', '/evidence/validate', { text, section });
  }

  matchJob(jobId: string): Promise<MatchResult> {
    return this.json<MatchResult>('POST', `/jobs/${jobId}/match`);
  }

  /** Publish (or re-publish) the public candidate page. Keeps the slug across calls. */
  async publish(): Promise<string> {
    const settings = await this.json<{
      slug: string | null;
      isPublished: boolean;
      canPublish: boolean;
    }>('POST', '/public/publish', { published: true });
    if (!settings.slug) {
      throw new Error('publishing returned no slug — the public page has no URL');
    }
    return settings.slug;
  }
}

/** `POST /auth/demo` needs no credentials; the account is seeded on first use. */
export async function signIn(request: APIRequestContext): Promise<SessionPayload> {
  const response = await request.post(`${API_BASE_URL}/auth/demo`, {
    headers: { Accept: 'application/json' },
  });
  const body = (await response.json()) as Envelope<SessionPayload>;
  if (!response.ok() || !body.data) {
    const reason =
      response.status() === 429
        ? 'the API is rate limiting sign-ins (10/minute/IP); wait for the window to pass or restart the API'
        : `is the API running on ${API_BASE_URL}?`;
    throw new Error(
      `POST /auth/demo → HTTP ${response.status()} ` +
        `${body.error ? `(${body.error.code}) ` : ''}— ${reason} ` +
        `[requestId ${body.requestId ?? 'unknown'}]`,
    );
  }
  return body.data;
}

/** Re-exported so a spec can import the client and its shapes from one place. */
export type {
  AiRun,
  AiRunDetail,
  Capabilities,
  ClaimValidation,
  DashboardResponse,
  DocumentAnalysis,
  EvidenceGraph,
  EvidenceRow,
  EvidenceSetup,
  InterviewSession,
  InterviewTurnResult,
  JobDetail,
  MatchResult,
  PublicCandidate,
  PublicEvidence,
  SessionPayload,
  SkillTree,
  ValidatedClaim,
};
