import { vi } from 'vitest';

import { APPLICATION_STATUSES, type ApplicationStatus } from '@careerforge/shared';

/**
 * A synthetic layout for board tests.
 *
 * jsdom implements no layout at all: every `getBoundingClientRect()` returns zeros, which
 * makes every droppable equidistant and leaves dnd-kit's collision detection — the thing that
 * turns an arrow key into a target column — with nothing to work from. So the tests describe
 * the layout they assume, in the same units the real board uses:
 *
 * * 280px columns with a 16px gap, side by side in the documented order (docs/UI.md §5.13);
 * * 80px cards stacked from a 44px column header, 8px apart;
 * * the board itself is the horizontal scroll container.
 *
 * Two details cost real debugging time and are the reason this file exists rather than a
 * three-line stub in each test:
 *
 * 1. the board must report a **sized** rect — dnd-kit's keyboard sensor clamps movement into
 *    the scrollable ancestor, so a 0×0 board pins every arrow key in place;
 * 2. anything without a column (the drag overlay's wrapper, which is what dnd-kit measures
 *    for the dragging item) must be **card-sized** — a board-sized rect there makes collision
 *    detection pick whichever column sits nearest the centre of the screen, and one ArrowRight
 *    then lands four columns away.
 */

export const COLUMN_WIDTH = 280;
export const COLUMN_GAP = 16;
export const CARD_HEIGHT = 80;
export const CARD_GAP = 8;
export const HEADER_HEIGHT = 44;
export const BOARD_RECT = { width: 1920, height: 600 } as const;

export function rect(left: number, top: number, width: number, height: number): DOMRect {
  return {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
}

/** Install the synthetic layout for the duration of one test file. */
export function installBoardLayout(): void {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    const status = this.dataset?.['column'];

    if (!status) {
      if (this.dataset?.['testid'] === 'kanban-board') {
        return rect(0, 0, BOARD_RECT.width, BOARD_RECT.height);
      }
      return rect(0, HEADER_HEIGHT, COLUMN_WIDTH, CARD_HEIGHT);
    }

    const columnIndex = APPLICATION_STATUSES.indexOf(status as ApplicationStatus);
    const left = columnIndex * (COLUMN_WIDTH + COLUMN_GAP);
    const cardId = this.dataset?.['cardId'];
    if (cardId) {
      const index = Number(this.dataset?.['index'] ?? '0');
      return rect(
        left,
        HEADER_HEIGHT + index * (CARD_HEIGHT + CARD_GAP),
        COLUMN_WIDTH,
        CARD_HEIGHT,
      );
    }
    return rect(left, 0, COLUMN_WIDTH, 4 * (CARD_HEIGHT + CARD_GAP) + HEADER_HEIGHT);
  });
}
