import { APPLICATION_STATUSES } from '@careerforge/shared';
import type {
  ApplicationBoardResponse,
  ApplicationCard,
  ApplicationColumn,
  ApplicationStatus,
} from '@careerforge/shared';

/**
 * Pure board arithmetic.
 *
 * Everything here is a function of `(board, interaction)` → `board`, with no React and no
 * network, for one reason: **the optimistic update must produce exactly what the server will
 * return.** The server's rule (see `services/application_service.py`) is "remove the card,
 * insert it at the requested index, renumber that column densely from zero". `applyMove`
 * implements that same rule, so a drag shows the user the truth immediately rather than a
 * guess that the response then corrects.
 *
 * It is also the only part of the drag that can be tested without a browser, so it is tested
 * exhaustively in `board-state.test.ts`.
 */

/** Prefix that distinguishes a column droppable from a card droppable. */
export const COLUMN_PREFIX = 'column:';

/** One card's target place, in the vocabulary the API's reorder endpoint speaks. */
export interface BoardMove {
  cardId: string;
  toStatus: ApplicationStatus;
  toIndex: number;
}

export function columnDroppableId(status: ApplicationStatus): string {
  return `${COLUMN_PREFIX}${status}`;
}

export type DroppableTarget =
  { kind: 'column'; status: ApplicationStatus } | { kind: 'card'; id: string } | null;

export function parseDroppableId(value: string | number | null | undefined): DroppableTarget {
  if (typeof value !== 'string' || value.length === 0) return null;
  if (value.startsWith(COLUMN_PREFIX)) {
    const status = value.slice(COLUMN_PREFIX.length);
    return (APPLICATION_STATUSES as readonly string[]).includes(status)
      ? { kind: 'column', status: status as ApplicationStatus }
      : null;
  }
  return { kind: 'card', id: value };
}

/** Where a card currently sits, or `null` when it is not on this board. */
export function locateCard(
  board: ApplicationBoardResponse,
  cardId: string,
): { status: ApplicationStatus; index: number; card: ApplicationCard } | null {
  for (const column of board.columns) {
    const index = column.items.findIndex((item) => item.id === cardId);
    if (index >= 0) {
      const card = column.items[index];
      if (card) return { status: column.status, index, card };
    }
  }
  return null;
}

/**
 * Turn a drop into a move, in the coordinates the server expects.
 *
 * Dropping on a card means "take that card's place": the index is the target card's index
 * **after** the dragged card has been removed, which is the same arithmetic as
 * `arrayMove(items, from, to)` for a within-column move — so a reorder inside one column and
 * a move across two columns need no special cases.
 *
 * Dropping on a column (its header or its empty space) appends to the end.
 */
export function resolveDrop(
  board: ApplicationBoardResponse,
  activeCardId: string,
  overDroppableId: string | number | null | undefined,
): BoardMove | null {
  const target = parseDroppableId(overDroppableId);
  if (!target) return null;
  const origin = locateCard(board, activeCardId);
  if (!origin) return null;

  if (target.kind === 'card') {
    if (target.id === activeCardId) return null;
    const over = locateCard(board, target.id);
    if (!over) return null;
    return { cardId: activeCardId, toStatus: over.status, toIndex: over.index };
  }

  const column = board.columns.find((candidate) => candidate.status === target.status);
  if (!column) return null;
  const items = column.items.filter((item) => item.id !== activeCardId);
  return { cardId: activeCardId, toStatus: target.status, toIndex: items.length };
}

function renumber(items: ApplicationCard[]): ApplicationCard[] {
  return items.map((item, index) =>
    item.position === index ? item : { ...item, position: index },
  );
}

/**
 * Apply a move optimistically.
 *
 * Returns a new board; the input is never mutated, because React Query hands the cached
 * object straight back on rollback and an in-place edit would corrupt the snapshot it is
 * supposed to restore.
 */
export function applyMove(
  board: ApplicationBoardResponse,
  move: BoardMove,
): ApplicationBoardResponse {
  const origin = locateCard(board, move.cardId);
  if (!origin) return board;

  const columns: ApplicationColumn[] = board.columns.map((column) => ({
    status: column.status,
    items: column.items.filter((item) => item.id !== move.cardId),
  }));

  const destination = columns.find((column) => column.status === move.toStatus);
  if (!destination) return board;

  const moved: ApplicationCard = {
    ...origin.card,
    status: move.toStatus,
    // Mirrors the server: the column the card lands in, at the requested index.
    position: Math.max(0, Math.min(move.toIndex, destination.items.length)),
  };
  destination.items.splice(moved.position, 0, moved);

  const next: ApplicationColumn[] = columns.map((column) => ({
    status: column.status,
    items: renumber(column.items),
  }));

  const counts = Object.fromEntries(
    next.map((column) => [column.status, column.items.length]),
  ) as Record<string, number>;

  return {
    columns: next,
    counts,
    total: next.reduce((sum, column) => sum + column.items.length, 0),
    archived: board.archived,
  };
}

/** Apply several moves in order (a whole-board save, or a queued drag). */
export function applyMoves(
  board: ApplicationBoardResponse,
  moves: BoardMove[],
): ApplicationBoardResponse {
  return moves.reduce((current, move) => applyMove(current, move), board);
}

/** Every card on the board, in column order. */
export function allCards(board: ApplicationBoardResponse): ApplicationCard[] {
  return board.columns.flatMap((column) => column.items);
}

export function isEmptyBoard(board: ApplicationBoardResponse): boolean {
  return allCards(board).length === 0;
}

/** What the API expects for one move. */
export function toReorderItem(move: BoardMove): {
  id: string;
  status: ApplicationStatus;
  position: number;
} {
  return { id: move.cardId, status: move.toStatus, position: move.toIndex };
}
