import type { Metadata } from 'next';

import { JobsView } from '@/components/jobs/jobs-view';

export const metadata: Metadata = {
  title: 'JD Intelligence',
  description: '分析岗位描述：三层技能树、五维匹配拆解、缺口与待确认项，全部来自接口返回的依据。',
};

interface PageProps {
  /** `?job=<id>` opens a stored posting instead of an empty form. */
  searchParams: Promise<{ job?: string }>;
}

/**
 * `/app/jobs` — JD Intelligence (PRD FR-5).
 *
 * The page is dynamic because `?job=<id>` is part of its meaning: the id selects which stored
 * analysis, skill tree and match the three reads are scoped to. Reading it on the server keeps
 * `useSearchParams` and its Suspense boundary out of the client bundle entirely.
 */
export default async function JobsPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const jobId = typeof params.job === 'string' && params.job.trim() ? params.job.trim() : null;
  return <JobsView initialJobId={jobId} />;
}
