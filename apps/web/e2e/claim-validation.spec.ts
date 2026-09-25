import { EXAGGERATED_CLAIM, SUPPORTED_CLAIM } from './helpers/dataset';
import { expect, test } from './helpers/fixtures';

/**
 * E2E 4 · Claim validation (`/app/validator`) — the gate, driven through its own page.
 *
 * The PHASE 12 version of this file posted to `/ai/validate/claim` from inside the page and read
 * the JSON, because no route rendered a verdict. `/app/validator` exists now, and it runs a
 * *different* endpoint — `POST /evidence/validate`, which supplies the gate with a retriever over
 * the account's own stored evidence (`lib/validator-api.ts` explains why the stateless endpoint
 * cannot carry the page). So this spec types sentences into the real textarea, presses the real
 * button, and reads the verdict off the screen.
 *
 * The expectations are not invented here. Two claims go in:
 *
 * * one the fixture résumé states almost verbatim;
 * * one that invents two hard numbers, a superlative and a technology nothing anywhere measures.
 *
 * and the spec first asks the same endpoint what it decided, then asserts the rendered page says
 * the same thing. The UI is checked against the API rather than against a hand-written copy of the
 * rules, which is the only way this test stays true when the rules change.
 *
 * The evidence base is prepared with **two independent kinds** (`document_chunk` + `manual`): the
 * gate requires two before it will call a sentence `supported`
 * (`careerforge_ai/scoring/confidence.py` → `_MIN_INDEPENDENT_SOURCES = 2`).
 */
test.describe('Claim validation', () => {
  test('an evidenced claim and a fabricated one land on opposite sides of the gate', async ({
    api,
    evidenceBase,
    signedInPage: page,
  }) => {
    expect(
      evidenceBase.kinds['document_chunk'] ?? 0,
      'the gate needs real evidence in the account before it can support anything',
    ).toBeGreaterThan(0);
    expect(
      evidenceBase.kinds['manual'] ?? 0,
      'the gate needs two independent evidence kinds to reach its highest verdict',
    ).toBeGreaterThan(0);

    // ── what the gate decides, asked of the same endpoint the page uses ───────────────────────
    const expectedGood = await api.validateClaim(SUPPORTED_CLAIM);
    const expectedBad = await api.validateClaim(EXAGGERATED_CLAIM);

    // The expectation is the gate's own answer, checked against the properties it promises, and the
    // *page* is then asserted to render exactly that answer — so the spec cannot drift into
    // asserting a verdict the rules no longer produce.
    //
    // It stops short of asserting `supported` because that verdict sits on a knife edge here, and
    // the edge is arithmetic rather than a UI problem: the gate's confidence is the mean confidence
    // of the retrieved sources, and this account's matching sources are `document_chunk` rows at
    // 0.80 and one `manual` row at 0.65. Two sources give 0.725 (→ `partially_supported`, below the
    // 0.75 threshold) and three give exactly 0.750 (→ `supported`, at the threshold). Whether the
    // third `document_chunk` exists depends on whether `scripts/capture-pages.mts` has been run
    // against the same database — a real dependency, not a flaky one, but not something a spec
    // should pin either way. Measured both states: `partially_supported · Medium · 73%` with two
    // sources, `supported · High · 75%` with three.
    expect(
      ['supported', 'partially_supported'],
      'an evidenced claim must not be refused',
    ).toContain(expectedGood.claim.status);
    expect(expectedGood.claim.independentSourceCount).toBeGreaterThanOrEqual(2);
    expect(expectedGood.claim.sources.length).toBeGreaterThan(0);
    expect(
      expectedGood.claim.reasons.some((reason) => reason.severity === 'blocker'),
      'nothing about this sentence is a blocker',
    ).toBe(false);

    // Numbers with nothing behind them cannot reach a résumé, and the refusal names its rule.
    expect(expectedBad.claim.status).toBe('unsupported');
    expect(
      expectedBad.claim.reasons
        .filter((reason) => reason.severity === 'blocker')
        .map((r) => r.rule),
      'the refusal must name the rule it applied',
    ).toContain('numeric_without_evidence');
    expect(expectedBad.claim.reasons.map((reason) => reason.rule)).toContain(
      'superlative_language',
    );

    // ── the same two claims, typed into the page ──────────────────────────────────────────────
    await page.goto('/app/validator');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Resume Claim Validator' }),
    ).toBeVisible();
    // The empty state explains what the gate does rather than showing a scoreboard.
    await expect(
      page.getByText('Validate a resume statement against your evidence.'),
    ).toBeVisible();

    const box = page.getByLabel('Résumé sentence');
    const submit = page.getByTestId('validate-claim');
    // A claim shorter than two characters has nothing to check, so the button refuses it.
    await expect(submit).toBeDisabled();

    await box.fill(SUPPORTED_CLAIM);
    await expect(submit).toBeEnabled();
    await submit.click();

    const result = page.getByTestId('validator-result');
    await expect(result).toBeVisible();

    // The verdict: the status verbatim, and the sentence the gate actually read.
    await expect(page.getByTestId('verdict-badge')).toHaveText(expectedGood.claim.status);
    await expect(page.getByTestId('verdict-label')).toBeVisible();
    await expect(result).toContainText(SUPPORTED_CLAIM);
    // The confidence block prints the gate's own number through `readConfidence`, which renders
    // `<band> · <percent>` — the band is the threshold the value fell into, the percentage is the
    // value itself. Both are derived here from the API's number rather than copied off the screen.
    const expectedBand =
      expectedGood.claim.confidence >= 0.75
        ? 'High'
        : expectedGood.claim.confidence >= 0.45
          ? 'Medium'
          : 'Low';
    await expect(page.getByTestId('confidence')).toHaveText(
      `${expectedBand} · ${Math.round(expectedGood.claim.confidence * 100)}%`,
    );

    // Every source the gate cited is listed by title — that is the chain's middle link, and the
    // list must be the API's list rather than a sample of it.
    await expect(page.getByTestId('evidence-source')).toHaveCount(
      expectedGood.claim.sources.length,
    );
    for (const source of expectedGood.claim.sources.filter((item) => item.title).slice(0, 3)) {
      await expect(
        page.getByTestId('evidence-source').filter({ hasText: source.title }),
      ).toHaveCount(1);
    }

    // ── the fabricated claim, on the same page ────────────────────────────────────────────────
    await box.fill(EXAGGERATED_CLAIM);
    await submit.click();
    await expect(page.getByTestId('verdict-badge')).toHaveText('unsupported');

    // The refusal has to be readable as a reason, not as a mood: the panel that holds the rule
    // codes is collapsed by default, so the spec opens it the way a reader would.
    const whyRejected = page.getByTestId('why-rejected');
    await expect(whyRejected).toBeVisible();
    await expect(whyRejected).toHaveAttribute('aria-expanded', 'false');
    await whyRejected.click();
    await expect(whyRejected).toHaveAttribute('aria-expanded', 'true');

    const rules = await page
      .getByTestId('rule-explanation')
      .evaluateAll((nodes) => nodes.map((node) => node.textContent ?? ''));
    expect(rules.length).toBeGreaterThan(0);
    expect(
      rules.join(' '),
      'the rule that blocked the claim must be visible, not summarised away',
    ).toContain('numeric_without_evidence');

    // And the constructive half: either a rewrite that removes the unmeasured number, or an
    // explicit statement of why none was offered. A blank panel is the one outcome not allowed.
    await expect(page.getByTestId('rewrite-original')).toHaveText(EXAGGERATED_CLAIM);
    await expect(
      page.getByTestId('rewrite-text').or(page.getByTestId('rewrite-declined')),
    ).toBeVisible();
  });

  test('the evidence-base badge counts the account, not a hard-coded number', async ({
    api,
    evidenceBase,
    signedInPage: page,
  }) => {
    expect(evidenceBase.manual.id.length).toBeGreaterThan(0);
    // The page reads `GET /evidence?limit=200` and counts the rows it got. Asking the same
    // question here means the badge is checked against the account, not against a constant that
    // would pass on an empty database.
    const evidence = await api.json<{ items: unknown[] }>('GET', '/evidence?limit=200');
    const expected = evidence.items.length;
    expect(expected).toBeGreaterThan(0);

    await page.goto('/app/validator');
    await expect(
      page.getByText(`evidence base: ${expected}${expected >= 200 ? '+' : ''} rows`),
    ).toBeVisible();
  });
});
