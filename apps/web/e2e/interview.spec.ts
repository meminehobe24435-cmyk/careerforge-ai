import { INTERVIEW_ANSWER } from './helpers/dataset';
import { ensureJob } from './helpers/pages';
import { expect, test } from './helpers/fixtures';
import type { InterviewSession } from './helpers/api';

/**
 * E2E 5 · Interview simulator (`/app/interview`) — a session started and answered in the UI.
 *
 * The PHASE 12 version of this file drove `POST /ai/interview/start` and
 * `POST /ai/interview/{id}/answer` from inside the page, because there was no route to type an
 * answer into. The page exists now, so the flow is the real one: choose a target role in the setup
 * screen, press **开始面试**, answer the question the backend asked, and watch the session advance.
 *
 * The provider is the zero-key heuristic one, so this costs nothing and is deterministic — but
 * "deterministic" is not the same as "informative": the heuristic question generator has no model
 * to vary its prompt with, so the spec does not require the question *text* to change. It requires
 * the **session state** to advance, which is what the API actually promises: the turn index grows,
 * the evaluation lands with a score, and the persisted session gains the candidate's turn.
 *
 * The page keeps the URL as its state (`?session=<id>`), so the last section asserts a refresh
 * resumes the session instead of resetting it — that is the behaviour the header in
 * `components/interview/interview-view.tsx` claims, and the only way to check it is to reload.
 */
test.describe('Interview', () => {
  test('a session is started and one question answered through the workspace', async ({
    api,
    signedInPage: page,
  }) => {
    // The setup screen starts a session *against a stored posting*, so the spec creates one the
    // same way a user would: `POST /jobs/analyze` de-duplicates on the posting text, so this is
    // idempotent across runs.
    const jobId = await ensureJob(api);

    await page.goto('/app/interview');

    // ── setup ──────────────────────────────────────────────────────────────────────────────────
    await expect(page.getByRole('heading', { level: 1, name: '模拟面试' })).toBeVisible();
    const start = page.getByRole('button', { name: '开始面试' });
    // No target role selected yet: starting is refused rather than starting against nothing.
    await expect(start).toBeDisabled();
    await expect(page.getByText('先选择或解析一个目标岗位。')).toBeVisible();

    // `getByLabel('目标岗位')` would be ambiguous: the JD textarea's label is
    // 「粘贴岗位描述（解析后加入目标岗位）」, which also contains that text. The id is unambiguous.
    await page.locator('#target-job').selectOption(jobId);
    await expect(start).toBeEnabled();
    await start.click();

    // ── the workspace, with a question the backend actually asked ──────────────────────────────
    await page.waitForURL(/[?&]session=/);
    const sessionId = new URL(page.url()).searchParams.get('session');
    expect(sessionId, 'the session id must be in the URL, so a refresh resumes').toBeTruthy();
    if (!sessionId) throw new Error('unreachable');

    const workspace = page.locator('[data-interview-workspace]');
    await expect(workspace).toBeVisible();
    await expect(page.getByRole('heading', { level: 1, name: /模拟面试/ })).toBeVisible();

    // The first question is on screen before anything is answered.
    await expect(page.getByRole('heading', { name: '第 1 题' })).toBeVisible();
    const question = page.locator('[data-question]');
    await expect(question).toBeVisible();
    const firstQuestion = (await question.textContent())?.trim() ?? '';
    expect(firstQuestion.length).toBeGreaterThan(0);
    // Nothing has been answered, and the page says so instead of showing a placeholder score.
    await expect(page.getByText(/还没有已回答的轮次/)).toBeVisible();
    await expect(page.locator('[data-evaluation]')).toHaveCount(0);

    // ── answer it ─────────────────────────────────────────────────────────────────────────────
    await page.getByLabel('你的回答').fill(INTERVIEW_ANSWER);
    await page.getByRole('button', { name: '提交回答' }).click();

    // The workspace advances to the second question and renders the evaluation of the first answer.
    await expect(page.getByRole('heading', { name: '第 2 题' })).toBeVisible();
    const evaluation = page.locator('[data-evaluation]');
    await expect(evaluation).toBeVisible();
    // The sub-scores are the evaluator's own dimensions — a bare total would be unauditable.
    for (const dimension of ['技术', '深度', '表达', '解题', '工程', '自信']) {
      await expect(evaluation).toContainText(dimension);
    }

    // ── the server agrees that the session advanced ────────────────────────────────────────────
    // Read back through the API: the page could show an optimistic state that the session store
    // never recorded, and the whole point of the flow is that the turn really landed.
    const persisted = await api.json<InterviewSession>('GET', `/ai/interview/${sessionId}`);
    expect(persisted.session_id).toBe(sessionId);
    expect(persisted.status).toBe('in_progress');
    // Start (1 interviewer turn) + answer (candidate) + next question (interviewer) = 3.
    expect(persisted.turns).toHaveLength(3);
    expect(persisted.turns.filter((turn) => turn.role === 'candidate')).toHaveLength(1);
    expect(persisted.turns.filter((turn) => turn.role === 'interviewer')).toHaveLength(2);
    expect(persisted.turns.map((turn) => turn.turn_index)).toEqual([0, 1, 2]);
    const scored = persisted.turns.find((turn) => turn.role === 'candidate');
    expect(scored?.score ?? 0).toBeGreaterThan(0);
    // The plan is the session's contract with the candidate and is built once, up front.
    expect(persisted.plan.length).toBeGreaterThan(0);

    // The turn index the evaluation belongs to is on screen, so the reader can tell which answer
    // the feedback is about.
    await expect(page.getByText('第 1 题的回答')).toBeVisible();

    // ── a refresh resumes rather than resets ──────────────────────────────────────────────────
    // A reload re-fetches the whole bundle and then `GET /ai/interview/{id}`; the default 10s
    // expectation budget was tight enough that a slow first paint on the mobile project failed
    // here once (measured: the desktop project passed the same assertion in the same run), so this
    // one waits longer rather than asserting something weaker.
    await page.reload();
    await expect(page.locator('[data-interview-workspace]')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('heading', { name: '第 2 题' })).toBeVisible();
    // `GET /ai/interview/{id}` returns each turn's score and not the full evaluation, so after a
    // refresh the panel reports the score and says where the rest lives — it does not fake it.
    await expect(page.getByText(/会话载荷.*只带 score/)).toBeVisible();
  });
});
