import type { Metadata } from 'next';

import { CostsView } from '@/components/observability/costs-view';

export const metadata: Metadata = {
  title: 'AI 成本',
  description:
    '按天、按 Agent、按功能拆分的 token 与成本，含缓存命中率、日预算护栏与提示词版本注册表。',
};

/** `/app/costs` — data comes from `GET /ai-costs/*`, `/cache/stats` and `/prompts`. */
export default function CostsPage() {
  return <CostsView />;
}
