import { expect, type Page } from '@playwright/test';

import type { Api, DocumentAnalysis } from './api';
import { INTERVIEW_ANSWER, JOB_DESCRIPTION, RESUME, SUPPORTED_CLAIM } from './dataset';

/**
 * The four PHASE 13 pages, described once.
 *
 * Every spec that drives them (`jd-analysis`, `evidence-graph`, `claim-validation`, `interview`,
 * `a11y`, `overflow`, `demo-capture`) needs the same three things: the route, a *ready selector*
 * that only exists once the API has answered, and a way to put real data behind the page. Keeping
 * them here means a page rename cannot leave one spec pointing at a route that 404s while another
 * still passes.
 *
 * The ready selectors are the same idea as `scripts/capture-pages.mts`: a screenshot or an axe run
 * against a skeleton is not evidence about the page.
 */
export interface PageUnderTest {
  name: string;
  path: string;
  /** Only present once real API data has rendered — never a wrapper or a skeleton. */
  readySelector: string;
}

export const PHASE_13_PAGES: PageUnderTest[] = [
  // `[data-skill]` is the first skill-tree row: it exists only after `POST /jobs/analyze` returned
  // and `GET /jobs/{id}/skill-tree` was read. The match lands a moment later, so the specs that
  // need a score assert the `Match figures` heading separately (it auto-waits); a CSS-only marker
  // is what lets the same string drive `document.querySelector` in the screenshot script.
  { name: 'jobs', path: '/app/jobs', readySelector: '[data-skill]' },
  {
    name: 'evidence-graph',
    path: '/app/evidence-graph',
    readySelector: '[data-testid="node-index-row"]',
  },
  {
    name: 'validator',
    path: '/app/validator',
    readySelector: '[data-testid="validator-result"]',
  },
  { name: 'interview', path: '/app/interview', readySelector: '[data-interview-workspace]' },
];

/**
 * One of the account's manual evidence rows.
 *
 * `POST /evidence` stores a `manual` row, and it matters more than it looks: the claim gate
 * requires **two independent evidence kinds** before it will call a sentence `supported`
 * (`careerforge_ai/scoring/confidence.py` → `_MIN_INDEPENDENT_SOURCES = 2`), and a locally uploaded
 * résumé only ever produces `document_chunk`. Without a manual row the strongest verdict the
 * validator page can show is `partially_supported`.
 */
export interface ManualEvidence {
  id: string;
  kind: string;
  confidence: number;
  title: string;
}

/** What the PHASE 13 pages read: how much evidence the account holds, and of which kinds. */
export interface EvidenceBase {
  /** The résumé document the chunks came from, if one exists. */
  documentId: string | null;
  /** The account's manual row, created only if it had none. */
  manual: ManualEvidence;
  /** Rows in `GET /evidence`, by kind — the precondition every page needs. */
  kinds: Record<string, number>;
  total: number;
  /**
   * The analysis this *run* performed, or `null` when the account already had evidence.
   *
   * See the rate-limit note on {@link ensureEvidenceBase} for why a rerun does no work.
   */
  analysis: DocumentAnalysis | null;
}

function countByKind(items: Array<{ kind: string }>): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) counts[item.kind] = (counts[item.kind] ?? 0) + 1;
  return counts;
}

/**
 * The manual row, created once and reused after that.
 *
 * **It must not be created twice.** `evidence` carries a unique constraint on
 * `(user_id, kind, content_hash)`, and `EvidenceService.add_manual` inserts without honouring it —
 * so a second `POST /evidence` with the same content is a `500 INTERNAL_ERROR`
 * (`sqlite3.IntegrityError: UNIQUE constraint failed: evidence.user_id, evidence.kind,
 * evidence.content_hash`), not an updated row. That is a backend bug and it is reported as one
 * rather than worked around silently; the workaround here is to read first and only write when the
 * account has no manual row at all, which is also what a rerunnable suite should do anyway.
 */
export async function ensureManualEvidence(
  api: Api,
  title = '嵌入式固件代码片段',
): Promise<ManualEvidence> {
  const existing = (await api.evidenceList(200)).items.find((row) => row.kind === 'manual');
  if (existing) {
    return {
      id: existing.id,
      kind: existing.kind,
      confidence: existing.confidence,
      title: existing.title,
    };
  }
  return api.addManualEvidence({
    title,
    snippet:
      'motor_control.c：STM32 上以 FreeRTOS 任务运行电机控制固件，负责 CAN 总线节点通信调试与 PID 控制环。',
    evidenceLocator: { path: 'motor_control.c', line: 42 },
  });
}

/**
 * The evidence base every PHASE 13 page reads: a résumé chunk **and** a manual row.
 *
 * **Cheap on a rerun, and that is a correctness requirement rather than an optimisation.**
 * `POST /profile/import` and `POST /documents/{id}/analyze` both draw on the `upload` rate-limit
 * bucket, which is **20 requests per hour per user** (`middleware/ratelimit.py`,
 * `docs/API.md` §1.7). A setup that re-imported on every run spent that budget in two consecutive
 * runs and then turned every spec into `429 RATE_LIMITED`. So this reads the account first and only
 * does the import/upload/analyze work when the evidence is genuinely missing; on a rerun it costs
 * two `GET /evidence` calls. `analysis` is therefore `null` on a rerun, and the assertions use
 * `kinds`/`total`, which are true either way.
 */
export async function ensureEvidenceBase(api: Api): Promise<EvidenceBase> {
  const before = await api.evidenceList(200);
  const kinds = countByKind(before.items);

  let documentId: string | null = null;
  let analysis: DocumentAnalysis | null = null;
  if ((kinds['document_chunk'] ?? 0) === 0) {
    const setup = await api.ensureEvidence(RESUME);
    documentId = setup.documentId;
    analysis = setup.analysis;
  } else {
    const documents = await api.json<{ items: Array<{ id: string; kind: string }> }>(
      'GET',
      '/documents?kind=resume&limit=1',
    );
    documentId = documents.items[0]?.id ?? null;
  }

  const manual = await ensureManualEvidence(api);
  const after = await api.evidenceList(200);

  return {
    documentId,
    manual,
    kinds: countByKind(after.items),
    total: after.items.length,
    analysis,
  };
}

/**
 * A stored job posting, so `/app/jobs` has something to load and the interview has a target.
 *
 * `POST /jobs/analyze` de-duplicates on the posting text, so calling this from several specs
 * updates one row rather than creating three. The worker-scoped `jobId` fixture calls it once per
 * worker anyway — parsing a posting is a real backend operation and a suite should not ask for it
 * fifteen times.
 */
export async function ensureJob(api: Api, text = JOB_DESCRIPTION): Promise<string> {
  const job = await api.analyzeJob(text);
  if (!job.id) throw new Error('POST /jobs/analyze returned no job id');
  return job.id;
}

/**
 * Start an interview session through the setup screen and answer one question.
 *
 * Used by the specs that need the *workspace* on screen (a11y and the overflow guard) rather than
 * by the interview flow spec, which drives each step itself and asserts what each one did.
 *
 * The target job is chosen in the real `<select>` the user would use — by id, because
 * `getByLabel('目标岗位')` also matches the JD textarea whose label reads
 * 「粘贴岗位描述（解析后加入目标岗位）」 — and the answer goes into the real textarea: this is a UI
 * helper, not an API shortcut with a page opened next to it.
 */
export async function startInterviewViaUi(
  page: Page,
  jobId: string,
  answer: string,
): Promise<void> {
  await page.goto('/app/interview');
  await page.locator('#target-job').selectOption(jobId);
  await page.getByRole('button', { name: '开始面试' }).click();
  await page.waitForURL(/[?&]session=/);
  const box = page.getByLabel('你的回答');
  await box.waitFor();
  await box.fill(answer);
  await page.getByRole('button', { name: '提交回答' }).click();
  await page.locator('[data-evaluation]').waitFor();
}

/** The pages this helper can put real data in front of, and the ones the guards cover. */
export type PopulatedPage =
  | 'dashboard'
  | 'jobs'
  | 'evidence-graph'
  | 'validator'
  | 'interview'
  | 'ai-runs'
  | 'costs'
  | 'analytics';

/**
 * Put real data in front of a page and wait until it is on screen.
 *
 * Every spec in this phase starts from an account the API populated, and — more importantly —
 * every one of them waits for a *ready selector* before measuring anything. The reason is not
 * tidiness: axe passes happily on an error panel, and a horizontal-overflow measurement taken on a
 * skeleton measures the skeleton.
 *
 * Each branch re-drives the page rather than reloading it, because two of these pages hold their
 * state in the component rather than in the URL (`/app/validator` keeps its verdict, `/app/jobs`
 * keeps a match it computed) — a reload would measure the empty state and the populated layout,
 * which is the one that overflowed in PHASE 11, would never be measured at all.
 */
export async function openPopulatedPage(
  page: Page,
  jobId: string,
  name: PopulatedPage,
): Promise<void> {
  switch (name) {
    case 'dashboard':
      await page.goto('/app/dashboard');
      await page.locator('section[aria-labelledby="dash-strength-heading"]').waitFor();
      return;
    case 'ai-runs':
      // `attached`, not `visible`: below `md` the runs table is replaced by a card list and one of
      // the two copies is `hidden`. The row existing at all is the readiness signal.
      await page.goto('/app/ai-runs');
      await page.locator('[data-run]').first().waitFor({ state: 'attached' });
      return;
    case 'costs':
      // `[data-total]` is on four stat cards, not one.
      await page.goto('/app/costs');
      await page.locator('[data-total]').first().waitFor();
      return;
    case 'analytics':
      await page.goto('/app/analytics');
      await page.locator('[data-stage]').first().waitFor();
      return;
    case 'jobs':
      // `?job=` loads the stored analysis, which is the populated state; the form alone is empty.
      await page.goto(`/app/jobs?job=${encodeURIComponent(jobId)}`);
      await page.locator('[data-skill]').first().waitFor();
      // `Match figures` is the last panel to arrive (the page reads `GET /jobs/{id}/match` for the
      // stored score). 30s rather than the default 10s: one run of this spec timed out here while
      // every other test in the same run passed, and a readiness wait that is occasionally too
      // short turns a layout guard into a flake. Nothing is asserted more weakly — the panel still
      // has to appear.
      await page.getByRole('heading', { name: 'Match figures' }).waitFor({ timeout: 30_000 });
      return;
    case 'evidence-graph':
      await page.goto('/app/evidence-graph');
      await page.getByTestId('node-index-row').first().waitFor();
      return;
    case 'validator':
      await page.goto('/app/validator');
      await page.getByLabel('Résumé sentence').fill(SUPPORTED_CLAIM);
      await page.getByTestId('validate-claim').click();
      await page.getByTestId('validator-result').waitFor();
      return;
    case 'interview':
      await startInterviewViaUi(page, jobId, INTERVIEW_ANSWER);
      return;
  }
}

/**
 * Click a node **on the graph canvas**, the way a finger or a mouse actually does it.
 *
 * `locator.click()` does not select a canvas node on this page. Measured, twice per run, on the
 * live stack: `locator.click()` on `[data-testid="graph-node"][data-node-id="…"]` leaves the URL at
 * `/app/evidence-graph` and no drawer opens, while the identical pointer sequence
 * (`mouse.move` → `down` → `up` at the same centre point) sets `?skill=…` and opens the drawer
 * every time. The node is not covered — `document.elementFromPoint` at that centre resolves to the
 * node's own subtree, and Playwright's actionability check passes — so this is not an intercepted
 * click. The two remaining candidates are Playwright's `scrollIntoViewIfNeeded` (which xyflow
 * answers by re-running its layout, moving the node between the measurement and the click) and the
 * extra `mousemove` Playwright synthesizes during a locator click. The raw sequence is what a
 * device sends, so the spec uses that and the discrepancy is reported rather than hidden.
 */
export async function clickCanvasNode(page: Page, nodeId: string): Promise<void> {
  const card = page.locator(`[data-testid="graph-node"][data-node-id="${nodeId}"]`);
  await expect(card).toBeVisible();
  const box = await card.boundingBox();
  if (!box) throw new Error(`canvas node ${nodeId} has no box to click`);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.up();
}

export { RESUME };
