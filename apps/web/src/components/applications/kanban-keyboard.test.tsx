import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type {
  ApplicationBoardResponse,
  ApplicationCard,
  ApplicationStatus,
} from '@careerforge/shared';
import { APPLICATION_STATUSES } from '@careerforge/shared';

import { KanbanBoard } from '@/components/applications/kanban-board';
import { installBoardLayout } from '@/test/layout';

/**
 * The keyboard path, tested against the board itself.
 *
 * This is the phase's accessibility requirement, and it is not a formality: dnd-kit's stock
 * `sortableKeyboardCoordinates` only walks the sortable items of the column the drag started
 * in, so with it a card picked up by keyboard can never change columns — the one thing the
 * board is for. `lib/keyboard-coordinates.ts` is ours, and these are its tests:
 *
 * * ArrowRight moves one column right, and pressing it twice moves two (the position
 *   accumulates rather than snapping back to where the drag started);
 * * ArrowDown reorders within the column;
 * * the drop sends the move the API expects, in the API's vocabulary.
 *
 * The board is rendered directly with a spy for `onMove`, so a failure here is a failure of
 * the interaction and not of the data plumbing — that wiring has its own test in
 * `applications-board.test.tsx`.
 */

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), message: vi.fn() },
}));

beforeEach(() => {
  installBoardLayout();
});

function card(id: string, overrides: Partial<ApplicationCard> = {}): ApplicationCard {
  return {
    id,
    jobId: null,
    resumeVersionId: null,
    company: `公司 ${id}`,
    role: '工程师',
    location: null,
    status: 'wishlist',
    matchScore: null,
    salaryExpectation: null,
    notes: '',
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
    items: (columns[status] ?? []).map((item, index) => ({ ...item, status, position: index })),
  }));
  return {
    columns: all,
    counts: Object.fromEntries(all.map((column) => [column.status, column.items.length])),
    total: all.reduce((sum, column) => sum + column.items.length, 0),
    archived: 0,
  };
}

async function dragCard(keys: string) {
  const onMove = vi.fn();
  const user = userEvent.setup();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <KanbanBoard
        board={boardOf({
          wishlist: [card('a', { company: '智远科技' }), card('b', { company: '第二家' })],
        })}
        onMove={onMove}
      />
    </QueryClientProvider>,
  );

  const board = screen.getByTestId('kanban-board');
  const handle = within(board).getByText('智远科技').closest('[data-card-id]') as HTMLElement;
  expect(handle).toBeTruthy();

  handle.focus();
  expect(handle).toHaveFocus();
  await user.keyboard(' '); // pick up
  await user.keyboard(keys); // move
  await user.keyboard(' '); // drop

  return onMove.mock.calls.map((call) => call[0]);
}

describe('keyboard drag', () => {
  it('moves the card one column to the right', async () => {
    expect(await dragCard('{ArrowRight}')).toEqual([
      { cardId: 'a', toStatus: 'applied', toIndex: 0 },
    ]);
  });

  it('accumulates: a second press moves two columns', async () => {
    expect(await dragCard('{ArrowRight}{ArrowRight}')).toEqual([
      { cardId: 'a', toStatus: 'oa', toIndex: 0 },
    ]);
  });

  it('reorders within the column with ArrowDown', async () => {
    expect(await dragCard('{ArrowDown}')).toEqual([
      { cardId: 'a', toStatus: 'wishlist', toIndex: 1 },
    ]);
  });

  it('carries the ARIA wiring a screen reader needs to operate it', async () => {
    const onMove = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <KanbanBoard
          board={boardOf({ wishlist: [card('a', { company: '智远科技' })] })}
          onMove={onMove}
        />
      </QueryClientProvider>,
    );

    const board = screen.getByTestId('kanban-board');
    const handle = within(board).getByText('智远科技').closest('[data-card-id]') as HTMLElement;

    // dnd-kit's attributes: focusable, announced as a sortable, and described by the hidden
    // instructions node the context creates.
    expect(handle).toHaveAttribute('role', 'button');
    expect(handle).toHaveAttribute('tabindex', '0');
    expect(handle).toHaveAttribute('aria-roledescription', 'sortable');
    const describedBy = handle.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy as string)).not.toBeNull();

    // The announcement *text* is announced through a live region that only updates while a
    // drag is in flight, and jsdom does not run the screen reader; the wiring above is what
    // can be asserted honestly here. The keyboard path itself is asserted by the tests above.
  });
});
