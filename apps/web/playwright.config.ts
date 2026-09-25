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
 * The mobile project is declared unconditionally but selected only when asked for, so a default
 * run stays fast. `E2E_MOBILE=1 pnpm test:e2e` and `pnpm test:e2e:mobile` both work — the second
 * one is why the project is also enabled when `--project=mobile` is on the command line.
 */
const baseURL = process.env.E2E_BASE_URL?.trim() || 'http://127.0.0.1:3318';

function wantsMobileProject(): boolean {
  if (process.env.E2E_MOBILE === '1') return true;
  const argv = process.argv.slice(2);
  return argv.some(
    (arg, index) =>
      arg === '--project=mobile' || (arg === '--project' && argv[index + 1] === 'mobile'),
  );
}

const mobileEnabled = wantsMobileProject();

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
      // `testIgnore` rather than omitting the project: a project that does not exist makes
      // `--project=mobile` an error, and a project that exists but matches nothing is a no-op.
      ...(mobileEnabled ? {} : { testIgnore: '**/*' }),
    },
  ],
});
