import type { Metadata } from 'next';

import { AiRunsView } from '@/components/observability/runs-view';

export const metadata: Metadata = {
  title: 'AI 运行记录',
  description:
    '每一次 AI 操作的运行记录：步骤链、provider、token、延迟与成本，全部来自 agent_runs 与 llm_calls。',
};

/** `/app/ai-runs` — data comes from `GET /ai-runs` via React Query. */
export default function AiRunsPage() {
  return <AiRunsView />;
}
