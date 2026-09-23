import type { Metadata } from 'next';

import { DashboardView } from '@/components/dashboard/dashboard-view';

export const metadata: Metadata = {
  title: '总览',
  description: 'Profile Strength、六项核心指标、最近岗位与下一步行动。',
};

/** `/app/dashboard` ★ — data comes from `GET /dashboard` via React Query. */
export default function DashboardPage() {
  return <DashboardView />;
}
