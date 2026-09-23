'use client';

import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  closestCorners,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import { useState } from 'react';
import type { ApplicationBoardResponse, ApplicationCard } from '@careerforge/shared';

import { BoardColumn } from '@/components/applications/board-column';
import { ApplicationCardView } from '@/components/applications/application-card';
import { boardKeyboardCoordinates } from '@/lib/keyboard-coordinates';
import { locateCard, resolveDrop, type BoardMove } from '@/lib/board-state';

interface KanbanBoardProps {
  board: ApplicationBoardResponse;
  onMove: (move: BoardMove) => void;
  /** True while a write is in flight, which disables interaction rather than queueing it. */
  pending?: boolean;
}

/**
 * The seven-column board (PRD FR-13.1).
 *
 * The card follows the cursor in a `DragOverlay` rather than being re-ordered live under it.
 * That is a deliberate trade: live reordering gives a slightly nicer preview and costs a
 * class of bugs where the list shifts mid-gesture and the card lands next to where the user
 * aimed. The board re-renders once, on drop, with the optimistic result — which is already
 * what the server will confirm.
 *
 * Both sensors are enabled: pointer for a mouse, keyboard for Space + arrows. The keyboard
 * sensor gets the custom coordinate getter (see `lib/keyboard-coordinates.ts`) because the
 * stock one cannot cross columns.
 */
export function KanbanBoard({ board, onMove, pending = false }: KanbanBoardProps) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const sensors = useSensors(
    // A small activation distance keeps a click on the card menu from starting a drag.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: boardKeyboardCoordinates }),
  );

  const activeCard: ApplicationCard | null = activeId
    ? (locateCard(board, activeId)?.card ?? null)
    : null;

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null);
    const { active, over } = event;
    if (!over) return;
    const move = resolveDrop(board, String(active.id), over.id);
    if (move) onMove(move);
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={() => setActiveId(null)}
      accessibility={{
        announcements: {
          onDragStart: ({ active }) =>
            `已拿起卡片 ${active.id}，用方向键选择列，空格放下，Esc 取消`,
          onDragOver: ({ over }) => (over ? `移动到 ${over.id}` : '当前不在任何列上'),
          onDragEnd: ({ over }) => (over ? `已放到 ${over.id}` : '已取消'),
          onDragCancel: () => '已取消拖动',
        },
      }}
    >
      <div
        className="flex gap-3 overflow-x-auto pb-2"
        data-testid="kanban-board"
        aria-busy={pending || undefined}
      >
        {board.columns.map((column) => (
          <BoardColumn key={column.status} column={column} disabled={pending} />
        ))}
      </div>

      <DragOverlay dropAnimation={null}>
        {activeCard ? (
          <div className="w-[280px] rotate-1">
            <ApplicationCardView
              card={activeCard}
              columnStatus={activeCard.status}
              index={activeCard.position}
              disabled
            />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
