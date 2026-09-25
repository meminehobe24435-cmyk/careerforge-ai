import type { Metadata } from 'next';
import { Suspense } from 'react';

import { Skeleton } from '@careerforge/ui';

import { EvidenceGraphView } from '@/components/graph/evidence-graph-view';

export const metadata: Metadata = {
  title: 'Career Evidence Graph',
  description:
    'Explore how skills, projects, repositories, documents and claims are connected — and open the evidence behind every confidence.',
};

/**
 * `/app/evidence-graph` (PRD FR-6).
 *
 * The view reads the query string (`?skill=` / `?node=` / `?focus=` / `?depth=` / `?hide=`), which
 * makes it a client-side read of the URL — so it is wrapped in a Suspense boundary, which is what
 * Next requires before a statically rendered page may call `useSearchParams`.
 */
export default function EvidenceGraphPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <EvidenceGraphView />
    </Suspense>
  );
}
