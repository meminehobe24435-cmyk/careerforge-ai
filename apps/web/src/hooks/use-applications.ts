'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import type {
  ApplicationBoardResponse,
  ApplicationCreateRequest,
  ApplicationDetail,
  ApplicationStatus,
  ApplicationUpdateRequest,
} from '@careerforge/shared';
import { getErrorMessage } from '@careerforge/shared';

import { api } from '@/lib/api';
import { applyMove, toReorderItem, type BoardMove } from '@/lib/board-state';
import { labelOf } from '@/lib/application-status';
import { queryKeys } from '@/lib/query-keys';

/**
 * Board queries and the optimistic mutations behind every interaction (PRD FR-13.2).
 *
 * The shape is the same for all three write paths:
 *
 * 1. `onMutate` cancels in-flight reads, snapshots the cached board, and writes the
 *    predicted board through `applyMove` — the same arithmetic the server uses, so the
 *    prediction is a model of the server rather than a guess about it;
 * 2. `onError` restores the snapshot **and says what failed** — a rollback nobody notices is
 *    indistinguishable from the drag simply not working, which is how a board loses trust;
 * 3. `onSettled` invalidates, so a successful write reconciles with the server's own ordering
 *    instead of leaving the optimistic copy in place forever.
 */

const boardKey = () => queryKeys.applications.board();

export function useApplicationBoard(options: { includeArchived?: boolean } = {}) {
  const includeArchived = options.includeArchived ?? false;
  return useQuery({
    queryKey: queryKeys.applications.board(includeArchived),
    queryFn: () => api.applicationBoard({ includeArchived }),
    retry: 1,
    staleTime: 15_000,
  });
}

export function useApplication(id: string | null) {
  return useQuery({
    queryKey: queryKeys.applications.detail(id ?? ''),
    queryFn: () => api.application(id as string),
    enabled: Boolean(id),
    retry: 1,
  });
}

interface MoveContext {
  previous?: ApplicationBoardResponse;
}

/** Move one card, optimistically. Used by drag-and-drop and by the card menu alike. */
export function useMoveApplication() {
  const queryClient = useQueryClient();
  return useMutation<unknown, unknown, BoardMove, MoveContext>({
    mutationFn: (move) => api.reorderApplications([toReorderItem(move)]),
    onMutate: async (move) => {
      await queryClient.cancelQueries({ queryKey: boardKey() });
      const previous = queryClient.getQueryData<ApplicationBoardResponse>(boardKey());
      if (previous) {
        queryClient.setQueryData(boardKey(), applyMove(previous, move));
      }
      return { previous };
    },
    onError: (error, move, context) => {
      if (context?.previous) {
        queryClient.setQueryData(boardKey(), context.previous);
      }
      toast.error('移动失败，已回滚', {
        description: `${labelOf(move.toStatus)} · ${getErrorMessage(error)}`,
      });
    },
    onSuccess: (_data, move) => {
      toast.success(`已移到「${labelOf(move.toStatus)}」`);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications.all() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.root() });
    },
  });
}

interface UpdateContext {
  previous?: ApplicationBoardResponse;
}

/**
 * Field updates, archiving included.
 *
 * A status change through this path is *not* applied optimistically: the server decides what
 * a transition means (stamping `appliedAt`, clearing a closed card's next action), and
 * predicting those side effects would mean duplicating that policy in the client. Only the
 * card's own visible fields move immediately.
 */
export function useUpdateApplication() {
  const queryClient = useQueryClient();
  return useMutation<
    unknown,
    unknown,
    { id: string; payload: ApplicationUpdateRequest; optimisticStatus?: ApplicationStatus },
    UpdateContext
  >({
    mutationFn: ({ id, payload }) => api.updateApplication(id, payload),
    onMutate: async ({ id, payload }) => {
      await queryClient.cancelQueries({ queryKey: boardKey() });
      const previous = queryClient.getQueryData<ApplicationBoardResponse>(boardKey());
      if (previous && payload.archived) {
        queryClient.setQueryData(boardKey(), removeCard(previous, id));
      }
      return { previous };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(boardKey(), context.previous);
      }
      toast.error('更新失败，已回滚', { description: getErrorMessage(error) });
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications.all() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.root() });
    },
  });
}

export function useCreateApplication() {
  const queryClient = useQueryClient();
  return useMutation<unknown, unknown, ApplicationCreateRequest>({
    mutationFn: (payload) => api.createApplication(payload),
    onSuccess: (_data, payload) => {
      toast.success(`已加入看板：${payload.company ?? payload.role ?? '新岗位'}`);
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications.all() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.root() });
    },
    onError: (error) => {
      toast.error('加入看板失败', { description: getErrorMessage(error) });
    },
  });
}

export function useDeleteApplication() {
  const queryClient = useQueryClient();
  return useMutation<unknown, unknown, { id: string; label: string }, UpdateContext>({
    mutationFn: ({ id }) => api.deleteApplication(id),
    onMutate: async ({ id }) => {
      await queryClient.cancelQueries({ queryKey: boardKey() });
      const previous = queryClient.getQueryData<ApplicationBoardResponse>(boardKey());
      if (previous) queryClient.setQueryData(boardKey(), removeCard(previous, id));
      return { previous };
    },
    onError: (error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(boardKey(), context.previous);
      }
      toast.error('删除失败，已回滚', { description: getErrorMessage(error) });
    },
    onSuccess: (_data, variables) => {
      toast.success(`已删除：${variables.label}`);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.applications.all() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.root() });
    },
  });
}

function removeCard(board: ApplicationBoardResponse, cardId: string): ApplicationBoardResponse {
  const columns = board.columns.map((column) => ({
    status: column.status,
    items: column.items
      .filter((item) => item.id !== cardId)
      .map((item, index) => (item.position === index ? item : { ...item, position: index })),
  }));
  return {
    columns,
    counts: Object.fromEntries(columns.map((column) => [column.status, column.items.length])),
    total: columns.reduce((sum, column) => sum + column.items.length, 0),
    archived: board.archived,
  };
}

/** A card's history, fetched when a detail panel opens. */
export type { ApplicationDetail };
