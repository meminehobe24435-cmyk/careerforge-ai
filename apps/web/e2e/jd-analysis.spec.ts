import { JOB_DESCRIPTION } from './helpers/dataset';
import { expect, test } from './helpers/fixtures';

/**
 * E2E 2 · JD analysis (Chinese job description).
 *
 * **There is no JD-analysis UI in this app.** `nav-config.ts` marks `/app/jobs` `live: false` with a
 * `PHASE 4` badge and the sidebar renders it as a non-clickable item; `apps/web/src/app/**` has no
 * route under `/app/jobs`, and the dashboard's recent-jobs empty state says as much in words
 * ("JD 分析入口在 PHASE 4 上线"). So the analysis is submitted through the real endpoint
 * (`POST /jobs/analyze`, the same endpoint the future form will call) with the same bearer token
 * the browser holds, and the assertions are split honestly:
 *
 * * what the API returns — role, required skill names, the match score, the dimensions that add up
 *   to it and at least one explicit gap — is asserted against the live response;
 * * what a reader can actually see is asserted in the browser: the analysed posting appears in the
 *   dashboard's 最近岗位 table with its role and its match score, and the match is reflected in the
 *   Resume Match and Skill Coverage stat cards.
 *
 * The one thing this spec cannot assert is a *rendered* skill list or gap list, because no page
 * renders one. That is a real coverage gap and it is reported as one rather than papered over with
 * a synthetic page.
 */
test.describe('JD analysis', () => {
  test('a Chinese JD is parsed, matched, and the result is visible on the dashboard', async ({
    api,
    signedInPage: page,
  }) => {
    const job = await api.analyzeJob(JOB_DESCRIPTION);
    if (!job.id) throw new Error('POST /jobs/analyze returned no job id');

    // Parsed role: the first line of the posting, stored verbatim.
    const company = job.company ?? '';
    expect(job.role).toContain('嵌入式软件工程师');
    expect(company).toContain('某某智能科技');
    expect(job.requiredCount).toBeGreaterThan(0);
    expect(job.parseConfidence).toBeGreaterThan(0);

    // Skill names, at the three documented levels, each carrying the JD sentence behind it.
    const tree = await api.skillTree(job.id);
    const requiredNames = tree.required.map((item) => item.rawText);
    expect(requiredNames).toEqual(
      expect.arrayContaining(['STM32', 'FreeRTOS', 'CAN', 'PID Control']),
    );
    const preferredNames = tree.preferred.map((item) => item.rawText);
    expect(preferredNames.length).toBeGreaterThan(0);
    for (const item of tree.required.slice(0, 5)) {
      expect(
        item.jdEvidence.length,
        `requirement ${item.rawText} must quote the JD`,
      ).toBeGreaterThan(0);
    }

    // The match: a score, explained dimensions, a strength figure and an explicit gap.
    const match = await api.matchJob(job.id);
    expect(match.score).toBeGreaterThan(0);
    expect(Object.keys(match.dimensions).length).toBeGreaterThan(0);
    expect(match.why.formula.length).toBeGreaterThan(0);
    expect(match.why.algorithmVersion).toBeTruthy();
    expect(match.evidenceCoverage).toBeGreaterThan(0);

    // The gap has to be a requirement the fixture résumé genuinely does not mention: it never
    // speaks of SPI or UART, so at least one of them must come back as a gap rather than silence.
    const gapNames = match.gaps.map((gap) => gap.displayName);
    expect(
      gapNames.length,
      'the fixture JD asks for more than the fixture résumé shows',
    ).toBeGreaterThan(0);
    expect(gapNames.some((name) => ['SPI', 'UART', 'MCU'].includes(name))).toBe(true);
    for (const gap of match.gaps) {
      expect(
        gap.canonicalId.length,
        `gap ${gap.displayName} must be a taxonomy id, not free text`,
      ).toBeGreaterThan(0);
      expect(['required', 'preferred', 'bonus']).toContain(gap.requirement);
    }

    // ── what a reader sees ───────────────────────────────────────────────────────────────────
    const dashboard = await api.dashboard();
    const recent = dashboard.recentJobs.find((entry) => entry.jobId === job.id);
    if (!recent) {
      throw new Error(
        `job ${job.id} was analysed but does not appear in GET /dashboard → recentJobs`,
      );
    }
    expect(recent.role).toBe(job.role);

    await page.goto('/app/dashboard');
    const recentJobsTable = page
      .locator('section[aria-labelledby="dash-jobs-heading"]')
      .getByRole('table');
    await expect(recentJobsTable).toBeVisible();

    const row = recentJobsTable
      .getByRole('row')
      .filter({ has: page.getByRole('cell', { name: job.role }) });
    await expect(row).toHaveCount(1);
    await expect(row.getByRole('cell', { name: company })).toBeVisible();
    // The score cell renders `formatScore(matchScore)`: an integer, or an em dash if the job was
    // never matched — which is why the expectation is computed from the payload, not hard-coded.
    const renderedScore = recent.matchScore === null ? '—' : recent.matchScore.toFixed(0);
    await expect(row.getByRole('cell', { name: renderedScore, exact: true })).toBeVisible();

    // The match's strength and coverage are rendered in the stat cards. Both are computed by the
    // app from the same payload, so the expectation follows the app's own formatting.
    const strengthSection = page.locator('section[aria-labelledby="dash-strength-heading"]');
    expect(dashboard.stats.resumeMatch).toBeCloseTo(match.score / 100, 4);
    expect(dashboard.stats.skillCoverage).toBeGreaterThan(0);

    // Two cards can legitimately show the same percentage, so these are `first()` rather than a
    // strict single match: the claim is "this figure is on screen", and the figures themselves are
    // pinned by the API assertions above.
    await expect(
      strengthSection
        .getByText(`${(dashboard.stats.resumeMatch * 100).toFixed(0)}%`, { exact: true })
        .first(),
    ).toBeVisible();
    await expect(
      strengthSection
        .getByText(`${(dashboard.stats.skillCoverage * 100).toFixed(0)}%`, { exact: true })
        .first(),
    ).toBeVisible();
  });
});
