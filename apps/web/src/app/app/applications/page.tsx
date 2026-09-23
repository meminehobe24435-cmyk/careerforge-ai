import type { Metadata } from 'next';

import { ApplicationsView } from '@/components/applications/applications-view';

export const metadata: Metadata = {
  title: '投递看板',
  description: '七列投递看板，拖拽或方向键改状态，每次变更都写进投递历史。',
};

/** `/app/applications` — data comes from `GET /applications/board` via React Query. */
export default function ApplicationsPage() {
  return <ApplicationsView />;
}
