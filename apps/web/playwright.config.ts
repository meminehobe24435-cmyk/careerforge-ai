import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright end-to-end configuration for the CareerForge web app.
 *
 * Three environment facts drive this file, all of them deliberate rather than incidental:
 *
 * 1. **No `webServer` block.** The stack is two processes and the order matters: the API must be
 *    listening before `next start` serves a page whose client fetches it, and the API's
 *    `CORS_ORIGINS` has to name the origin the browser will actually use. A `webServer` block can
 *    only start one of them and would have to guess the other's URL, so the stack is started by
 *    the caller (see the header of `e2e/cors.spec.ts` for the exact commands).
 * 2. **`channel: 'chrome'`.** The browsers Playwright ships are not installed here and this
 *    machine must not download them; the already-installed Google Chrome is used instead. Nothing
 *    in this config ever triggers a browser download.
 * 3. **`workers: 1`.** Every flow shares one database and one demo account, so the specs are
 *    written to be independent in *setup* (each one creates what it needs through the API) but
 *    they must not race each other's writes.
 *
 * ## Both projects run by default
 *
 * Until PHASE 13 the mobile project existed but was inert unless `E2E_MOBILE=1` was set, so the one
 * regression it was written to catch — the PHASE 12 z-index bug where the drawer's backdrop sat
 * above the drawer panel and swallowed every tap on a nav link — only fired when somebody
 * remembered the flag. `pnpm test:e2e` now runs both projects: the guard runs by default or it is
 * not a guard.
 *
 * The two projects do **not** run the same file list, and the split is deliberate:
 *
 * * `desktop` runs everything except the drawer spec, which asserts against an element that is
 *   `md:hidden` and therefore cannot be exercised at 1440px;
 * * `mobile` runs the specs whose *layout* differs at 375px — the four PHASE 13 pages, the
 *   dashboard, the drawer and the axe gate — so the mobile run is a real second look at those
 *   pages rather than the same 1440px assertions with a smaller viewport. The specs that pin
 *   transport rather than layout (`cors.spec.ts`, `ai-runs.spec.ts`) run once, on the desktop
 *   project, because a second identical run adds minutes and no information.
 *
 * `E2E_MOBILE=1 pnpm test:e2e` is still honoured for compatibility, and `pnpm test:e2e:mobile`
 * (`--project=mobile`) still selects the mobile project alone.
 */
const baseURL = process.env.E2E_BASE_URL?.trim() || 'http://127.0.0.1:3318';

/** Specs that only mean something below the `md` breakpoint (768px). */
const MOBILE_ONLY_SPECS = ['**/navigation-drawer.spec.ts'];

/**
 * The specs the mobile project runs: the pages whose layout is different at 375px, plus the gate
 * specs that are re-run at the narrow width on purpose (axe, and the navigation drawer).
 */
const MOBILE_SPECS = [
  '**/dashboard.spec.ts',
  '**/jd-analysis.spec.ts',
  '**/evidence-graph.spec.ts',
  '**/claim-validation.spec.ts',
  '**/interview.spec.ts',
  '**/navigation-drawer.spec.ts',
  '**/a11y.spec.ts',
];

export default defineConfig({
  testDir: './e2e',
  // One failure at a time is enough to read; the reporter is the list one so the CI log carries
  // the assertion text rather than a link to an artifact the log cannot open.
  reporter: [['list']],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  use: {
    baseURL,
    channel: 'chrome',
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
    video: 'off',
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
    // The app writes `data-testid` on the few panels whose content is its own thing; role and
    // text locators are preferred everywhere else.
    testIdAttribute: 'data-testid',
  },
  projects: [
    {
      name: 'desktop',
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome',
        viewport: { width: 1440, height: 900 },
      },
      // The drawer does not exist at 1440px: the top bar's open button is `md:hidden` and the
      // sidebar is a static rail, so running the drawer spec here would assert on nothing.
      testIgnore: MOBILE_ONLY_SPECS,
    },
    {
      name: 'mobile',
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome',
        viewport: { width: 375, height: 812 },
        isMobile: true,
        hasTouch: true,
      },
      testMatch: MOBILE_SPECS,
    },
  ],
});
