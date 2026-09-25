import { API_BASE_URL } from './helpers/api';
import { expect, sidebarNav, STAT_CARD_LABELS, test } from './helpers/fixtures';

/**
 * E2E 1 · Dashboard (`/app/dashboard`, `docs/UI.md` §5.3).
 *
 * What this proves: a session established the way the app stores one gets past the client-side
 * guard, the page renders *real API data* rather than a skeleton or an error panel, and the
 * sidebar navigation actually moves between routes.
 *
 * What it deliberately does not prove: any particular number. The specs share one database and
 * several of them create data through the API, so an assertion like "evidence coverage is 0%" or
 * "there are exactly 2 recent jobs" would be an assertion about test order, not about the app.
 * The structural assertions below hold in every state the suite can leave the account in.
 */
test.describe('Dashboard', () => {
  test('renders the profile strength, the six stat cards and the recent-jobs card from the API', async ({
    signedInPage: page,
    session,
  }) => {
    await page.goto('/app/dashboard');

    // The client-side guard let us through and the greeting carries the signed-in user's name.
    const heading = page.getByRole('heading', { level: 1 });
    await expect(heading).toBeVisible();
    await expect(heading).toContainText(session.user.displayName);

    // The bundle was built against the running API — otherwise the page would render ErrorState.
    await expect(page.getByText(`GET ${API_BASE_URL}/dashboard`)).toBeVisible();
    await expect(page.getByText('Backend not reachable')).toHaveCount(0);

    // Profile Strength: the ring is a role=img with the score in its accessible name.
    const strengthSection = page.locator('section[aria-labelledby="dash-strength-heading"]');
    await expect(strengthSection).toBeVisible();
    const ring = strengthSection.getByRole('img', { name: /^Profile Strength/ });
    await expect(ring).toBeVisible();
    await expect(ring).toHaveAccessibleName(/Profile Strength \d+ \/ 100/);
    await expect(
      strengthSection.getByRole('heading', { level: 3, name: 'Profile Strength' }),
    ).toBeVisible();

    // The six stat cards, by label. Their container is the section the page marks with
    // aria-labelledby; no CSS class is used as a selector anywhere in these specs.
    for (const label of STAT_CARD_LABELS) {
      await expect(strengthSection.getByText(label, { exact: true })).toBeVisible();
    }
    // Every metric has a value: the em dash is what a metric renders when the API omitted it, and
    // the demo account has a profile, so a dash here would mean the payload stopped arriving.
    await expect(strengthSection.getByText('—')).toHaveCount(0);

    // Recent jobs panel (empty state or rows — both are real renderings of `recentJobs`).
    await expect(
      page.getByRole('heading', { level: 3, name: '最近岗位', exact: true }),
    ).toBeVisible();

    // The page states where its numbers come from, and it must not silently substitute others.
    await expect(page.getByText(/本页所有数字均直接来自/)).toBeVisible();
  });

  test('the sidebar navigates and marks the active route', async ({ signedInPage: page }) => {
    await page.goto('/app/dashboard');

    const nav = await sidebarNav(page);
    const overview = nav.getByRole('link', { name: '总览' });
    await expect(overview).toHaveAttribute('aria-current', 'page');

    // A nav item in another group → its route loads and renders its own heading.
    await nav.getByRole('link', { name: '数据分析' }).click();
    await expect(page).toHaveURL(/\/app\/analytics$/);
    await expect(page.getByRole('heading', { level: 1, name: '求职分析' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '投递漏斗' })).toBeVisible();

    // And back: the nav is a router, not a one-way link list.
    const analyticsNav = await sidebarNav(page);
    await expect(analyticsNav.getByRole('link', { name: '数据分析' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await analyticsNav.getByRole('link', { name: '总览' }).click();
    await expect(page).toHaveURL(/\/app\/dashboard$/);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });

  test('a route that has not shipped is not presented as clickable', async ({
    signedInPage: page,
  }) => {
    // `nav-config.ts` marks PHASE 5–8 routes `live: false` on purpose: a scaffold must not pretend
    // a page exists. This test pins that honesty down, because the specs below depend on it.
    await page.goto('/app/dashboard');
    const nav = await sidebarNav(page);

    await expect(nav.getByRole('link', { name: '证据图谱' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: '模拟面试' })).toHaveCount(0);
    await expect(nav.getByRole('link', { name: '断言验证' })).toHaveCount(0);

    const badge = nav.locator('[aria-disabled="true"]', { hasText: '证据图谱' });
    await expect(badge).toBeVisible();
    await expect(badge).toContainText('PHASE 6');
  });
});
