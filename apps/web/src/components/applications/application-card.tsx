'use client';

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Badge, Card, cn } from '@careerforge/ui';
import type { ApplicationCard } from '@careerforge/shared';
import { GripVertical, MapPin, Wallet } from 'lucide-react';

import { ApplicationCardMenu } from '@/components/applications/application-card-menu';
import { STATUS_TONES } from '@/lib/application-status';
import { formatDateTime } from '@/lib/utils';

interface ApplicationCardViewProps {
  card: ApplicationCard;
  columnStatus: string;
  /** Index within its column — the sortable context needs it, and tests read it for layout. */
  index: number;
  disabled?: boolean;
}

/**
 * One board card (PRD FR-13.3: Company / Role / Location / Salary / Status / Match Score /
 * Date / Notes).
 *
 * The whole card is the drag handle rather than a small grip, because the grip is the
 * smallest target on the screen; the grip icon stays as a visual affordance. `attributes`
 * from `useSortable` carry the ARIA wiring and, with the keyboard sensor, make the card
 * focusable and operable with Space + arrows — which is the phase's a11y requirement, not a
 * decoration.
 */
export function ApplicationCardView({
  card,
  columnStatus,
  index,
  disabled = false,
}: ApplicationCardViewProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: card.id,
    disabled,
  });

  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
  };

  return (
    <Card
      ref={setNodeRef}
      style={style}
      data-card-id={card.id}
      data-index={index}
      data-column={columnStatus}
      className={cn(
        'bg-surface group flex flex-col gap-2 p-3',
        isDragging && 'opacity-40',
        !disabled && 'cursor-grab active:cursor-grabbing',
      )}
      {...attributes}
      {...listeners}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <p className="text-primary truncate text-sm font-medium" title={card.company}>
            {card.company || '（未填公司）'}
          </p>
          <p className="text-secondary truncate text-xs" title={card.role}>
            {card.role || '（未填岗位）'}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <GripVertical
            className="text-tertiary size-3.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
            aria-hidden="true"
          />
          <ApplicationCardMenu card={card} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant={STATUS_TONES[card.status]}>{card.status}</Badge>
        {card.matchScore !== null ? (
          <Badge variant="outline">匹配 {Math.round(card.matchScore)}</Badge>
        ) : (
          // "Never scored" is not "scored zero", so it says so instead of printing 0.
          <Badge variant="outline" title="这个岗位还没有跑过匹配">
            未评分
          </Badge>
        )}
        {card.location ? (
          <span className="text-tertiary inline-flex items-center gap-1 text-[11px]">
            <MapPin className="size-3" aria-hidden="true" />
            {card.location}
          </span>
        ) : null}
        {card.salaryExpectation ? (
          <span className="text-tertiary inline-flex items-center gap-1 text-[11px]">
            <Wallet className="size-3" aria-hidden="true" />
            {card.salaryExpectation}
          </span>
        ) : null}
      </div>

      {card.notes ? (
        <p className="text-tertiary line-clamp-2 text-[11px] leading-relaxed">{card.notes}</p>
      ) : null}

      <div className="text-tertiary flex items-center justify-between gap-2 font-mono text-[10px]">
        <span>{card.appliedAt ? `投递 ${formatDateTime(card.appliedAt)}` : '尚未投递'}</span>
        {card.nextActionAt ? <span>待办 {formatDateTime(card.nextActionAt)}</span> : null}
      </div>
    </Card>
  );
}
