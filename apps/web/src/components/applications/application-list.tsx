'use client';

import { Badge, Card, cn } from '@careerforge/ui';
import { APPLICATION_STATUSES, type ApplicationBoardResponse } from '@careerforge/shared';

import { ApplicationCardMenu } from '@/components/applications/application-card-menu';
import { STATUS_LABELS } from '@/lib/application-status';
import { formatDateTime } from '@/lib/utils';

interface ApplicationListProps {
  board: ApplicationBoardResponse;
}

/**
 * The board as a list, for narrow screens.
 *
 * Not a squeezed board: at 390px seven columns are unusable and drag-and-drop on a phone
 * fights the page scroll. The list keeps every field and every action — the card menu is the
 * move path here, which is why the menu exists as a first-class control rather than as an
 * accessibility afterthought.
 */
export function ApplicationList({ board }: ApplicationListProps) {
  const empty = board.columns.every((column) => column.items.length === 0);

  return (
    <div className="flex flex-col gap-4 md:hidden" data-testid="application-list">
      {empty ? <p className="text-secondary text-xs">看板还是空的。</p> : null}
      {board.columns
        .filter((column) => column.items.length > 0)
        .map((column) => (
          <section
            key={column.status}
            aria-label={STATUS_LABELS[column.status]}
            className="flex flex-col gap-2"
          >
            <h3 className="text-secondary text-xs font-semibold">
              {STATUS_LABELS[column.status]}
              <span className="text-tertiary ml-2 font-mono text-[10px]">
                {column.items.length}
              </span>
            </h3>
            {column.items.map((card) => (
              <Card key={card.id} className={cn('flex flex-col gap-2 p-3')}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <p className="text-primary truncate text-sm font-medium">
                      {card.company || '（未填公司）'}
                    </p>
                    <p className="text-secondary truncate text-xs">{card.role || '（未填岗位）'}</p>
                  </div>
                  <ApplicationCardMenu card={card} />
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline">{card.status}</Badge>
                  {card.matchScore !== null ? (
                    <Badge variant="outline">匹配 {Math.round(card.matchScore)}</Badge>
                  ) : null}
                  {card.location ? (
                    <span className="text-tertiary text-[11px]">{card.location}</span>
                  ) : null}
                </div>
                <p className="text-tertiary font-mono text-[10px]">
                  {card.appliedAt ? `投递 ${formatDateTime(card.appliedAt)}` : '尚未投递'}
                </p>
              </Card>
            ))}
          </section>
        ))}
      <p className="text-tertiary text-[11px] leading-relaxed">
        窄屏用列表：七列在手机上无法使用，拖拽也会和页面滚动打架。用卡片右上角的菜单改状态，
        和拖拽走的是同一个接口。
      </p>
    </div>
  );
}

export { APPLICATION_STATUSES };
