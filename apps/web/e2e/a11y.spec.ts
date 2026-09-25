import type { Locator, Page } from '@playwright/test';

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
 *
 * PHASE 14 added two tests axe cannot write for us, because axe inspects the DOM and these are about
 * behaviour:
 *
 * * `scrollable-region-focusable` was fixed by giving the interview plan-basis list a tab stop, and
 *   "it has a `tabindex`" is not the same claim as "the keyboard can read it". The test tabs to it
 *   and then scrolls it with the keyboard, because a tab stop on a region that does not actually
 *   scroll is worse than nothing: it is a stop that announces content the user still cannot read.
 * * `prefers-reduced-motion` is a media query in `globals.css` plus `--dur-*` tokens, and a
 *   stylesheet rule that stopped matching would be invisible to every other test here. The test
 *   measures the real computed animation duration with the preference on *and* off, so a run where
 *   the animations never ran at all cannot pass as "reduced motion works".
 */

/**
 * The computed `animation-duration` of a layer, in milliseconds.
 *
 * Read from the live element rather than from the stylesheet, because the claim being checked is
 * about what the browser resolved: the reduced-motion rule is unlayered `!important` CSS competing
 * with Tailwind's `@layer utilities` animation utilities, and only the computed value says who won.
 * `animation-duration` may be a comma-separated list — the first entry is the layer's own.
 */
async function layerAnimationMs(layer: Locator): Promise<number> {
  return layer.evaluate((element) => {
    const raw = getComputedStyle(element).animationDuration;
    const value = Number.parseFloat(raw);
    return raw.trim().endsWith('ms') ? value : value * 1000;
  });
}

/** Open a layer, measure its entry animation, close it again. */
async function measureLayer(page: Page, trigger: string, dialogName: string): Promise<number> {
  await page.getByRole('button', { name: trigger }).filter({ visible: true }).first().click();
  const layer = page.getByRole('dialog', { name: dialogName });
  await expect(layer).toBeVisible();
  const milliseconds = await layerAnimationMs(layer);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  return milliseconds;
}

/**
 * Every animated layer this viewport actually has, by accessible name.
 *
 * The command palette exists at both widths (the top bar renders a wide trigger above `lg` and an
 * icon trigger below it); the navigation drawer only exists below `md`, where it *is* the sidebar.
 * Measuring whatever is present keeps one test honest at 1440px and 375px instead of skipping the
 * drawer — which is the layer a mobile keyboard user opens most often.
 */
async function measureLayerAnimations(page: Page): Promise<Record<string, number>> {
  const measured: Record<string, number> = {};
  measured['命令面板'] = await measureLayer(page, '打开命令面板', '命令面板');
  if (
    (await page.getByRole('button', { name: '打开导航菜单' }).filter({ visible: true }).count()) > 0
  ) {
    measured['导航菜单'] = await measureLayer(page, '打开导航菜单', '导航菜单');
  }
  return measured;
}

/**
 * Press Tab until `target` owns focus; return the number of presses, or 0 if it never did.
 *
 * A bounded walk rather than `target.focus()`, because the claim is reachability *in the tab order*:
 * an element can be focusable and still be unreachable if something earlier in the document traps
 * Tab. The bound is reported on failure so the message says how far the walk got.
 */
async function tabUntilFocused(page: Page, target: Locator, maxPresses: number): Promise<number> {
  for (let press = 1; press <= maxPresses; press += 1) {
    await page.keyboard.press('Tab');
    if (await target.evaluate((element) => element === document.activeElement)) return press;
  }
  return 0;
}

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

  test('the interview plan-basis list is reachable and scrollable by keyboard', async ({
    evidenceBase,
    jobId,
    signedInPage: page,
  }) => {
    expect(evidenceBase.total).toBeGreaterThan(0);
    await openPopulatedPage(page, jobId, 'interview');
    await expect(page.locator('[data-interview-workspace]')).toBeVisible();

    const list = page.getByRole('list', { name: /题目依据列表/ });
    await expect(list).toHaveCount(1);

    // The region has to genuinely overflow, or "reachable" is a claim about nothing: `tabIndex`
    // on a list that fits on screen would pass this test and fix nobody's problem.
    const overflow = await list.evaluate((element) => element.scrollHeight - element.clientHeight);
    expect(
      overflow,
      'the plan-basis list must scroll for this test to mean anything — if it now fits, the ' +
        'scrollable-region-focusable fix is unnecessary and should be removed with this test',
    ).toBeGreaterThan(0);

    // 1. `Tab` reaches it. This is what axe's rule is actually about.
    const presses = await tabUntilFocused(page, list, 150);
    expect(
      presses,
      `Tab did not reach the plan-basis list in 150 stops (last focus: ` +
        `${await page.evaluate(() => document.activeElement?.tagName ?? 'nothing')})`,
    ).toBeGreaterThan(0);

    // 2. …and it shows a focus ring, so the new tab stop is visible rather than a black hole.
    //    That comes from the global `:focus-visible` rule in `styles/globals.css`. Asserting the
    //    *computed* value rather than the class is not pedantry: PHASE 14 measured the same
    //    `focus-visible:outline-*` utilities rendering `outline-style: none` on every Button and
    //    sidebar link, because Tailwind's `outline-none` sets `--tw-outline-style: none` and the
    //    width utility reads it back (see `packages/ui/src/lib/focus-ring.ts`).
    const ring = await list.evaluate((element) => {
      const style = getComputedStyle(element);
      return { line: style.outlineStyle, width: Number.parseFloat(style.outlineWidth) };
    });
    expect(ring.line, 'the focused region must draw an outline').toBe('solid');
    expect(ring.width, 'docs/UI.md §9 specifies a 2px ring').toBeGreaterThanOrEqual(2);

    // 3. The keyboard scrolls the region itself.
    //
    //    Every read here is taken *after the scroll settles*, and that is a measurement fix rather
    //    than a workaround: the document sets `scroll-behavior: smooth`, so a read taken straight
    //    after the key press catches an animation mid-flight. Measured on the live stack, the same
    //    two ArrowDown presses read as `0` immediately and as `80` once settled, and the first press
    //    also scrolls the page into position (html 243 → 675) before the region starts moving.
    //    Asserting on the unsettled value would have been a flake that blamed the product.
    type Geometry = { top: number; max: number };
    const geometry = (): Promise<Geometry> =>
      list.evaluate((element) => ({
        top: element.scrollTop,
        max: element.scrollHeight - element.clientHeight,
      }));

    const before = (await geometry()).top;
    for (let press = 0; press < 2; press += 1) {
      await page.keyboard.press('ArrowDown');
      await page.waitForTimeout(300);
    }
    expect(
      (await geometry()).top,
      'ArrowDown must scroll the focused region (measured: 40px per press)',
    ).toBeGreaterThan(before);

    // 4. PageDown walks the region to its end — the functional outcome. Without it a keyboard user
    //    could not read past the first screenful of plan rows, which is exactly the harm the
    //    `scrollable-region-focusable` violation described. Bounded, and it stops as soon as the
    //    end is reached, so a future layout that fits in one screenful cannot make this spin.
    let scrolled = await geometry();
    for (let press = 0; press < 8 && scrolled.max - scrolled.top > 1; press += 1) {
      await page.keyboard.press('PageDown');
      await page.waitForTimeout(300);
      scrolled = await geometry();
    }
    expect(
      scrolled.max - scrolled.top,
      `PageDown must scroll the focused region to its end (stopped at ${scrolled.top} of ${scrolled.max})`,
    ).toBeLessThanOrEqual(1);
  });

  test('prefers-reduced-motion neutralises the dialog and drawer animations', async ({
    signedInPage: page,
  }) => {
    await page.goto('/app/dashboard');
    await expect(
      page.getByRole('button', { name: '打开命令面板' }).filter({ visible: true }),
    ).toBeVisible();

    // Measured in both directions on purpose. Asserting only "with the preference the duration is
    // 0" would also pass if the animation had been deleted, or if the selector had stopped
    // matching — the run has to show the animation first, then show it gone.
    const animated = await measureLayerAnimations(page);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const reduced = await measureLayerAnimations(page);

    expect(Object.keys(animated).length).toBeGreaterThan(0);
    expect(Object.keys(reduced)).toEqual(Object.keys(animated));
    for (const [name, milliseconds] of Object.entries(animated)) {
      expect(milliseconds, `${name} must animate while motion is allowed`).toBeGreaterThan(100);
    }
    for (const [name, milliseconds] of Object.entries(reduced)) {
      expect(
        milliseconds,
        `${name} must not animate under prefers-reduced-motion`,
      ).toBeLessThanOrEqual(1);
    }
  });
});
