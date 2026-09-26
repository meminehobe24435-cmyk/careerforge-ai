import {
  request as playwrightRequest,
  test as base,
  expect,
  type Locator,
  type Page,
} from '@playwright/test';

import { API_BASE_URL, Api, signIn, type SessionPayload } from './api';
import { ensureEvidenceBase, ensureJob, type EvidenceBase } from './pages';
import { installSession, toBrowserSession } from './session';

/**
 * The fixtures every spec shares.
 *
 * `signedInPage` is a real browser on the app's own origin with the demo session already in
 * `localStorage`, which is what makes the specs read like a user's session rather than like a test
 * harness: `await page.goto('/app/dashboard')` lands on the authenticated dashboard.
 *
 * The API context, the sign-in, the evidence base and the posting are all *worker*-scoped, and that
 * is a correctness fix rather than an optimisation. `POST /auth/demo` is limited to 10 requests per
 * minute per IP (`middleware/ratelimit.py`, `docs/API.md` §1.7), so signing in once per test pushed
 * a second consecutive run over the limit and turned every spec into a `429`. The evidence base is
 * worse: `POST /profile/import` and `POST /documents/{id}/analyze` both draw on the `upload` bucket,
 * which is **20 requests per hour per user** — so a suite where ten specs each prepared their own
 * evidence spent its entire hourly budget in one run and failed with `429` from then on. One setup
 * per worker is also what a real user does: they import their material once, then use the product.
 */
export interface TestFixtures {
  /** A page with the session installed and nothing loaded yet. */
  signedInPage: Page;
}

export interface WorkerFixtures {
  /** Internal: one API context and one session for the whole worker. */
  apiContext: { session: SessionPayload; api: Api };
  /** `data` of `POST /auth/demo`: the token and user the browser will also be given. */
  session: SessionPayload;
  /** The same API, used for setup and for the flows whose UI is not shipped. */
  api: Api;
  /**
   * The account's evidence: a résumé chunk plus one manual row, prepared **once per worker**.
   *
   * Every PHASE 13 page reads it — the graph draws it, the validator retrieves over it, the jobs
   * match scores against it — and the specs assert against what it returned, so they cannot pass on
   * an empty account.
   */
  evidenceBase: EvidenceBase;
  /** A stored posting **with a stored match**: the jobs page, the interview target, one application. */
  jobId: string;
}

export const test = base.extend<TestFixtures, WorkerFixtures>({
  // The built-in `request` fixture is test-scoped, so a worker-scoped fixture has to build its own
  // context. `playwrightRequest.newContext` is the standalone form of exactly that fixture.
  //
  // Playwright's fixture callback takes `use` as its second argument; it is named `provide` here
  // because `react-hooks/rules-of-hooks` (which `eslint-config-next` enables for this package) sees
  // a call to `use(...)` and reads it as a hook called outside a component.
  apiContext: [
    async ({}, provide) => {
      const context = await playwrightRequest.newContext({ baseURL: API_BASE_URL });
      try {
        const session = await signIn(context);
        await provide({ session, api: new Api(context, session) });
      } finally {
        await context.dispose();
      }
    },
    { scope: 'worker' },
  ],
  session: [
    async ({ apiContext }, provide) => {
      await provide(apiContext.session);
    },
    { scope: 'worker' },
  ],
  api: [
    async ({ apiContext }, provide) => {
      await provide(apiContext.api);
    },
    { scope: 'worker' },
  ],
  // Once per worker: see the note on `upload` above. With `workers: 1` this is one import and one
  // analysis for an entire run, which is what keeps the suite inside the hourly budget.
  evidenceBase: [
    async ({ api }, provide) => {
      await provide(await ensureEvidenceBase(api));
    },
    { scope: 'worker' },
  ],
  jobId: [
    // The evidence base is a dependency, not a convenience: the match is scored *against* the
    // account's evidence, so computing it before the fixture has built any would store a match with
    // every requirement treated as a gap — a figure that is real but measured on an empty account.
    async ({ api, evidenceBase }, provide) => {
      if (evidenceBase.total === 0) {
        throw new Error(
          'the match fixture needs the account evidence: a match scored against an empty account ' +
            'reports every requirement as a gap, and the gates would then be guard-testing a page ' +
            'that is populated with the wrong kind of data',
        );
      }
      const jobId = await ensureJob(api);
      // A stored posting is not a *populated* one: `/app/jobs?job=` renders the analysis, and its
      // `Match figures` panel reads `GET /jobs/{id}/match`, which is a separate stored row produced
      // by `POST /jobs/{id}/match`. Until PHASE 14 the fixture only analysed, so the panel existed
      // only if some earlier spec had happened to compute a match first. On a fresh database the
      // desktop project runs `a11y.spec.ts` before `jd-analysis.spec.ts`, the stored read returned
      // `404 This job has not been matched yet`, and the accessibility gate timed out waiting for a
      // panel that could not exist. Two full runs and an isolated `overflow.spec.ts` run reproduced
      // it; the suite must not depend on spec order.
      await api.matchJob(jobId);
      await provide(jobId);
    },
    { scope: 'worker' },
  ],
  signedInPage: async ({ page, session }, provide) => {
    await installSession(page, toBrowserSession(session));
    await provide(page);
  },
});

export { expect };
export type { Locator };

/**
 * The sidebar, whichever of its three layouts is currently visible.
 *
 * `docs/UI.md` §3.2 renders the navigation three times: a 240px rail at ≥1024px, a 64px icon rail
 * from 768px, and an off-canvas drawer below that. All three are real elements in the document, so
 * a role locator alone would match more than one; `filter({ visible: true })` picks the one the
 * user is actually looking at, and below 768px the drawer has to be opened first.
 */
export async function sidebarNav(page: Page) {
  const visible = page.getByRole('navigation', { name: '主导航' }).filter({ visible: true });
  if ((await visible.count()) === 0) {
    await page.getByRole('button', { name: '打开导航菜单' }).click();
  }
  return page.getByRole('navigation', { name: '主导航' }).filter({ visible: true });
}

/** The six stat-card labels fixed by `docs/UI.md` §5.3, in render order. */
export const STAT_CARD_LABELS = [
  'Evidence Coverage',
  'Skill Coverage',
  'Resume Match',
  'Applications',
  'Interviews',
  'Offers',
] as const;
