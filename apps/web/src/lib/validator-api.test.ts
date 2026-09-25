import { ApiError } from '@careerforge/shared';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { fetchEvidenceIndex, findInvalidClaimField, validateClaim } from '@/lib/validator-api';

/**
 * The guard, tested against the shape the live endpoint actually returns.
 *
 * `validated` below is a trimmed copy of a real `POST /evidence/validate` response captured from
 * the running stack (`.tmp/p13-validator-populate.py`), field names and all: `claimId`, the
 * camelCase `independentSourceCount`, `safeRewrite.removedClaims`, and source objects carrying
 * `relevance` but no confidence. The point of copying it rather than inventing a fixture is that
 * the guard exists precisely to catch a backend that changes this shape.
 */

function envelope(data: unknown): string {
  return JSON.stringify({ success: true, data, error: null, requestId: 'req_test' });
}

function validated() {
  return {
    claimId: '9481406c-5dbe-4eb3-85a8-c95193afeede',
    claim: {
      claim: '使用 STM32 与 FreeRTOS 实现串级 PID 控制环，并用 TensorFlow 部署推理模型',
      status: 'partially_supported',
      confidence: 0.781,
      reasons: [
        {
          rule: 'skill_not_in_graph',
          severity: 'warning',
          message: '证据中未出现：tensorflow。',
          evidenceIds: [],
        },
      ],
      sources: [
        {
          evidenceId: 'ae768aa5-dc7f-47b8-90ff-64a901b12f80',
          title: 'wei-zhang-resume.md',
          kind: 'document_chunk',
          relevance: 1.0,
          channel: 'keyword',
          locator: '—',
          url: null,
          snippet: '使用 STM32F4 与 FreeRTOS 编写任务调度与串级 PID 控制环',
        },
      ],
      safeRewrite: {
        text: '使用 STM32 与 FreeRTOS 实现串级 PID 控制环',
        removedClaims: ['tensorflow'],
        rationale: '由证据验证模型给出的降级表述',
      },
      unknowns: ['tensorflow'],
      hasQuantifiedClaim: false,
      independentSourceCount: 2,
      ruleVersion: 'claim_rules@1.0.0',
      model: 'heuristic',
    },
  };
}

/**
 * Stub the global fetch with the smallest object the client reads: `ok`, `status`, `text()` and
 * `headers.get()`. A real `Response` would work in Node but adds an environment dependency to a
 * test that is about the guard, not about HTTP.
 */
function stubFetch(payload: unknown, status = 200): void {
  const body = typeof payload === 'string' ? payload : envelope(payload);
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: status >= 200 && status < 300,
      status,
      headers: { get: () => null },
      text: async () => body,
    })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('findInvalidClaimField', () => {
  it('accepts the live shape', () => {
    expect(findInvalidClaimField(validated())).toBeNull();
  });

  it('accepts a null rewrite (the gate declining one is a valid answer)', () => {
    const payload = validated();
    // @ts-expect-error — the fixture is deliberately mutated to the other legal shape.
    payload.claim.safeRewrite = null;
    expect(findInvalidClaimField(payload)).toBeNull();
  });

  it('names the field it expected, one at a time', () => {
    const missingId = { ...validated(), claimId: undefined };
    expect(findInvalidClaimField(missingId)).toBe('data.claimId');

    const missingConfidence = validated();
    // @ts-expect-error — simulating a backend that dropped the field.
    delete missingConfidence.claim.confidence;
    expect(findInvalidClaimField(missingConfidence)).toBe('data.claim.confidence');

    const badStatus = validated();
    badStatus.claim.status = 'probably_fine';
    expect(findInvalidClaimField(badStatus)).toContain('data.claim.status');

    const badRelevance = validated();
    // @ts-expect-error — a string where a number belongs is a rejected shape, not a coerced one.
    badRelevance.claim.sources[0].relevance = '1.0';
    expect(findInvalidClaimField(badRelevance)).toBe('data.claim.sources[0].relevance');

    const badReason = validated();
    // @ts-expect-error — same for a reason message.
    delete badReason.claim.reasons[0].message;
    expect(findInvalidClaimField(badReason)).toBe('data.claim.reasons[0].message');
  });

  it('rejects a non-object payload', () => {
    expect(findInvalidClaimField(null)).toBe('data (object)');
    expect(findInvalidClaimField({ claim: {} })).toBe('data.claimId');
  });
});

describe('validateClaim', () => {
  it('returns a normalised verdict', async () => {
    stubFetch(validated());
    const result = await validateClaim({ text: 'claim text', section: 'experience' });

    expect(result.claimId).toBe('9481406c-5dbe-4eb3-85a8-c95193afeede');
    expect(result.claim.status).toBe('partially_supported');
    expect(result.claim.confidence).toBeCloseTo(0.781);
    expect(result.claim.independentSourceCount).toBe(2);
    expect(result.claim.sources[0]?.channel).toBe('keyword');
    expect(result.claim.safeRewrite?.removedClaims).toEqual(['tensorflow']);
    expect(result.claim.model).toBe('heuristic');
  });

  it('sends the claim to POST /evidence/validate', async () => {
    stubFetch(validated());
    await validateClaim({ text: '一句话', section: 'project' });

    const call = vi.mocked(fetch).mock.calls[0];
    expect(String(call?.[0])).toContain('/evidence/validate');
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({
      text: '一句话',
      section: 'project',
    });
  });

  it('throws ApiError INVALID_RESPONSE naming the missing field', async () => {
    const payload = validated();
    // @ts-expect-error — the rejected shape under test.
    delete payload.claim.independentSourceCount;
    stubFetch(payload);

    await expect(validateClaim({ text: '一句话' })).rejects.toSatisfy(
      (error: unknown) =>
        error instanceof ApiError &&
        error.code === 'INVALID_RESPONSE' &&
        error.message.includes('data.claim.independentSourceCount'),
    );
  });

  it('reports a transport failure as a network error, not as a verdict', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('failed to fetch');
      }),
    );
    await expect(validateClaim({ text: '一句话' })).rejects.toSatisfy(
      (error: unknown) => error instanceof ApiError && error.isNetworkError,
    );
  });
});

describe('fetchEvidenceIndex', () => {
  it('indexes evidence by id and reports how many rows it read', async () => {
    stubFetch({
      items: [
        { id: 'ev-1', kind: 'document_chunk', title: 'a.md', confidence: 0.8 },
        { id: 'ev-2', kind: 'manual', title: 'b.md', confidence: 0.705 },
      ],
      total: 2,
    });

    const index = await fetchEvidenceIndex(200);
    expect(index.count).toBe(2);
    expect(index.truncated).toBe(false);
    expect(index.byId['ev-1']?.confidence).toBe(0.8);
  });

  it('keeps the rows it can read and skips the ones it cannot', async () => {
    stubFetch({
      items: [{ id: 'ev-1', confidence: 0.8 }, { confidence: 'high' }, null],
      total: 3,
    });

    const index = await fetchEvidenceIndex(200);
    expect(Object.keys(index.byId)).toEqual(['ev-1']);
    expect(index.byId['ev-1']?.title).toBe('');
  });

  it('reports a truncated read rather than pretending it is the whole base', async () => {
    stubFetch({
      items: Array.from({ length: 2 }, (_, i) => ({ id: `ev-${i}`, confidence: 0.5 })),
      total: 2,
    });

    const index = await fetchEvidenceIndex(2);
    expect(index.truncated).toBe(true);
  });

  it('rejects a payload with no items array', async () => {
    stubFetch({ rows: [] });
    await expect(fetchEvidenceIndex()).rejects.toSatisfy(
      (error: unknown) =>
        error instanceof ApiError &&
        error.code === 'INVALID_RESPONSE' &&
        error.message.includes('data.items[]'),
    );
  });
});
