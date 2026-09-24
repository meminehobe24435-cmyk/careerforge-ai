import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { AiRun, AiRunDetail, AiRunList } from '@careerforge/shared';

import { AiRunsView } from '@/components/observability/runs-view';
import { ApiError, api } from '@/lib/api';

/**
 * The AI Runs page's contract with its reader.
 *
 * Five assertions matter more than the layout:
 *
 * 1. a run that reports zero tokens says **why** — a table of zeros with no explanation reads as
 *    broken instrumentation rather than as a zero-key deployment;
 * 2. the drill-down is keyboard reachable and fetches *that row's* trace, not the list's;
 * 3. filters are sent to the API as query parameters, because a filter applied client-side would
 *    silently disagree with `total`;
 * 4. an unmeasurable latency is a dash, never `0 ms`;
 * 5. the narrow layout carries the same facts. jsdom applies no CSS, so the table and the card list
 *    are both in the DOM at once; every query below is scoped to one of them on purpose, and the
 *    two layouts are asserted separately rather than blurred together.
 */

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      aiRuns: vi.fn(),
      aiRun: vi.fn(),
    },
  };
});

const mocked = vi.mocked(api);

function runOf(overrides: Partial<AiRun> = {}): AiRun {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    userId: '22222222-2222-2222-2222-222222222222',
    workflow: 'jd_analysis',
    agent: 'job',
    status: 'degraded',
    trigger: 'api',
    provider: 'heuristic',
    model: null,
    promptVersion: 'jd_analysis@v1',
    promptTokens: 0,
    completionTokens: 0,
    totalTokens: 0,
    costUsd: 0,
    costCny: 0,
    latencyMs: 93,
    cacheHit: false,
    requestId: 'req_abc',
    error: null,
    stepCount: 4,
    startedAt: '2026-09-24T10:00:00',
    finishedAt: '2026-09-24T10:00:00.093',
    ...overrides,
  };
}

function listOf(items: AiRun[]): AiRunList {
  return { items, total: items.length, limit: 50, offset: 0 };
}

function detailOf(run: AiRun): AiRunDetail {
  return {
    ...run,
    steps: [
      {
        name: 'clean',
        status: 'ok',
        latencyMs: 1,
        provider: null,
        model: null,
        promptVersion: null,
        attempts: 1,
        cacheHit: false,
        tokens: 0,
        costUsd: 0,
        inputDigest: 'aaaa1111bbbb2222',
        outputDigest: 'cccc3333dddd4444',
        errorCode: null,
        errorMessage: null,
        startedAt: '2026-09-24T10:00:00',
      },
      {
        name: 'extract',
        status: 'ok',
        latencyMs: 12,
        provider: null,
        model: null,
        promptVersion: null,
        attempts: 2,
        cacheHit: false,
        tokens: 0,
        costUsd: 0,
        inputDigest: 'eeee5555ffff6666',
        outputDigest: '9999aaaa1111bbbb',
        errorCode: null,
        errorMessage: null,
        startedAt: '2026-09-24T10:00:00.010',
      },
    ],
    calls: [],
    inputRef: { documentId: 'doc-1' },
    outputRef: {},
  };
}

/** The desktop table, which is the layout the column assertions belong to. */
function desktop(): HTMLElement {
  return screen.getByRole('table');
}

/** The narrow-screen card list, rendered alongside the table (jsdom applies no CSS). */
function mobile(): HTMLElement {
  return document.querySelector('[data-run-list]') as HTMLElement;
}

beforeEach(() => {
  mocked.aiRuns.mockResolvedValue(listOf([runOf()]));
  mocked.aiRun.mockResolvedValue(detailOf(runOf()));
});

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <AiRunsView />
    </QueryClientProvider>,
  );
  return user;
}

/**
 * Render and wait until the list has data.
 *
 * The table and the card list only exist once the query resolved, so a scope like
 * `within(screen.getByRole('table'))` has to be taken *after* that — evaluating it eagerly is how
 * the first version of these tests failed on its own timing rather than on the interface.
 */
async function renderReady() {
  const user = renderView();
  await screen.findByText('运行记录');
  return user;
}

describe('the AI runs page', () => {
  it('lists the run with its provider, prompt version and measured latency', async () => {
    renderView();
    await screen.findByText('运行记录');

    const table = within(desktop());
    expect(table.getByText('job')).toBeInTheDocument();
    expect(table.getByText('jd_analysis')).toBeInTheDocument();
    expect(table.getByText('prompt jd_analysis@v1')).toBeInTheDocument();
    expect(table.getByText('93 ms')).toBeInTheDocument();
    expect(table.getByText('4 步')).toBeInTheDocument();
    // Status is a word inside the row, not just a colour — and the same word also labels the
    // filter button above, so the assertion is scoped to the row itself.
    const row = document.querySelector(`table [data-run="${runOf().id}"]`);
    expect(row).not.toBeNull();
    expect(within(row as HTMLElement).getByText('降级')).toBeInTheDocument();
    expect(within(row as HTMLElement).getByText('未命中')).toBeInTheDocument();
  });

  it('carries the same facts in the narrow layout instead of clipping the table', async () => {
    await renderReady();

    const list = mobile();
    // The agent and workflow share one line in the card layout, so the assertion is on that line.
    expect(list.textContent).toContain('job · jd_analysis');
    expect(within(list).getByText('降级')).toBeInTheDocument();
    expect(within(list).getByText('93 ms')).toBeInTheDocument();
    // These are the columns a 375 px viewport pushed off-screen in the first version.
    expect(within(list).getByText('$0.0000')).toBeInTheDocument();
    expect(within(list).getByText('2026-09-24 10:00')).toBeInTheDocument();
    expect(within(list).getByText(/未命中 · 4 步/)).toBeInTheDocument();
  });

  it('explains a page of zero tokens instead of presenting it as broken metering', async () => {
    await renderReady();
    expect(screen.getByText(/零 Key 启发式 provider/)).toBeInTheDocument();
    expect(screen.getByText(/延迟仍然被真实测量/)).toBeInTheDocument();
  });

  it('opens the row and fetches that run’s step chain, not the list', async () => {
    const user = await renderReady();
    const toggle = within(desktop()).getByRole('button', { name: /jd_analysis/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle);

    await waitFor(() => expect(mocked.aiRun).toHaveBeenCalledWith(runOf().id));
    // Scoped to the table: the card list shares the expansion state and is also in the DOM (jsdom
    // applies no CSS), so an unscoped query would match the invisible copy.
    expect(await within(desktop()).findByText('extract')).toBeInTheDocument();
    // The second attempt is visible: a retried step is not the same as a fast one.
    expect(within(desktop()).getByText('重试 1 次')).toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
  });

  it('opens the same drill-down from the narrow layout', async () => {
    const user = await renderReady();
    await user.click(within(mobile()).getByRole('button', { name: /jd_analysis/ }));
    await waitFor(() => expect(mocked.aiRun).toHaveBeenCalledWith(runOf().id));
    expect(within(mobile()).getByText('clean')).toBeInTheDocument();
  });

  it('says a zero-call run is the zero-key path rather than a missing trace', async () => {
    const user = await renderReady();
    await user.click(within(desktop()).getByRole('button', { name: /jd_analysis/ }));
    expect(await within(desktop()).findByText(/没有产生模型调用记录/)).toBeInTheDocument();
    expect(within(desktop()).getByText(/启发式路径走本地规则/)).toBeInTheDocument();
  });

  it('sends the filters to the API rather than filtering the page', async () => {
    const user = await renderReady();

    await user.click(screen.getByRole('button', { name: '失败' }));
    await waitFor(() =>
      expect(mocked.aiRuns).toHaveBeenCalledWith(expect.objectContaining({ status: 'failed' })),
    );

    await user.click(screen.getByRole('button', { name: '24 小时' }));
    await waitFor(() =>
      expect(mocked.aiRuns).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'failed', sinceHours: 24 }),
      ),
    );

    await user.type(screen.getByLabelText('按 workflow 过滤'), 'jd');
    await waitFor(() =>
      expect(mocked.aiRuns).toHaveBeenCalledWith(
        expect.objectContaining({ workflow: 'jd', status: 'failed', sinceHours: 24 }),
      ),
    );
  });

  it('shows an unmeasurable latency as a dash and a cached run as a hit', async () => {
    mocked.aiRuns.mockResolvedValue(
      listOf([
        runOf({ id: 'aaaaaaaa-0000-0000-0000-000000000000', latencyMs: null, cacheHit: true }),
      ]),
    );
    renderView();
    await screen.findByText('运行记录');
    const table = within(desktop());
    expect(table.getByText('—')).toBeInTheDocument();
    expect(table.getByText('命中')).toBeInTheDocument();
  });

  it('explains an empty result instead of showing an empty table', async () => {
    mocked.aiRuns.mockResolvedValue(listOf([]));
    renderView();
    expect(await screen.findByText('还没有被追踪的 AI 运行')).toBeInTheDocument();
    expect(screen.getByText(/GET \/ai-runs → total 0/)).toBeInTheDocument();
  });

  it('surfaces a failed read with its code and request id', async () => {
    // A real `ApiError`, not a duck-typed object: the page reads `requestId` off it, and a test that
    // hands it a lookalike would pass while the real error path showed "UNKNOWN".
    mocked.aiRuns.mockRejectedValue(
      new ApiError({
        code: 'INTERNAL_ERROR',
        message: 'boom',
        requestId: 'req_500',
        status: 500,
        body: null,
      }),
    );
    renderView();
    // The hook retries once, so the error state arrives after the retry delay rather than at once.
    expect(await screen.findByText('运行记录加载失败', {}, { timeout: 5_000 })).toBeInTheDocument();
    expect(screen.getByText('INTERNAL_ERROR')).toBeInTheDocument();
    expect(screen.getByText('req_500')).toBeInTheDocument();
  });
});
