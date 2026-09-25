import { assertAccessibleNodeIndex, expectNoBlockingViolations, runAxe } from './helpers/axe';
import { openPopulatedPage } from './helpers/pages';
import { expect, test } from './helpers/fixtures';

/**
 * E2E 6 路 The accessibility gate (`@axe-core/playwright`) over every PHASE 13 surface.
 *
 * Runs on Dashboard, Jobs, Evidence Graph, Validator and Interview, at both project viewports:
 * the desktop project measures the 1440px layouts, the mobile project measures the 375px ones.
 * Layouts differ enough at 375px (the graph's canvas disappears, the tables become card lists,
 * the drawer becomes a bottom sheet) that a single-width run would be a gate over half the product.
 *
 * `critical` and `serious` fail; `moderate` and `minor` are printed and annotated. The counters are
 * printed for every page on every run, so "0 critical" is visible as a measurement rather than as
 * silence.
 *
 * Each page is populated before axe runs, from the worker-scoped `evidenceBase`/`jobId` fixtures
 * (see `helpers/fixtures.ts` for why the setup is worker-scoped: the `upload` bucket is 20 requests
 * per hour per user). This is not decoration: axe reports *nothing* on a loading skeleton 鈥?an empty
 * page has no violations because it has no content 鈥?so a gate that measured the shell would pass
 * forever while the real page drifted.
 *
 * Every test also asserts its own ready selector, so a page that stopped rendering its data fails
 * here loudly instead of passing an accessibility audit of an error state.
 */
test.describe('Accessibility gate', () => {
  test('dashboard has no critical or serious violations', async ({
    evidenceBase,
    jobId,
    signedInPage: page,
  }) => {
    expect(evidenceBase.total).toBeGreaterThan(0);
    expect(jobId.length).toBeGreaterThan(0);
    await openPopulatedPage(page, jobId, 'dashboard');
    await expect(page.locator('section[aria-labelledby="dash-strength-heading"]')).toBeVisible();
    await expectNoBlockingViolations(await runAxe(page, 'dashboard', test.info()), test.info());
  });

  test('jobs has no critical or serious violations', async ({
    evidenceBase,
    jobId,
    signedInPage: page,
  }) => {
    expect(evidenceBase.kinds['document_chunk'] ?? 0).toBeGreaterThan(0);
    await openPopulatedPage(page, jobId, 'jobs');
    // The parsed result is on screen before the audit, not a form and not a skeleton.
    await expect(page.getByRole('heading', { name: 'Required skills' })).toBeVisible();
    await expectNoBlockingViolations(await runAxe(page, 'jobs', test.info()), test.info());
  });

  test('evidence graph has no critical or serious violations, and its node list is the equivalent', async ({
    evidenceBase,
    jobId,
    signedInPage: page,
  }) => {
    expect(evidenceBase.total).toBeGreaterThan(0);
    await openPopulatedPage(page, jobId, 'evidence-graph');
    await expect(page.getByTestId('node-index')).toBeVisible();

    // Full canvas accessibility is not achievable for a pannable, zoomable picture 鈥?so the
    // requirement is a real equivalent: the same nodes as named, keyboard-reachable buttons that
    // open the same drawer. That is asserted, not assumed.
    await assertAccessibleNodeIndex(page);

    await expectNoBlockingViolations(
      await runAxe(page, 'evidence-graph', test.info()),
      test.info(),
    );
  });

  test('validator has no critical or serious violations', async ({
    evidenceBase,
    jobId,
    signedInPage: page,
  }) => {
    expect(evidenceBase.manual.kind).toBe('manual');
    await openPopulatedPage(page, jobId, 'validator');
    // The verdict, its sources and its rules are all rendered 鈥?the panels the audit is about.
    await expect(page.getByTestId('verdict-badge')).toBeVisible();
    await expect(page.getByTestId('evidence-source').first()).toBeVisible();
    await expectNoBlockingViolations(await runAxe(page, 'validator', test.info()), test.info());
  });

  test('interview has no critical or serious violations', async ({
    evidenceBase,
    jobId,
    signedInPage: page,
  }) => {
    expect(evidenceBase.total).toBeGreaterThan(0);
    await openPopulatedPage(page, jobId, 'interview');
    // The workspace, with a question asked and one answer evaluated.
    await expect(page.locator('[data-interview-workspace]')).toBeVisible();
    await expect(page.locator('[data-evaluation]')).toBeVisible();
    await expectNoBlockingViolations(await runAxe(page, 'interview', test.info()), test.info());
  });
});
