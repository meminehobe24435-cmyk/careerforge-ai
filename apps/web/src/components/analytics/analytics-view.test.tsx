import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  CategoryPerformance,
  FunnelResponse,
  RatesResponse,
  SkillCorrelation,
  TimelineResponse,
} from '@careerforge/shared';

import { AnalyticsView } from '@/components/analytics/analytics-view';
import { api } from '@/lib/api';

/**
 * The analytics page's contract with its reader.
 *
 * Three assertions matter more than the layout:
 *
 * 1. the window is on screen and switching it refetches — a funnel without its range is a number
 *    nobody can check;
 * 2. an insufficient sample says "样本不足" **next to the number**, which is the phase's exit
 *    criterion in the interface rather than in the JSON;
 * 3. an empty cohort is explained, not drawn as five zeros.
 */

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() },
}));

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      funnel: vi.fn(),
      rates: vi.fn(),
      skillCorrelation: vi.fn(),
      categories: vi.fn(),
      timeline: vi.fn(),
    },
  };
});

const mocked = vi.mocked(api);

const META = {
  range: '30d',
  fromAt: '2026-02-01T00:00:00Z',
  toAt: '2026-03-01T00:00:00Z',
  cohortSize: 6,
  minimumSample: 5,
  windowBasis: 'applications' as const,
  notes: ['range 过滤的是投递的创建时间（同期群）。'],
};

function funnelOf(cohortSize = 6): FunnelResponse {
  return {
    meta: { ...META, cohortSize },
    stages: [
      {
        key: 'applications',
        label: '投递',
        count: 6,
        shareOfFirst: 1,
        stepRate: 1,
        basis: '曾离开 wishlist 的卡片',
      },
      {
        key: 'replies',
        label: '有回复',
        count: 3,
        shareOfFirst: 0.5,
        stepRate: 0.5,
        basis: '曾进入 oa/interview/final/offer，或投递后被拒',
      },
      {
        key: 'interviews',
        label: '面试',
        count: 1,
        shareOfFirst: 0.1667,
        stepRate: 0.3333,
        basis: '曾进入 interview/final/offer',
      },
      {
        key: 'finals',
        label: '终面',
        count: 0,
        shareOfFirst: 0,
        stepRate: 0,
        basis: '曾进入 final/offer',
      },
      {
        key: 'offers',
        label: 'Offer',
        count: 0,
        shareOfFirst: 0,
        stepRate: null,
        basis: '曾进入 offer',
      },
    ],
  };
}

function ratesOf(): RatesResponse {
  return {
    meta: { ...META, notes: ['分母小于 5 时 sufficient=false。'] },
    cards: [
      {
        key: 'interviewRate',
        label: 'Interview Rate',
        rate: 0.1667,
        numerator: 1,
        denominator: 6,
        sufficient: true,
        intervalLow: 0.03,
        intervalHigh: 0.56,
        definition: '进入面试的投递 ÷ 全部投递',
      },
      {
        key: 'offerRate',
        label: 'Offer Rate',
        rate: 0,
        numerator: 0,
        denominator: 3,
        sufficient: false,
        intervalLow: 0,
        intervalHigh: 0.56,
        definition: '拿到 Offer 的投递 ÷ 全部投递',
      },
      {
        key: 'averageMatchScore',
        label: 'Avg Match Score',
        rate: null,
        numerator: 0,
        denominator: 0,
        sufficient: false,
        intervalLow: 0,
        intervalHigh: 0,
        definition: '已评分卡片的平均匹配分 ÷ 100',
      },
    ],
  };
}

const CORRELATION: SkillCorrelation[] = [
  {
    skillId: 'stm32',
    displayName: 'STM32',
    withSkillTotal: 6,
    withSkillSuccesses: 1,
    withSkillRate: 0.1667,
    withoutSkillTotal: 4,
    withoutSkillSuccesses: 1,
    withoutSkillRate: 0.25,
    lift: -0.0833,
    sufficient: true,
    notable: false,
    note: '两组的 95% 区间重叠，差异不显著——这是提示而非结论',
  },
  {
    skillId: 'can',
    displayName: 'CAN',
    withSkillTotal: 2,
    withSkillSuccesses: 1,
    withSkillRate: 0.5,
    withoutSkillTotal: 8,
    withoutSkillSuccesses: 1,
    withoutSkillRate: 0.125,
    lift: 0.375,
    sufficient: false,
    notable: false,
    note: '样本不足（2 vs 8，各需 ≥ 5 条），差距不可作为结论',
  },
];

const CATEGORIES: CategoryPerformance[] = [
  {
    category: 'embedded',
    applications: 6,
    interviews: 1,
    offers: 0,
    interviewRate: 0.1667,
    averageMatchScore: 42.5,
    sufficient: true,
  },
];

function timelineOf(): TimelineResponse {
  return {
    meta: {
      ...META,
      windowBasis: 'events',
      cohortSize: 3,
      notes: ['range 过滤的是事件发生时间。', '空月份会保留为 0。'],
    },
    entries: [
      {
        kind: 'application',
        title: '投递：智远科技',
        occurredAt: '2026-02-20T09:00:00Z',
        status: 'applied',
        refId: 'a',
      },
    ],
    buckets: [
      { month: '2026-01', applications: 0, interviews: 0, offers: 0 },
      { month: '2026-02', applications: 3, interviews: 1, offers: 0 },
    ],
  };
}

beforeEach(() => {
  mocked.funnel.mockResolvedValue(funnelOf());
  mocked.rates.mockResolvedValue(ratesOf());
  mocked.skillCorrelation.mockResolvedValue(CORRELATION);
  mocked.categories.mockResolvedValue(CATEGORIES);
  mocked.timeline.mockResolvedValue(timelineOf());
});

function renderView() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <AnalyticsView />
    </QueryClientProvider>,
  );
  return user;
}

describe('the analytics page', () => {
  it('shows the funnel with every stage and its stated basis', async () => {
    renderView();
    await screen.findByText('投递漏斗');

    // One band per stage, addressed by key rather than by position.
    const bands = document.querySelectorAll('[data-stage]');
    expect(Array.from(bands).map((band) => band.getAttribute('data-stage'))).toEqual([
      'applications',
      'replies',
      'interviews',
      'finals',
      'offers',
    ]);
    // Each stage states how it was counted: a number whose definition is implicit is a number
    // nobody can check.
    expect(screen.getByText(/曾离开 wishlist 的卡片/)).toBeInTheDocument();
    expect(screen.getByText(/曾进入 interview\/final\/offer/)).toBeInTheDocument();
    // The chart carries an accessible description of its own numbers.
    expect(screen.getByRole('img', { name: /投递漏斗：投递 6/ })).toBeInTheDocument();
  });

  it('renders an empty stage as an empty band rather than a missing one', async () => {
    renderView();
    await screen.findByText('投递漏斗');
    // The Offer band exists in the SVG even with zero cards, so the shape shows where the
    // pipeline stopped.
    const band = document.querySelector('[data-stage="offers"]');
    expect(band).not.toBeNull();
    expect(band?.getAttribute('data-empty')).toBe('true');
  });

  it('marks an insufficient rate next to the number, in words', async () => {
    renderView();
    await screen.findByText('Interview Rate');
    expect(screen.getByText('样本不足（n=3），仅供参考')).toBeInTheDocument();
    // And an unmeasurable rate is an em dash, never 0%.
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('shows both groups of a correlation, and distinguishes "flat" from "not enough data"', async () => {
    renderView();
    await screen.findByText('技能与面试成功率');

    expect(screen.getByText('STM32')).toBeInTheDocument();
    expect(screen.getByText('无显著差异')).toBeInTheDocument();
    expect(screen.getByText('样本不足')).toBeInTheDocument();
    // Both sides of each comparison are on screen: a rate with no comparison group is not one.
    expect(screen.getByText(/17% \(1\/6\)/)).toBeInTheDocument();
    expect(screen.getByText(/25% \(1\/4\)/)).toBeInTheDocument();
  });

  it('switches the window and refetches every panel', async () => {
    const user = renderView();
    await screen.findByText('投递漏斗');
    expect(mocked.funnel).toHaveBeenCalledWith('30d');

    await user.click(screen.getByRole('button', { name: '90 天' }));

    await waitFor(() => expect(mocked.funnel).toHaveBeenCalledWith('90d'));
    expect(mocked.rates).toHaveBeenCalledWith('90d');
    expect(mocked.timeline).toHaveBeenCalledWith('90d');
    expect(screen.getByRole('button', { name: '90 天' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('explains an empty cohort instead of drawing five zeros', async () => {
    mocked.funnel.mockResolvedValue(funnelOf(0));
    renderView();
    expect(await screen.findByText('这个窗口内没有投递')).toBeInTheDocument();
    expect(screen.getByText(/cohortSize 0/)).toBeInTheDocument();
  });

  it('keeps idle months in the trend', async () => {
    renderView();
    await screen.findByText('时间趋势与里程碑');
    expect(screen.getByTitle('2026-01 投递 0')).toBeInTheDocument();
    expect(screen.getByTitle('2026-02 投递 3')).toBeInTheDocument();
  });
});
