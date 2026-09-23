'use client';

import { useDroppable } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import type { ApplicationColumn } from '@careerforge/shared';
import { cn } from '@careerforge/ui';

import { ApplicationCardView } from '@/components/applications/application-card';
import { STATUS_HINTS, STATUS_LABELS } from '@/lib/application-status';
import { columnDroppableId } from '@/lib/board-state';

interface BoardColumnProps {
  column: ApplicationColumn;
  disabled?: boolean;
}

/**
 * One board column.
 *
 * The column *and* its cards are droppables: dropping on a card means "take that card's
 * place", dropping anywhere else in the column means "append". Without the column droppable
 * an empty column could never receive a card — which is precisely the column a new user
 * needs to reach.
 */
export function BoardColumn({ column, disabled = false }: BoardColumnProps) {
  const { setNodeRef, isOver } = useDroppable({
    id: columnDroppableId(column.status),
    disabled,
  });

  return (
    <section
      ref={setNodeRef}
      data-column={column.status}
      aria-label={`${STATUS_LABELS[column.status]}（${column.items.length}）`}
      className={cn(
        'border-subtle bg-sunken/40 flex min-h-[240px] w-[280px] shrink-0 flex-col gap-2 rounded-lg border p-2 transition-colors',
        isOver && 'border-signal/40 bg-signal/5',
      )}
    >
      <header className="flex items-baseline justify-between gap-2 px-1">
        <div className="flex min-w-0 flex-col">
          <h3 className="text-primary truncate text-xs font-semibold">
            {STATUS_LABELS[column.status]}
          </h3>
          <p className="text-tertiary truncate text-[10px]">{STATUS_HINTS[column.status]}</p>
        </div>
        <span className="text-tertiary font-mono text-[10px]">{column.items.length}</span>
      </header>

      <SortableContext
        items={column.items.map((item) => item.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="flex flex-col gap-2">
          {column.items.map((card, index) => (
            <ApplicationCardView
              key={card.id}
              card={card}
              columnStatus={column.status}
              index={index}
              disabled={disabled}
            />
          ))}
        </div>
      </SortableContext>

      {column.items.length === 0 ? (
        <p className="text-tertiary px-1 py-6 text-center text-[11px]">拖到这里</p>
      ) : null}
    </section>
  );
}
