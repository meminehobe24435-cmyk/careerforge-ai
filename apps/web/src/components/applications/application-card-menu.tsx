'use client';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  IconButton,
} from '@careerforge/ui';
import { APPLICATION_STATUSES, type ApplicationCard } from '@careerforge/shared';
import { Archive, MoreHorizontal, Trash2 } from 'lucide-react';

import { STATUS_LABELS } from '@/lib/application-status';
import {
  useDeleteApplication,
  useMoveApplication,
  useUpdateApplication,
} from '@/hooks/use-applications';

interface ApplicationCardMenuProps {
  card: ApplicationCard;
}

/**
 * The card's non-drag and non-pointer path: move, archive, delete.
 *
 * This is not a fallback bolted on for accessibility — it is the primary path on touch, the
 * discoverable path for anyone who does not know the board is draggable, and the only place
 * archive/delete live. It calls exactly the same mutation as a drag, so the two cannot drift.
 */
export function ApplicationCardMenu({ card }: ApplicationCardMenuProps) {
  const move = useMoveApplication();
  const update = useUpdateApplication();
  const remove = useDeleteApplication();

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {/* The card itself carries drag listeners, so every pointer event on the menu must
            stop before it reaches them — otherwise opening the menu starts a drag. */}
        <IconButton
          aria-label={`${card.company || '这张卡片'} 的更多操作`}
          variant="ghost"
          size="sm"
          onPointerDown={(event) => event.stopPropagation()}
          onKeyDown={(event) => event.stopPropagation()}
        >
          <MoreHorizontal className="size-4" aria-hidden="true" />
        </IconButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-44">
        <DropdownMenuLabel className="text-tertiary text-[11px]">移动到</DropdownMenuLabel>
        {APPLICATION_STATUSES.filter((status) => status !== card.status).map((status) => (
          <DropdownMenuItem
            key={status}
            onSelect={() => move.mutate({ cardId: card.id, toStatus: status, toIndex: 0 })}
          >
            {STATUS_LABELS[status]}
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => update.mutate({ id: card.id, payload: { archived: true } })}
        >
          <Archive className="size-3.5" aria-hidden="true" />
          归档（保留历史）
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={() =>
            remove.mutate({ id: card.id, label: card.company || card.role || '这张卡片' })
          }
        >
          <Trash2 className="size-3.5" aria-hidden="true" />
          删除
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
