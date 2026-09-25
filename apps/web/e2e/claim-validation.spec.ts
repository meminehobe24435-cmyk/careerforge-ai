import { EXAGGERATED_CLAIM, RESUME, SUPPORTED_CLAIM } from './helpers/dataset';
import { expect, test } from './helpers/fixtures';
import { apiFromPage } from './helpers/session';
import type { ClaimValidation } from './helpers/api';

/**
 * E2E 4 · Claim validation — the gate that decides whether a sentence may go on a résumé.
 *
 * **There is no validator UI.** `nav-config.ts` badges `/app/validator` `PHASE 6` and renders it as
 * a non-clickable item, and no route under `app/**` renders a claim decision. The gate itself is
 * fully implemented and is exercised here through the endpoint `docs/API.md` §2.5 documents for it
 * (`POST /ai/validate/claim`), called **from the page** with the session the browser holds, so the
 * request travels the same origin/CORS path the app's own client would use.
 *
 * Two claims are posted against the same material:
 *
 * * one the fixture résumé states almost verbatim — evidence exists for it;
 * * one that invents two hard numbers, a superlative and a technology nothing anywhere measures.
 *
 * And the deployment's own ceiling is asserted rather than assumed. `GET /ai/capabilities` reports
 * `retrieval_available: false` on this build ("证据检索未接入：本次验证只基于调用方提供的材料"),
 * so the validator never gets retrieval hits; with no hits the gate falls back to a single
 * self-report source, and its own rule requires **two independent evidence kinds** before a claim
 * may be called `supported` (`careerforge_ai/scoring/confidence.py::classify_claim_status`,
 * `_MIN_INDEPENDENT_SOURCES = 2`). `partially_supported` is therefore the highest status reachable
 * here — and that is exactly what the second assertion below pins. It is written to fail on the day
 * retrieval is wired up, so the ceiling cannot quietly become a stale expectation.
 */
test.describe('Claim validation', () => {
  test('an evidenced claim and a fabricated one land on opposite sides of the gate', async ({
    api,
    signedInPage: page,
  }) => {
    const { analysis } = await api.ensureEvidence(RESUME);
    expect(
      analysis.evidenceCreated + analysis.evidenceUpdated,
      'the gate needs real evidence in the account before it can support anything',
    ).toBeGreaterThan(0);

    const capabilities = await api.capabilities();
    // The retrieval half of the gate is not wired in this build; every verdict below is therefore
    // based on the material supplied with the request. When this flips to `true`, the expectation
    // for `evidenceBacked` must become `supported`.
    expect(capabilities.retrieval_available).toBe(false);

    await page.goto('/app/dashboard');

    const evidenceBacked = await apiFromPage<ClaimValidation>(page, '/ai/validate/claim', {
      method: 'POST',
      body: { claim: SUPPORTED_CLAIM, evidence_text: RESUME },
    });
    expect(evidenceBacked.status).toBe(200);
    const good = evidenceBacked.data;

    const fabricated = await apiFromPage<ClaimValidation>(page, '/ai/validate/claim', {
      method: 'POST',
      body: { claim: EXAGGERATED_CLAIM, evidence_text: RESUME },
    });
    expect(fabricated.status).toBe(200);
    const bad = fabricated.data;

    // ── the evidenced claim is allowed through ───────────────────────────────────────────────
    expect(good.status, 'the highest status this deployment can reach (see the note above)').toBe(
      'partially_supported',
    );
    expect(good.allows_resume_inclusion).toBe(true);
    expect(good.is_blocking).toBe(false);
    expect(good.confidence).toBeGreaterThan(0);
    // The downgrade explains itself instead of looking like a bug.
    expect(good.reasons.map((reason) => reason.rule)).toContain('single_source_only');
    expect(good.reasons.every((reason) => reason.severity !== 'blocker')).toBe(true);

    // ── the fabricated claim is refused ──────────────────────────────────────────────────────
    expect(bad.status, 'numbers with nothing behind them must not reach a résumé').toBe(
      'unsupported',
    );
    expect(bad.allows_resume_inclusion).toBe(false);
    expect(bad.is_blocking).toBe(true);
    const blockerRules = bad.reasons
      .filter((reason) => reason.severity === 'blocker')
      .map((reason) => reason.rule);
    expect(blockerRules, 'the refusal must name the rule it applied').toContain(
      'numeric_without_evidence',
    );
    expect(bad.reasons.map((reason) => reason.rule)).toContain('superlative_language');
    expect(bad.reasons.length).toBeGreaterThan(good.reasons.length);
    expect(bad.confidence).toBeLessThanOrEqual(good.confidence);

    // Both callers get the same envelope, including the honest degradation flag of the provider.
    expect(good.meta.provider).toBe('heuristic');
    expect(good.meta.degraded).toBe(true);
    expect(bad.meta.provider).toBe('heuristic');
  });
});
