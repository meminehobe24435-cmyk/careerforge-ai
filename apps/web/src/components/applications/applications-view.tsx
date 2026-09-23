'use client';

import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CodeBlock,
  EmptyState,
  ErrorState,
  Skeleton,
} from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';
import { Plus, RefreshCw, Target } from 'lucide-react';

import { ApplicationList } from '@/components/applications/application-list';
import { KanbanBoard } from '@/components/applications/kanban-board';
import { NewApplicationDialog } from '@/components/applications/new-application-dialog';
import { useApplicationBoard, useMoveApplication } from '@/hooks/use-applications';
import { API_BASE_URL } from '@/lib/api';
import { isEmptyBoard } from '@/lib/board-state';

/**
 * `/app/applications` (PRD FR-13).
 *
 * The same three states as the dashboard — loading skeleton, error with the requestId, empty
 * with a real next step — because a board that renders seven empty columns and no explanation
 * reads as broken rather than as new.
 */
export function ApplicationsView() {
  const query = useApplicationBoard();
  const move = useMoveApplication();
  const [creating, setCreating] = useState(false);

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-48" />
        <div className="flex gap-3 overflow-hidden">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-64 w-[280px] shrink-0" />
          ))}
        </div>
      </div>
    );
  }

  if (query.isError) {
    const apiError = isApiError(query.error) ? query.error : null;
    return (
      <div className="flex flex-col gap-5">
        <Header onRefresh={() => void query.refetch()} refreshing={query.isFetching} />
        <ErrorState
          title={apiError?.isNetworkError ? 'Backend not reachable' : '看板加载失败'}
          error={query.error}
          code={apiError?.code ?? 'UNKNOWN'}
          requestId={apiError?.requestId ?? null}
          onRetry={() => void query.refetch()}
          retrying={query.isFetching}
          statusHref="/system"
          details={
            <CodeBlock filename="API base URL" code={API_BASE_URL} language="txt" maxHeight={64} />
          }
        />
      </div>
    );
  }

  const board = query.data;
  if (!board) {
    return (
      <EmptyState
        icon={<Target className="size-5" />}
        title="接口返回了空数据"
        description="后端返回 success 但没有 data。请检查 /applications/board 的实现是否遵循 docs/API.md §2.9。"
      />
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <Header
        onRefresh={() => void query.refetch()}
        refreshing={query.isFetching}
        onCreate={() => setCreating(true)}
        total={board.total}
        archived={board.archived}
      />

      {isEmptyBoard(board) ? (
        <EmptyState
          icon={<Target className="size-5" />}
          title="还没有在跟的岗位"
          description="在岗位分析页点「加入投递」，或者手动录入一个内推机会。看板的每一列都对应一次状态变更，会写进投递历史。"
          action={
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-3.5" aria-hidden="true" />
              加入投递
            </Button>
          }
          hint="GET /applications/board → total 0"
        />
      ) : null}

      <KanbanBoard board={board} onMove={move.mutate} pending={move.isPending} />
      <ApplicationList board={board} />

      {archivedDead(board.archived)}
      <NewApplicationDialog open={creating} onOpenChange={setCreating} />
    </div>
  );
}

function archivedDead(archived: number) {
  if (archived <= 0) return null;
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>归档</CardTitle>
      </CardHeader>
      <CardContent className="text-secondary text-xs leading-relaxed">
        有 {archived}{' '}
        张归档卡片未显示。归档保留事件历史（漏斗统计仍能看到它们），删除则连同历史一起移除——
        两者不是同一件事，所以没有放在同一个按钮里。
      </CardContent>
    </Card>
  );
}

interface HeaderProps {
  onRefresh: () => void;
  refreshing: boolean;
  onCreate?: () => void;
  total?: number;
  archived?: number;
}

function Header({ onRefresh, refreshing, onCreate, total, archived }: HeaderProps) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-primary text-lg font-semibold tracking-tight">投递看板</h1>
        <p className="text-tertiary font-mono text-[11px]">
          GET {API_BASE_URL}/applications/board
          {typeof total === 'number' ? ` · ${total} 张卡片` : ''}
          {archived ? ` · 归档 ${archived}` : ''}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">拖拽或方向键移动 · 每次都写事件</Badge>
        {onCreate ? (
          <Button size="sm" onClick={onCreate}>
            <Plus className="size-3.5" aria-hidden="true" />
            加入投递
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          onClick={onRefresh}
          loading={refreshing}
          aria-label="刷新投递看板"
        >
          <RefreshCw className="size-3.5" aria-hidden="true" />
          刷新
        </Button>
      </div>
    </header>
  );
}
