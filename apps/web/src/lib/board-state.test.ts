import { describe, expect, it } from 'vitest';

import type {
  ApplicationBoardResponse,
  ApplicationCard,
  ApplicationStatus,
} from '@careerforge/shared';

import {
  allCards,
  applyMove,
  applyMoves,
  columnDroppableId,
  isEmptyBoard,
  locateCard,
  parseDroppableId,
  resolveDrop,
  toReorderItem,
} from '@/lib/board-state';

/**
 * The optimistic update is a *model of the server*, so it is tested the way the server is:
 *
 * * the rule is "remove the card, insert it at the requested index, renumber that column
 *   densely from zero" (see `services/application_service.py`), and
 * * the interesting cases are the ones a drag produces — same column up, same column down,
 *   across columns, onto an empty column, and a no-op drop on itself.
 *
 * Everything here is a pure function, so none of it needs a browser.
 */

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

function boardOf(columns: Record<string, ApplicationCard[]>): ApplicationBoardResponse {
  const ordered = Object.keys(columns);
  const statuses: readonly ApplicationStatus[] = [
    'wishlist',
    'applied',
    'oa',
    'interview',
    'final',
    'offer',
    'rejected',
  ];
  const all = statuses.map((status) => ({
    status,
    items: (columns[status] ?? []).map((item, index) => ({
      ...item,
      status,
      position: index,
    })),
  }));
  return {
    columns: ordered.length === 0 ? [] : all,
    counts: Object.fromEntries(all.map((column) => [column.status, column.items.length])),
    total: all.reduce((sum, column) => sum + column.items.length, 0),
    archived: 0,
  };
}

const names = (board: ApplicationBoardResponse, status: string) =>
  board.columns.find((column) => column.status === status)?.items.map((item) => item.id) ?? [];

describe('droppable ids', () => {
  it('round-trips a column id and refuses an unknown status', () => {
    expect(parseDroppableId(columnDroppableId('interview'))).toEqual({
      kind: 'column',
      status: 'interview',
    });
    expect(parseDroppableId('column:ghosted')).toBeNull();
  });

  it('treats anything else as a card, and nothing at all as nothing', () => {
    expect(parseDroppableId('uuid-1')).toEqual({ kind: 'card', id: 'uuid-1' });
    expect(parseDroppableId(null)).toBeNull();
    expect(parseDroppableId(42)).toBeNull();
  });
});

describe('resolveDrop', () => {
  const board = boardOf({
    wishlist: [card('a'), card('b'), card('c')],
    applied: [card('d')],
  });

  it('drops on a column by appending to it', () => {
    expect(resolveDrop(board, 'a', columnDroppableId('applied'))).toEqual({
      cardId: 'a',
      toStatus: 'applied',
      toIndex: 1,
    });
  });

  it('appends into an empty column at index zero', () => {
    expect(resolveDrop(board, 'a', columnDroppableId('offer'))).toEqual({
      cardId: 'a',
      toStatus: 'offer',
      toIndex: 0,
    });
  });

  it('drops on a card by taking its index — downwards', () => {
    expect(resolveDrop(board, 'a', 'c')).toEqual({ cardId: 'a', toStatus: 'wishlist', toIndex: 2 });
  });

  it('drops on a card by taking its index — upwards', () => {
    expect(resolveDrop(board, 'c', 'a')).toEqual({ cardId: 'c', toStatus: 'wishlist', toIndex: 0 });
  });

  it('drops onto a card in another column', () => {
    expect(resolveDrop(board, 'a', 'd')).toEqual({ cardId: 'a', toStatus: 'applied', toIndex: 0 });
  });

  it('ignores a drop on itself, on nothing, or from a card that is not on the board', () => {
    expect(resolveDrop(board, 'a', 'a')).toBeNull();
    expect(resolveDrop(board, 'a', null)).toBeNull();
    expect(resolveDrop(board, 'zzz', 'a')).toBeNull();
  });
});

describe('applyMove', () => {
  const board = boardOf({
    wishlist: [card('a'), card('b'), card('c')],
    applied: [card('d')],
  });

  it('reorders within a column and renumbers densely', () => {
    const next = applyMove(board, { cardId: 'a', toStatus: 'wishlist', toIndex: 2 });
    expect(names(next, 'wishlist')).toEqual(['b', 'c', 'a']);
    expect(
      next.columns.find((column) => column.status === 'wishlist')?.items.map((i) => i.position),
    ).toEqual([0, 1, 2]);
  });

  it('moves across columns and leaves both renumbered', () => {
    const next = applyMove(board, { cardId: 'b', toStatus: 'applied', toIndex: 0 });
    expect(names(next, 'wishlist')).toEqual(['a', 'c']);
    expect(names(next, 'applied')).toEqual(['b', 'd']);
    expect(next.counts['wishlist']).toBe(2);
    expect(next.counts['applied']).toBe(2);
    expect(next.total).toBe(4);
  });

  it('writes the new status onto the card and keeps the rest of it', () => {
    const next = applyMove(board, { cardId: 'a', toStatus: 'offer', toIndex: 0 });
    const moved = locateCard(next, 'a');
    expect(moved?.status).toBe('offer');
    expect(moved?.card.company).toBe('公司 a');
    // The snapshot fields survive the move: a card is not rebuilt from the posting.
    expect(moved?.card.role).toBe('工程师');
  });

  it('clamps an index past the end of the column instead of dropping the card', () => {
    const next = applyMove(board, { cardId: 'a', toStatus: 'offer', toIndex: 99 });
    expect(names(next, 'offer')).toEqual(['a']);
  });

  it('does not mutate the board it was given', () => {
    const snapshot = JSON.stringify(board);
    applyMove(board, { cardId: 'a', toStatus: 'applied', toIndex: 0 });
    // React Query restores this exact object on rollback, so an in-place edit would corrupt
    // the snapshot it is supposed to bring back.
    expect(JSON.stringify(board)).toBe(snapshot);
  });

  it('is idempotent when the card is already there', () => {
    const once = applyMove(board, { cardId: 'c', toStatus: 'wishlist', toIndex: 2 });
    const twice = applyMove(once, { cardId: 'c', toStatus: 'wishlist', toIndex: 2 });
    expect(names(twice, 'wishlist')).toEqual(['a', 'b', 'c']);
    expect(twice.total).toBe(once.total);
  });

  it('returns the board unchanged for a card that is not on it', () => {
    expect(applyMove(board, { cardId: 'ghost', toStatus: 'offer', toIndex: 0 }).total).toBe(4);
  });
});

describe('board helpers', () => {
  it('counts what is displayed and reports emptiness', () => {
    const empty = boardOf({});
    expect(isEmptyBoard(empty)).toBe(true);
    const filled = boardOf({ wishlist: [card('a')], offer: [card('b')] });
    expect(isEmptyBoard(filled)).toBe(false);
    expect(allCards(filled).map((item) => item.id)).toEqual(['a', 'b']);
  });

  it('applies a queue of moves in order, as a bulk reorder would', () => {
    const board = boardOf({ wishlist: [card('a'), card('b')] });
    const next = applyMoves(board, [
      { cardId: 'a', toStatus: 'applied', toIndex: 0 },
      { cardId: 'b', toStatus: 'applied', toIndex: 1 },
    ]);
    expect(names(next, 'applied')).toEqual(['a', 'b']);
    expect(names(next, 'wishlist')).toEqual([]);
  });

  it('speaks the API vocabulary when building a reorder item', () => {
    expect(toReorderItem({ cardId: 'a', toStatus: 'interview', toIndex: 3 })).toEqual({
      id: 'a',
      status: 'interview',
      position: 3,
    });
  });
});
