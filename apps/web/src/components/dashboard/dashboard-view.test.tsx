import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { DashboardResponse, DashboardRecentJob } from '@careerforge/shared';

import { DashboardView } from '@/components/dashboard/dashboard-view';
import { api } from '@/lib/api';

/**
 * The dashboard's two layout decisions, pinned.
 *
 * Nothing here asserts a *number* — the values come from the API and the page's job is to print
 * them. What it asserts is that the page can still be read:
 *
 * 1. **the recent-jobs row is a card list below `sm`**, not a four-column table. At 375px the table
 *    gave the role ~90px and a Chinese role name has no spaces to break on, so it wrapped one
 *    character per line down the row while the match score stayed on one — a layout fault, not a
 *    long string;
 * 2. **both layouts carry the same five facts** (role, company, match, status, date). jsdom applies
 *    no CSS, so both copies are in the DOM at once; every query below is scoped to one of them on
 *    purpose, exactly as `runs-view.test.tsx` does for the AI Runs table.
 */

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    api: {
      ...actual.api,
      dashboard: vi.fn(),
    },
  };
});

const mocked = vi.mocked(api);

const JOB: DashboardRecentJob = {
  jobId: '11111111-1111-1111-1111-111111111111',
  company: '某某智能科技',
  role: '嵌入式软件工程师（电机控制方向）',
  matchScore: 84,
  status: 'wishlist',
  createdAt: '2026-09-26T02:12:51',
};

function dashboardOf(overrides: Partial<DashboardResponse> = {}): DashboardResponse {
  return {
    profileStrength: {
      score: 82,
      algorithmVersion: 'strength@1.0.0',
      dimensions: [
        { key: 'completeness', label: '资料完整度', raw: 0.9, weight: 0.3, weighted: 27 },
        { key: 'evidence_coverage', label: '证据覆盖率', raw: 0.72, weight: 0.25, weighted: 18 },
        { key: 'evidence_quality', label: '证据质量', raw: 0.81, weight: 0.2, weighted: 16.2 },
        { key: 'github_signal', label: 'GitHub 信号', raw: 0.74, weight: 0.15, weighted: 11.1 },
        { key: 'achievement_bonus', label: '成果加分', raw: 0.97, weight: 0.1, weighted: 9.7 },
      ],
    },
    stats: {
      evidenceCoverage: 0.62,
      skillCoverage: 0.5,
      resumeMatch: 0.84,
      applications: 3,
      interviews: 1,
      offers: 0,
    },
    skillsRadar: [],
    recentJobs: [JOB],
    nextActions: [],
    meta: { tookMs: 12 },
    ...overrides,
  };
}

beforeEach(() => {
  mocked.dashboard.mockResolvedValue(dashboardOf());
});

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DashboardView />
    </QueryClientProvider>,
  );
}

/** Below `sm`: the card list. */
function cards(): HTMLElement {
  return document.querySelector('[data-recent-job-list]') as HTMLElement;
}

/** From `sm` up: the table. */
function table(): HTMLElement {
  return document.querySelector('[data-recent-jobs-table]') as HTMLElement;
}

describe('the dashboard recent-jobs panel', () => {
  it('renders a card list for the narrow layout and a table for wide ones', async () => {
    renderView();
    await screen.findByText('最近岗位');

    // Both are rendered; CSS decides which one is on screen at a given width.
    expect(cards()).not.toBeNull();
    expect(table()).not.toBeNull();
    // …and the table is the wide-layout copy, so it is the one marked `hidden` below `sm`.
    expect(table()?.parentElement?.className).toContain('hidden');
    expect(cards()?.className).toContain('sm:hidden');
  });

  it('puts the role, company, match, status and date on every card', async () => {
    renderView();
    await screen.findByText('最近岗位');

    const card = within(cards());
    // The role is the card's own line: it is the one field that must be able to wrap.
    expect(card.getByText(JOB.role)).toBeInTheDocument();
    expect(card.getByText(JOB.company)).toBeInTheDocument();
    expect(card.getByText('84')).toBeInTheDocument();
    expect(card.getByText('wishlist')).toBeInTheDocument();
    // The API's naive-UTC instant, rendered on the UTC clock it was written on.
    expect(card.getByText('2026-09-26 02:12')).toBeInTheDocument();
  });

  it('keeps the four columns in the table, with the same five facts', async () => {
    renderView();
    await screen.findByText('最近岗位');

    const scope = within(table());
    for (const header of ['Company', 'Role', 'Match', 'Status', '时间 (UTC)']) {
      expect(scope.getByRole('columnheader', { name: header })).toBeInTheDocument();
    }
    expect(scope.getByText(JOB.role)).toBeInTheDocument();
    expect(scope.getByText('84')).toBeInTheDocument();
  });

  it('shows an em dash rather than a made-up date when the API sends none', async () => {
    mocked.dashboard.mockResolvedValue(dashboardOf({ recentJobs: [{ ...JOB, createdAt: null }] }));
    renderView();
    await screen.findByText('最近岗位');
    expect(within(cards()).getByText('—')).toBeInTheDocument();
  });

  it('names every metric in full, because a clipped label measures nothing', async () => {
    renderView();
    await screen.findByRole('heading', { level: 3, name: 'Profile Strength' });

    for (const label of [
      'Evidence Coverage',
      'Skill Coverage',
      'Resume Match',
      'Applications',
      'Interviews',
      'Offers',
    ]) {
      // `exact` because a truncated label would render as a different string entirely.
      expect(screen.getByText(label, { exact: true })).toBeInTheDocument();
    }
  });

  it('explains an empty jobs list instead of rendering an empty table', async () => {
    mocked.dashboard.mockResolvedValue(dashboardOf({ recentJobs: [] }));
    renderView();
    expect(await screen.findByText('还没有岗位数据')).toBeInTheDocument();
    expect(document.querySelector('[data-recent-job-list]')).toBeNull();
    expect(document.querySelector('[data-recent-jobs-table]')).toBeNull();
  });
});

describe('the profile-strength breakdown', () => {
  it("prints the API's own five dimensions, with the API's own numbers", async () => {
    renderView();
    const list = await screen.findByTestId('strength-dimensions');

    // The engine's labels, not a second copy maintained in the browser.
    for (const label of ['资料完整度', '证据覆盖率', '证据质量', 'GitHub 信号', '成果加分']) {
      expect(within(list).getByText(label, { exact: false })).toBeInTheDocument();
    }
    // The contribution printed is the one the API sent, down to the decimal: `27.0`, not `27`.
    for (const weighted of ['27.0', '18.0', '16.2', '11.1', '9.7']) {
      expect(within(list).getByText(weighted)).toBeInTheDocument();
    }
    expect(screen.getByText(/strength@1\.0\.0/)).toBeInTheDocument();
  });

  it('prints the total alone when the payload carries no breakdown', async () => {
    mocked.dashboard.mockResolvedValue(dashboardOf({ profileStrength: { score: 82 } }));
    renderView();
    await screen.findByRole('heading', { level: 3, name: 'Profile Strength' });

    // Absent dimensions must not become five zeroes: `—` and nothing else is the honest rendering.
    expect(screen.queryByTestId('strength-dimensions')).toBeNull();
    expect(screen.getByLabelText('Profile Strength 82 / 100')).toBeInTheDocument();
  });

  it('keeps internal phase vocabulary out of everything a reader can see', async () => {
    renderView();
    await screen.findByRole('heading', { level: 3, name: 'Profile Strength' });

    // This page used to say "载入示例数据 · PHASE 3", "尚未接入的面板" and "7d trend · PHASE 10", and
    // two of the three cards claimed endpoints were needed while those endpoints existed and shipped
    // on /app/analytics. Guarding the whole rendered page is the cheap version of that lesson, and it
    // catches the next one too.
    const rendered = document.body.textContent ?? '';
    expect(rendered).not.toMatch(/PHASE\s*\d/i);
    expect(rendered).not.toMatch(/尚未接入/);
  });
});
