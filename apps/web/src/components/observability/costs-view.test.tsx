import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  AiCosts,
  CacheStats,
  CostByAgent,
  CostByFeature,
  PromptVersion,
} from '@careerforge/shared';

import { CostsView } from '@/components/observability/costs-view';
import { api } from '@/lib/api';

/**
 * The cost dashboard's contract with its reader.
 *
 * The assertions are about the four ways a cost page can lie:
 *
 * 1. showing a progress bar for a budget that does not exist (`dailyBudgetUsd: 0` means "no
 *    ceiling configured", not "nothing allowed");
 * 2. drawing a hit-rate gauge for a cache that has served nothing (`hitRate: null`);
 * 3. reporting zero tokens without naming the provider that reported them;
 * 4. labelling a day "today" when the backend buckets by UTC date.
 */

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      aiCosts: vi.fn(),
      costsByAgent: vi.fn(),
      costsByFeature: vi.fn(),
      cacheStats: vi.fn(),
      prompts: vi.fn(),
    },
  };
});

const mocked = vi.mocked(api);

const COSTS: AiCosts = {
  range: '7d',
  days: [
    { day: '2026-09-23', runs: 2, tokens: 0, costUsd: 0, costCny: 0 },
    { day: '2026-09-24', runs: 3, tokens: 0, costUsd: 0, costCny: 0 },
  ],
  totals: { runs: 5, modelCalls: 5, tokens: 0, costUsd: 0, costCny: 0, latencyMs: 268 },
  dailyBudgetUsd: 1,
  notes: [
    'token 与成本来自 provider 自报的用量；零 Key 的 heuristic 路径不产生 token，因此这些运行的 token/成本为 0 而延迟仍被测量。',
  ],
};

const BY_AGENT: CostByAgent[] = [
  {
    agent: 'job',
    runs: 5,
    tokens: 0,
    costUsd: 0,
    costCny: 0,
    avgLatencyMs: 53.6,
    cacheHits: 1,
  },
];

const BY_FEATURE: CostByFeature[] = [
  { feature: 'JD 分析', workflows: ['jd_analysis'], runs: 5, tokens: 0, costUsd: 0, costCny: 0 },
];

const CACHE: CacheStats = {
  byKind: [
    { kind: 'llm', entries: 0, hits: 0, bytes: 0 },
    { kind: 'embedding', entries: 1, hits: 2, bytes: 2048 },
    { kind: 'tool', entries: 0, hits: 0, bytes: 0 },
  ],
  persistedHits: 2,
  process: {
    processHits: 3,
    processMisses: 2,
    processEntries: 3,
    eventsFlushed: 5,
    hitRate: 0.6,
  },
};

const PROMPTS: PromptVersion[] = [
  {
    name: 'jd_analysis',
    version: 1,
    sha256: 'abcdef0123456789abcdef0123456789',
    isActive: true,
    updatedAt: '2026-09-24T09:00:00',
  },
];

beforeEach(() => {
  mocked.aiCosts.mockResolvedValue(COSTS);
  mocked.costsByAgent.mockResolvedValue(BY_AGENT);
  mocked.costsByFeature.mockResolvedValue(BY_FEATURE);
  mocked.cacheStats.mockResolvedValue(CACHE);
  mocked.prompts.mockResolvedValue(PROMPTS);
});

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <CostsView />
    </QueryClientProvider>,
  );
  return user;
}

describe('the cost dashboard', () => {
  it('shows the window totals and repeats the provider caveat next to them', async () => {
    renderView();
    await screen.findByText('花费（USD）');

    // Scoped to the card: `$0.0000` is legitimately on screen several times (totals, budget guard,
    // per-agent rows), so an unscoped query would pass for the wrong reason.
    const spendCard = document.querySelector('[data-total="花费（USD）"]');
    expect(spendCard).not.toBeNull();
    expect(within(spendCard as HTMLElement).getByText('$0.0000')).toBeInTheDocument();
    expect(within(spendCard as HTMLElement).getByText(/约 ¥0\.0000/)).toBeInTheDocument();
    expect(screen.getByText('5 / 5')).toBeInTheDocument();
    expect(screen.getByText('268 ms')).toBeInTheDocument();
    // The note that explains why the tokens are zero travels with the numbers.
    expect(screen.getByText(/零 Key 的 heuristic 路径不产生 token/)).toBeInTheDocument();
  });

  it('keeps the cost answer honest when the window spent nothing', async () => {
    renderView();
    await screen.findByText('每日成本');
    // A flat line at zero would look like a measurement; there is nothing to measure.
    expect(
      screen.getByText(/这个窗口内的运行成本都是 0：零 Key 启发式 provider 不产生费用/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/窗口 7 天中 2 天有运行记录（接口只返回有活动的日期，不做零填充）/),
    ).toBeInTheDocument();
  });

  it('labels the budget comparison with the UTC day it actually read', async () => {
    renderView();
    await screen.findByText('日预算护栏');
    expect(screen.getByText('$0.0000 / $1.00')).toBeInTheDocument();
    expect(screen.getByText('最近记录日 2026-09-24（UTC）')).toBeInTheDocument();
    // A guarded deployment downgrades rather than 500s — the page says where to look.
    expect(screen.getByText(/BudgetExceededError/)).toBeInTheDocument();
  });

  it('says there is no ceiling instead of drawing a full bar when no budget is configured', async () => {
    mocked.aiCosts.mockResolvedValue({ ...COSTS, dailyBudgetUsd: 0 });
    renderView();
    await screen.findByText('日预算护栏');
    expect(screen.getByText(/未配置日预算上限/)).toBeInTheDocument();
    expect(screen.getByText('无上限')).toBeInTheDocument();
    expect(document.querySelector('[data-budget-used]')?.getAttribute('data-budget-used')).toBe(
      'null',
    );
  });

  it('reports the cache hit rate with its denominator, and every kind even at zero', async () => {
    renderView();
    await screen.findByText('缓存命中率');
    expect(screen.getByText('60.0%')).toBeInTheDocument();
    expect(screen.getByText('3 命中 / 5 次查询')).toBeInTheDocument();

    const kinds = Array.from(document.querySelectorAll('[data-cache-kind]')).map((node) =>
      node.getAttribute('data-cache-kind'),
    );
    expect(kinds).toEqual(['llm', 'embedding', 'tool']);
  });

  it('refuses to invent a hit rate for a cache that has served nothing', async () => {
    mocked.cacheStats.mockResolvedValue({
      ...CACHE,
      process: { ...CACHE.process, processHits: 0, processMisses: 0, hitRate: null },
    });
    renderView();
    await screen.findByText('缓存命中率');
    expect(screen.getByText('尚未服务')).toBeInTheDocument();
    expect(screen.getByText(/命中率不可计算/)).toBeInTheDocument();
    expect(document.querySelector('[data-hit-rate]')?.getAttribute('data-hit-rate')).toBe('null');
  });

  it('attributes cost to features and names the workflows behind each', async () => {
    renderView();
    await screen.findByText('每个功能的花费');
    // `jd_analysis` is also the prompt registry's row, so the assertion is scoped to the feature
    // list — which is where the workflow→feature mapping is the point.
    const featureRow = screen.getByText('JD 分析').closest('li');
    expect(featureRow).not.toBeNull();
    expect(within(featureRow as HTMLElement).getByText('jd_analysis')).toBeInTheDocument();
    expect(document.querySelector('[data-feature="JD 分析"]')).not.toBeNull();
  });

  it('switches the window and refetches every panel', async () => {
    const user = renderView();
    await screen.findByText('花费（USD）');
    expect(mocked.aiCosts).toHaveBeenCalledWith('7d');

    await user.click(screen.getByRole('button', { name: '90 天' }));

    await waitFor(() => expect(mocked.aiCosts).toHaveBeenCalledWith('90d'));
    expect(mocked.costsByAgent).toHaveBeenCalledWith('90d');
    expect(mocked.costsByFeature).toHaveBeenCalledWith('90d');
    expect(screen.getByRole('button', { name: '90 天' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows the prompt registry, because attribution needs a visible version', async () => {
    renderView();
    await screen.findByText('提示词注册表');
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.getByText('当前')).toBeInTheDocument();
    // The digest is truncated to a comparable prefix, not printed as a wall of hex.
    expect(screen.getByText('abcdef012345…')).toBeInTheDocument();
  });
});
