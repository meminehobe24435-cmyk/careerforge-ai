import { APPLICATION_STATUSES, CLOSED_APPLICATION_STATUSES } from '@careerforge/shared';
import type { ApplicationStatus } from '@careerforge/shared';

/**
 * Board vocabulary: the status order comes from the contract, the Chinese labels from here.
 *
 * Keeping the labels out of `@careerforge/shared` is deliberate — that package is the
 * *contract* (statuses, payload shapes, guards) and copy is presentation. The order is the
 * reverse: it is contract, because the API returns its columns in it.
 */
export { APPLICATION_STATUSES };

/** Column titles, in board order. */
export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  wishlist: '想投',
  applied: '已投递',
  oa: '笔试 / OA',
  interview: '面试',
  final: '终面',
  offer: 'Offer',
  rejected: '已结束',
};

/** One-line explanation of what the column means, shown under the title. */
export const STATUS_HINTS: Record<ApplicationStatus, string> = {
  wishlist: '还在观望，没有投出去',
  applied: '简历已送达，等回复',
  oa: '在线笔试或测评',
  interview: '一面 / 二面进行中',
  final: '终面或 HR 面',
  offer: '已拿到 offer',
  rejected: '被拒或自己放弃',
};

/** Badge tone per status. Sparse on purpose: only offer/rejected are loud. */
export const STATUS_TONES: Record<ApplicationStatus, 'default' | 'signal' | 'danger' | 'outline'> =
  {
    wishlist: 'outline',
    applied: 'default',
    oa: 'default',
    interview: 'signal',
    final: 'signal',
    offer: 'signal',
    rejected: 'danger',
  };

/**
 * Whether a status closes the application.
 *
 * Mirrors the server's rule (a closed card drops its next action) so the UI can stop asking
 * for a reminder it knows the API will discard.
 */
export function isClosedStatus(status: ApplicationStatus): boolean {
  return CLOSED_APPLICATION_STATUSES.includes(status);
}

/** Human label for a status the API returned; falls back to the raw value. */
export function labelOf(status: string): string {
  return STATUS_LABELS[status as ApplicationStatus] ?? status;
}
