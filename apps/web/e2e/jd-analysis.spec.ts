import { JOB_DESCRIPTION } from './helpers/dataset';
import { expect, test } from './helpers/fixtures';

/**
 * E2E 2 · JD analysis (`/app/jobs`) — now a page, so this spec drives the page.
 *
 * Until PHASE 13 this file called `POST /jobs/analyze` with a bearer token and then asserted the
 * *dashboard* showed the result, because `/app/jobs` did not exist. That gap is closed: the flow
 * below is what a user does — paste the posting into the textarea, press **Analyze**, read the
 * parsed role, the three-level skill tree, the score breakdown and the gap list off the screen.
 *
 * The assertions are still split honestly, and the split is different now:
 *
 * * the **API contract** (what the parser extracted, which gaps the match engine found, whether
 *   every requirement quotes the JD) is asserted against the live response, because the UI is
 *   supposed to be a faithful rendering of it rather than a second source of truth;
 * * the **rendering** is asserted in the browser against that same response — the skill rows the
 *   page draws must carry the canonical ids the API returned, and the figures on screen must be
 *   the API's figures, not re-derived ones.
 *
 * Nothing waits on a fixed delay: every wait is either Playwright's auto-waiting on a real element
 * or `expect.poll` on the API's own state.
 */
test.describe('JD analysis', () => {
  test('a pasted JD is analysed through the form and the parsed result renders', async ({
    api,
    evidenceBase,
    signedInPage: page,
  }) => {
    // The match reads the account's evidence; without it every requirement would be a gap and the
    // spec would be asserting about an empty account rather than about the page. The worker fixture
    // prepares it once for the whole run (the `upload` bucket is 20 requests per *hour*).
    expect(
      evidenceBase.kinds['document_chunk'] ?? 0,
      'the worker fixture must have built evidence before the page is read',
    ).toBeGreaterThan(0);

    await page.goto('/app/jobs');

    // ── the empty state is a real state, and it says what to do ─────────────────────────────────
    await expect(page.getByRole('heading', { level: 1, name: 'JD Intelligence' })).toBeVisible();
    await expect(page.getByText('还没有分析结果')).toBeVisible();
    // Analyze is disabled until there is something to analyse — a button that no-ops is worse than
    // a disabled one.
    await expect(page.getByRole('button', { name: 'Analyze' })).toBeDisabled();

    // ── type the posting and run it ─────────────────────────────────────────────────────────────
    await page.getByLabel('JD text').fill(JOB_DESCRIPTION);
    const analyze = page.getByRole('button', { name: 'Analyze' });
    await expect(analyze).toBeEnabled();
    await analyze.click();

    // The result half waits for the API; `Match figures` is the last panel to arrive because the
    // score comes from a second call (`POST /jobs/{id}/match`).
    await expect(page.getByRole('heading', { name: 'Match figures' })).toBeVisible();

    // ── what the API decided ───────────────────────────────────────────────────────────────────
    const jobId = new URL(page.url()).searchParams.get('job');
    expect(jobId, 'the address bar must hold the job id so the analysis is shareable').toBeTruthy();
    if (!jobId) throw new Error('unreachable');

    const job = await api.json<{ id: string; role: string; company: string | null }>(
      'GET',
      `/jobs/${jobId}`,
    );
    expect(job.role).toContain('嵌入式软件工程师');

    const tree = await api.skillTree(jobId);
    expect(tree.required.length).toBeGreaterThan(0);
    const requiredNames = tree.required.map((item) => item.rawText);
    expect(requiredNames).toEqual(expect.arrayContaining(['STM32', 'FreeRTOS', 'CAN']));
    for (const item of tree.required.slice(0, 5)) {
      expect(
        item.jdEvidence.length,
        `requirement ${item.rawText} must quote the JD`,
      ).toBeGreaterThan(0);
    }

    // `POST` — the computed path. `GET /jobs/{id}/match` returns the *stored* match, and that
    // response is built without `evidenceCoverage`/`confidence` (they arrive as the model's
    // defaults, which is why `MatchFiguresPanel` prints `—` and names the endpoint that does report
    // them on that path). Asserting a coverage of `> 0` therefore needs the call that computes it.
    const match = await api.matchJob(jobId);
    expect(match.score).toBeGreaterThan(0);
    expect(Object.keys(match.dimensions).length).toBeGreaterThan(0);
    expect(match.why.formula.length).toBeGreaterThan(0);
    expect(match.why.algorithmVersion).toBeTruthy();
    expect(match.evidenceCoverage).toBeGreaterThan(0);

    // The fixture JD asks for more than the fixture résumé shows — the gap has to be reported
    // rather than left silent.
    const gapNames = match.gaps.map((gap) => gap.displayName);
    expect(
      gapNames.length,
      'the fixture JD asks for more than the fixture résumé shows',
    ).toBeGreaterThan(0);
    expect(gapNames.some((name) => ['SPI', 'UART', 'MCU'].includes(name))).toBe(true);

    // ── what the reader sees: the parsed role as a heading ──────────────────────────────────────
    await expect(page.getByRole('heading', { level: 2, name: job.role })).toBeVisible();

    // The score is the API's score, printed by the panel's own `formatPoints` — which is
    // `String(value)`, so the page does not round a number it did not compute.
    await expect(page.locator('[aria-label="匹配分数"]')).toHaveText(String(match.score));

    // The three levels are labelled, and the required level is where the JD's own requirements go.
    await expect(page.getByRole('heading', { name: 'Required skills' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Preferred skills' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Bonus skills' })).toBeVisible();

    // Every required skill the API returned has a row on screen, under the id the page keyed it by.
    const renderedSkills = await page
      .locator('[data-skill]')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-skill')));
    for (const item of tree.required) {
      const key = item.canonicalId ?? item.rawText;
      expect(renderedSkills, `requirement ${item.rawText} must have a rendered row`).toContain(key);
    }

    // The gap list renders the first five gaps the engine reported, in the engine's order, keyed
    // by canonical id — so the rendered list is checkable against the payload without trusting the
    // page's own arithmetic (`MatchConclusions` slices to `SHOWN = 5` and prints the total).
    await expect(page.getByRole('heading', { name: 'Gaps' })).toBeVisible();
    const renderedGaps = await page
      .locator('[data-gap]')
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-gap')));
    expect(renderedGaps).toEqual(match.gaps.slice(0, 5).map((gap) => gap.canonicalId));

    // ── the analysis is addressable: reloading the link restores it ─────────────────────────────
    await page.goto(`/app/jobs?job=${encodeURIComponent(jobId)}`);
    await expect(page.getByRole('heading', { level: 2, name: job.role })).toBeVisible();
    await expect(page.locator('[data-skill]').first()).toBeVisible();
    await expect(page.getByText('还没有分析结果')).toHaveCount(0);
  });
});
