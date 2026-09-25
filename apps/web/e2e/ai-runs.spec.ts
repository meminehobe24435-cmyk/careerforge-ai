import { JOB_DESCRIPTION } from './helpers/dataset';
import { expect, test } from './helpers/fixtures';

/**
 * E2E 6 · AI runs (`/app/ai-runs`, `docs/UI.md` §5.15).
 *
 * The page is an operator surface, so the useful test is not "a table exists" but "the run that
 * just happened is in it, and expanding it shows the same numbers the API reports". The spec
 * therefore triggers a real traced operation (`POST /jobs/analyze` → a `jd_analysis` run), reads
 * that run back from `GET /ai-runs/{id}`, and then asserts the rendered row, the step chain and the
 * model-call table against those numbers rather than against hard-coded expectations.
 *
 * The model-call table is the interesting half: this deployment has no API key, so the heuristic
 * provider serves every call and the costs are zero. The panel says that in words instead of drawing
 * an empty table, and both states are asserted — which one is correct is decided by the payload.
 */
test.describe('AI runs', () => {
  test('a fresh operation appears as a run whose steps and model calls render', async ({
    api,
    signedInPage: page,
  }) => {
    const job = await api.analyzeJob(JOB_DESCRIPTION);
    expect(job.role).toContain('嵌入式');
    const run = await api.newestRun('jd_analysis');
    const detail = await api.aiRun(run.id);

    expect(run.workflow).toBe('jd_analysis');
    expect(run.agent.length).toBeGreaterThan(0);
    expect(detail.stepCount).toBeGreaterThan(0);
    expect(detail.steps.length).toBe(detail.stepCount);

    await page.goto('/app/ai-runs');
    await expect(page.getByRole('heading', { level: 1, name: 'AI 运行记录' })).toBeVisible();

    // The row for this exact run, located by the id the API assigned it. `RunTable` renders the
    // same facts twice — a nine-column table at ≥640px and a card list below it — and both carry
    // `data-run`, so the visible one is selected rather than the first in the DOM.
    const row = page.locator(`[data-run="${run.id}"]`).filter({ visible: true });
    await expect(row, `run ${run.id} should be listed on /app/ai-runs`).toBeVisible();
    await expect(row).toContainText(run.agent);
    await expect(row).toContainText(run.workflow);
    await expect(row).toContainText(`${detail.stepCount} 步`);

    // Expand it: the row header button announces the panel it controls.
    const expand = row.getByRole('button');
    await expect(expand).toHaveAttribute('aria-expanded', 'false');
    await expand.click();
    await expect(expand).toHaveAttribute('aria-expanded', 'true');

    // ── the step chain ───────────────────────────────────────────────────────────────────────
    const steps = page.getByRole('region', { name: '步骤链' });
    await expect(steps).toBeVisible();
    await expect(steps).toContainText(`步骤链（${detail.steps.length} 步`);
    const renderedSteps = steps.locator('[data-step]');
    await expect(renderedSteps).toHaveCount(detail.steps.length);
    // The order is the execution order, not a re-sorting by the renderer.
    expect(
      await renderedSteps.evaluateAll((nodes) =>
        nodes.map((node) => node.getAttribute('data-step')),
      ),
    ).toEqual(detail.steps.map((step) => step.name));

    // ── the model-call table ─────────────────────────────────────────────────────────────────
    const calls = page.getByRole('region', { name: '模型调用' });
    await expect(calls).toBeVisible();
    await expect(calls).toContainText(`模型调用（${detail.calls.length} 次`);
    if (detail.calls.length > 0) {
      const firstCall = detail.calls[0];
      const table = calls.getByRole('table');
      await expect(table).toBeVisible();
      await expect(table.getByRole('columnheader', { name: '操作' })).toBeVisible();
      await expect(table.locator('tbody tr')).toHaveCount(detail.calls.length);
      if (firstCall) await expect(table).toContainText(firstCall.operation);
    } else {
      // Zero-key deployment: the panel explains that the heuristic path calls no model rather than
      // rendering an empty table that reads as missing instrumentation.
      await expect(calls).toContainText('零 Key 的启发式路径走本地规则');
    }

    // The run list itself is unfiltered by default.
    await expect(
      page.getByRole('group', { name: '状态' }).getByRole('button', { name: '全部状态' }),
    ).toHaveAttribute('aria-pressed', 'true');
  });
});
