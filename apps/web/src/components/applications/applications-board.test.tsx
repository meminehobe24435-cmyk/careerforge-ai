import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  APPLICATION_STATUSES,
  type ApplicationBoardResponse,
  type ApplicationCard,
  type ApplicationStatus,
} from '@careerforge/shared';

import { ApplicationsView } from '@/components/applications/applications-view';
import { api } from '@/lib/api';
import { installBoardLayout } from '@/test/layout';

/**
 * The board's behaviour, not its markup.
 *
 * Three things are asserted, and they are exactly the phase's exit criteria:
 *
 * 1. a **keyboard** drag moves a card across columns and sends the documented payload — the
 *    stock dnd-kit coordinate getter cannot cross columns, so this is a test of our own;
 * 2. the move is **optimistic**: the card is in its new column while the request is still in
 *    flight (the promise never settles in that test);
 * 3. a failed write **rolls back and says so** — the card returns to where it was and a toast
 *    explains why, because a silent rollback is indistinguishable from a broken drag.
 *
 * Sonner is mocked rather than rendered: a toast is a message, and asserting the message is
 * the point. The rollback itself is asserted on the board, which is the part that matters.
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
      applicationBoard: vi.fn(),
      reorderApplications: vi.fn(),
      createApplication: vi.fn(),
      updateApplication: vi.fn(),
      deleteApplication: vi.fn(),
    },
  };
});

const mocked = vi.mocked(api);

function card(id: string, overrides: Partial<ApplicationCard> = {}): ApplicationCard {
  return {
    id,
    jobId: null,
    resumeVersionId: null,
    company: `公司 ${id}`,
    role: '嵌入式软件工程师',
    location: '苏州',
    status: 'wishlist',
    matchScore: 20,
    salaryExpectation: '18k×15',
    notes: '内推',
    position: 0,
    appliedAt: null,
    nextActionAt: null,
    archivedAt: null,
    createdAt: null,
    updatedAt: null,
    ...overrides,
  };
}

function boardOf(
  columns: Partial<Record<ApplicationStatus, ApplicationCard[]>>,
): ApplicationBoardResponse {
  const all = APPLICATION_STATUSES.map((status) => ({
    status,
    items: (columns[status] ?? []).map((item, index) => ({
      ...item,
      status,
      position: index,
    })),
  }));
  return {
    columns: all,
    counts: Object.fromEntries(all.map((column) => [column.status, column.items.length])),
    total: all.reduce((sum, column) => sum + column.items.length, 0),
    archived: 0,
  };
}

/**
 * jsdom has no layout, so the test supplies one — see `src/test/layout.ts` for the geometry
 * and for the two mistakes that cost real debugging time.
 */
beforeEach(() => {
  installBoardLayout();
});

function renderView(board: ApplicationBoardResponse) {
  mocked.applicationBoard.mockResolvedValue(board);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const user = userEvent.setup();
  render(
    <QueryClientProvider client={client}>
      <ApplicationsView />
    </QueryClientProvider>,
  );
  return user;
}

/**
 * The board and the mobile list are both in the DOM at all times — they are separated by a
 * CSS breakpoint, and jsdom evaluates no CSS. So every query is scoped to the board, and one
 * test asserts the list exists, which is what tells a reader the duplication is intentional
 * rather than an accident these tests happen to tolerate.
 */
async function boardEl(): Promise<HTMLElement> {
  return screen.findByTestId('kanban-board');
}

/** The draggable element for a card, found by the company text it renders. */
async function draggableFor(company: string): Promise<HTMLElement> {
  const board = await boardEl();
  const text = await within(board).findByText(company);
  const element = text.closest('[data-card-id]');
  expect(element, `card ${company} is not draggable`).not.toBeNull();
  return element as HTMLElement;
}

function columnNamed(board: HTMLElement, label: string): HTMLElement {
  const region = within(board)
    .getAllByRole('region')
    .find((node) => node.getAttribute('aria-label')?.startsWith(label));
  expect(region, `no column labelled ${label}`).toBeDefined();
  return region as HTMLElement;
}

async function dragWithKeyboard(
  user: ReturnType<typeof userEvent.setup>,
  company: string,
  keys: string,
) {
  const handle = await draggableFor(company);
  handle.focus();
  expect(handle).toHaveFocus();
  await user.keyboard(' '); // pick up
  await user.keyboard(keys); // move
  await user.keyboard(' '); // drop
}

describe('the board', () => {
  it('renders all seven columns in the documented order', async () => {
    renderView(boardOf({ wishlist: [card('a')] }));

    const board = await boardEl();
    const labels = within(board)
      .getAllByRole('region')
      .map((node) => node.getAttribute('aria-label'));
    expect(labels).toEqual([
      '想投（1）',
      '已投递（0）',
      '笔试 / OA（0）',
      '面试（0）',
      '终面（0）',
      'Offer（0）',
      '已结束（0）',
    ]);
  });

  it('renders the same cards as a list for narrow screens', async () => {
    renderView(boardOf({ wishlist: [card('a', { company: '窄屏公司' })] }));

    const list = await screen.findByTestId('application-list');
    expect(within(list).getByText('窄屏公司')).toBeInTheDocument();
  });

  it('shows an un-scored card as un-scored rather than as zero', async () => {
    renderView(boardOf({ wishlist: [card('a', { matchScore: null, company: '未评分公司' })] }));
    const handle = await draggableFor('未评分公司');
    expect(within(handle).getByText('未评分')).toBeInTheDocument();
  });

  it('tells a new account what to do instead of showing seven empty columns', async () => {
    renderView(boardOf({}));
    expect(await screen.findByText('还没有在跟的岗位')).toBeInTheDocument();
    // Two entry points on purpose: the header action is always there, and the empty state
    // offers the same thing where the eye already is.
    expect(screen.getAllByRole('button', { name: /加入投递/ }).length).toBeGreaterThanOrEqual(2);
  });
});

describe('moving a card', () => {
  it('moves it with the keyboard and sends the documented payload', async () => {
    const user = renderView(boardOf({ wishlist: [card('a', { company: '智远科技' })] }));
    mocked.reorderApplications.mockResolvedValue([]);

    await dragWithKeyboard(user, '智远科技', '{ArrowRight}');

    await waitFor(() => expect(mocked.reorderApplications).toHaveBeenCalledTimes(1));
    expect(mocked.reorderApplications).toHaveBeenCalledWith([
      { id: 'a', status: 'applied', position: 0 },
    ]);
  });

  it('applies the move before the server answers', async () => {
    // A promise that never settles: whatever is on screen now is the optimistic result.
    mocked.reorderApplications.mockReturnValue(new Promise(() => {}));
    const user = renderView(boardOf({ wishlist: [card('a', { company: '智远科技' })] }));

    await dragWithKeyboard(user, '智远科技', '{ArrowRight}');

    const board = await boardEl();
    await waitFor(() => {
      expect(within(columnNamed(board, '已投递')).getByText('智远科技')).toBeInTheDocument();
    });
    expect(within(columnNamed(board, '想投')).queryByText('智远科技')).not.toBeInTheDocument();
  });

  it('rolls back and explains itself when the write fails', async () => {
    mocked.reorderApplications.mockRejectedValue(new Error('boom'));
    const user = renderView(boardOf({ wishlist: [card('a', { company: '智远科技' })] }));

    await dragWithKeyboard(user, '智远科技', '{ArrowRight}');

    await waitFor(() => expect(toast.error).toHaveBeenCalledTimes(1));
    // The message names the destination the user was aiming for, in the same words the
    // column header uses — "applied" would be the API's vocabulary, not theirs.
    expect(toast.error).toHaveBeenCalledWith('移动失败，已回滚', {
      description: '已投递 · boom',
    });
    const board = await boardEl();
    await waitFor(() => {
      expect(within(columnNamed(board, '想投')).getByText('智远科技')).toBeInTheDocument();
    });
    expect(within(columnNamed(board, '已投递')).queryByText('智远科技')).not.toBeInTheDocument();
  });

  it('moves a card through the card menu, which is the path touch devices use', async () => {
    const user = renderView(boardOf({ wishlist: [card('a', { company: '智远科技' })] }));
    mocked.reorderApplications.mockResolvedValue([]);

    const handle = await draggableFor('智远科技');
    await user.click(within(handle).getByRole('button', { name: /更多操作/ }));
    await user.click(await screen.findByRole('menuitem', { name: '面试' }));

    await waitFor(() => expect(mocked.reorderApplications).toHaveBeenCalledTimes(1));
    expect(mocked.reorderApplications).toHaveBeenCalledWith([
      { id: 'a', status: 'interview', position: 0 },
    ]);
  });
});
