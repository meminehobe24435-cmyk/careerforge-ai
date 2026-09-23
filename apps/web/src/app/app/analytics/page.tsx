import type { Metadata } from 'next';

import { AnalyticsView } from '@/components/analytics/analytics-view';

export const metadata: Metadata = {
  title: '求职分析',
  description: '投递漏斗、核心比率、技能相关性与岗位类别表现，全部由事件流确定性计算。',
};

/** `/app/analytics` — data comes from `GET /analytics/*` via React Query. */
export default function AnalyticsPage() {
  return <AnalyticsView />;
}
