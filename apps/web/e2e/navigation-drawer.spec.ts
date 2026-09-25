import { ensureEvidenceBase } from './helpers/pages';
import { expect, test } from './helpers/fixtures';

/**
 * The mobile navigation drawer: open it, navigate from it, close it.
 *
 * This file exists because of a real bug. In PHASE 12 the drawer's overlay was left at
 * `--z-modal` (60) while the panel moved to `--z-drawer` (50), so the backdrop sat *above* the
 * drawer and swallowed every tap on a nav link: the drawer opened, looked correct in a screenshot,
 * and did nothing. No DOM-level test could catch it — jsdom has no stacking order — and the mobile
 * project it would have caught it in only ran when `E2E_MOBILE=1` was set.
 *
 * So the spec does the one thing that fails when the stacking is wrong: it **clicks a link inside
 * the drawer and asserts the route changed**. A drawer that opens but does not navigate is the
 * regression, and no assertion short of a real click on a real link detects it.
 *
 * It runs in the mobile project only: below 768px the sidebar is an off-canvas dialog, while at
 * 1440px it is a static rail and the top bar's open button is `md:hidden`.
 */
test.describe('Navigation drawer', () => {
  test('opens, navigates and closes, with the panel above its own backdrop', async ({
    api,
    signedInPage: page,
  }) => {
    // `/app/jobs` renders real data once the account has evidence, which keeps the destination
    // page from being a skeleton at the moment the drawer closes.
    await ensureEvidenceBase(api);
    await page.goto('/app/dashboard');

    const drawer = page.getByRole('dialog', { name: '导航菜单' });
    await expect(drawer).toHaveCount(0);

    // ── open ───────────────────────────────────────────────────────────────────────────────────
    await page.getByRole('button', { name: '打开导航菜单' }).click();
    await expect(drawer).toBeVisible();
    // The drawer holds the navigation, and it is the *visible* copy of it — the desktop rails are
    // also in the document, so `filter({ visible: true })` is what picks the one being looked at.
    const nav = drawer.getByRole('navigation', { name: '主导航' });
    await expect(nav).toBeVisible();

    // ── navigate from inside the drawer ───────────────────────────────────────────────────────
    // This is the assertion the z-index bug fails: if the backdrop intercepts the tap, Playwright
    // reports the link as covered by another element and the click fails rather than silently
    // no-op'ing.
    await nav.getByRole('link', { name: '岗位与匹配' }).click();
    await expect(page).toHaveURL(/\/app\/jobs$/);
    await expect(page.getByRole('heading', { level: 1, name: 'JD Intelligence' })).toBeVisible();

    // Navigating from the drawer closes it (`onNavigate` on every row) — a drawer left open over
    // the page it just opened is the other half of the same bug.
    await expect(page.getByRole('dialog', { name: '导航菜单' })).toHaveCount(0);

    // ── open, then close without navigating ───────────────────────────────────────────────────
    await page.getByRole('button', { name: '打开导航菜单' }).click();
    await expect(page.getByRole('dialog', { name: '导航菜单' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: '导航菜单' })).toHaveCount(0);
    await expect(page).toHaveURL(/\/app\/jobs$/);

    // ── a second route, to prove the first one was not a coincidence ──────────────────────────
    await page.getByRole('button', { name: '打开导航菜单' }).click();
    const secondNav = page
      .getByRole('dialog', { name: '导航菜单' })
      .getByRole('navigation', { name: '主导航' });
    await secondNav.getByRole('link', { name: '证据图谱' }).click();
    await expect(page).toHaveURL(/\/app\/evidence-graph$/);
    await expect(
      page.getByRole('heading', { level: 1, name: 'Career Evidence Graph' }),
    ).toBeVisible();
    await expect(page.getByRole('dialog', { name: '导航菜单' })).toHaveCount(0);
  });

  test('a route that has not shipped is still not presented as clickable', async ({
    signedInPage: page,
  }) => {
    await page.goto('/app/dashboard');
    await page.getByRole('button', { name: '打开导航菜单' }).click();

    const nav = page
      .getByRole('dialog', { name: '导航菜单' })
      .getByRole('navigation', { name: '主导航' });

    // `nav-config.ts` still badges PHASE 5/7 routes `live: false` on purpose: a scaffold must not
    // pretend a page exists. The four PHASE 13 routes are live and are therefore links.
    await expect(nav.getByRole('link', { name: 'GitHub' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: '简历 Copilot' })).toHaveCount(0);
    for (const label of ['证据图谱', '岗位与匹配', '断言验证', '模拟面试']) {
      await expect(nav.getByRole('link', { name: label })).toHaveCount(1);
    }

    const badge = nav.locator('[aria-disabled="true"]', { hasText: 'GitHub' });
    await expect(badge).toBeVisible();
    await expect(badge).toContainText('PHASE 5');
  });
});
