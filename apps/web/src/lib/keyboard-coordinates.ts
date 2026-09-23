'use client';

import type { KeyboardCoordinateGetter } from '@dnd-kit/core';

/**
 * Arrow-key movement across a kanban board.
 *
 * dnd-kit's stock `sortableKeyboardCoordinates` only walks the sortable items of the
 * container the drag started in: with it, a card picked up with the keyboard can be reordered
 * *within* its column and can never be moved to another one — i.e. the keyboard path cannot
 * do the thing the board exists for. So the coordinate getter is written here.
 *
 * It works on measured rectangles: for the pressed arrow it takes every other droppable
 * strictly in that direction (cards and columns alike, which is what makes an *empty* column
 * reachable) and moves the dragged rectangle onto the nearest one. dnd-kit then re-runs
 * collision detection at that position, so `over` becomes the target and the drop handler
 * needs no special case for the keyboard.
 *
 * Ordering is "nearest on the pressed axis first, then nearest overall". For ArrowRight that
 * means the next column; for ArrowDown, the next card in the same column — which is what a
 * person expects from each key.
 */

type Axis = 'x' | 'y';

const DIRECTIONS: Record<string, { axis: Axis; sign: 1 | -1 }> = {
  ArrowDown: { axis: 'y', sign: 1 },
  ArrowUp: { axis: 'y', sign: -1 },
  ArrowRight: { axis: 'x', sign: 1 },
  ArrowLeft: { axis: 'x', sign: -1 },
};

export const boardKeyboardCoordinates: KeyboardCoordinateGetter = (event, { context }) => {
  const direction = DIRECTIONS[event.code];
  if (!direction) return undefined;

  const { active, collisionRect, droppableRects, droppableContainers } = context;
  if (!active) return undefined;

  // The origin is the drag's *current* position, so repeated presses accumulate: the second
  // ArrowRight moves two columns, not one. `collisionRect` is that position, and the card's
  // own measured rect is the fallback for the first press (before any move has happened) or
  // for a sensor that has not measured one yet. A zero-sized rect is treated as absent — it
  // makes every droppable equidistant, which is worse than having no origin at all.
  const measured = droppableRects.get(active.id);
  const originRect = collisionRect && collisionRect.width > 0 ? collisionRect : measured;
  if (!originRect) return undefined;
  const origin = {
    x: originRect.left,
    y: originRect.top,
    centerY: originRect.top + originRect.height / 2,
    centerX: originRect.left + originRect.width / 2,
  };

  const candidates = droppableContainers
    .getEnabled()
    .filter((container) => container.id !== active.id)
    .map((container) => ({ id: container.id, rect: droppableRects.get(container.id) }))
    .filter((entry): entry is { id: string | number; rect: DOMRect } => Boolean(entry.rect))
    .filter(({ rect }) => {
      const primary = direction.axis === 'x' ? rect.left - origin.x : rect.top - origin.y;
      // Strictly in the pressed direction, and far enough to be a different target: an
      // offset of a few pixels is the same element, not the next one.
      return primary * direction.sign > 4;
    });

  if (candidates.length === 0) return undefined;

  const primaryOf = (rect: DOMRect) =>
    direction.axis === 'x' ? Math.abs(rect.left - origin.x) : Math.abs(rect.top - origin.y);
  const secondaryOf = (rect: DOMRect) =>
    direction.axis === 'x'
      ? Math.abs(rect.top + rect.height / 2 - origin.centerY)
      : Math.abs(rect.left - origin.x);

  const target = candidates.reduce((best, candidate) => {
    const bestPrimary = primaryOf(best.rect);
    const candidatePrimary = primaryOf(candidate.rect);
    if (candidatePrimary < bestPrimary - 1) return candidate;
    if (
      Math.abs(candidatePrimary - bestPrimary) <= 1 &&
      secondaryOf(candidate.rect) < secondaryOf(best.rect)
    ) {
      return candidate;
    }
    return best;
  });

  return { x: target.rect.left, y: target.rect.top };
};
