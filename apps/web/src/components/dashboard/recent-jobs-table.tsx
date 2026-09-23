import { Badge, Card, CardContent, CardHeader, CardTitle, EmptyState } from '@careerforge/ui';
import type { DashboardRecentJob } from '@careerforge/shared';
import { Inbox } from 'lucide-react';

import { formatScore } from '@/lib/utils';

const STATUS_VARIANT: Record<string, 'default' | 'supported' | 'weak' | 'danger' | 'signal'> = {
  wishlist: 'default',
  applied: 'signal',
  oa: 'signal',
  interview: 'weak',
  final: 'weak',
  offer: 'supported',
  rejected: 'danger',
};

/** Recent jobs table from `GET /dashboard` → `recentJobs` (docs/API.md §2.10). */
export function RecentJobsTable({ jobs }: { jobs: DashboardRecentJob[] }) {
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>最近岗位</CardTitle>
      </CardHeader>
      <CardContent className="px-0 pb-0 sm:px-0 sm:pb-0">
        {jobs.length === 0 ? (
          <div className="px-4 pb-4 sm:px-5 sm:pb-5">
            <EmptyState
              icon={<Inbox className="size-5" />}
              title="还没有岗位数据"
              description="分析一份 JD 之后，匹配结果会出现在这里。JD 分析入口在 PHASE 4 上线。"
              hint="GET /dashboard → recentJobs: []"
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="border-subtle bg-surface border-y">
                  <th scope="col" className="text-tertiary px-4 py-2 text-[11px] font-medium">
                    Company
                  </th>
                  <th scope="col" className="text-tertiary px-4 py-2 text-[11px] font-medium">
                    Role
                  </th>
                  <th scope="col" className="text-tertiary px-4 py-2 text-[11px] font-medium">
                    Match
                  </th>
                  <th scope="col" className="text-tertiary px-4 py-2 text-[11px] font-medium">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.jobId} className="border-subtle border-b last:border-b-0">
                    <td className="text-primary px-4 py-2 text-xs">{job.company}</td>
                    <td className="text-secondary px-4 py-2 text-xs">{job.role}</td>
                    <td className="text-primary px-4 py-2 font-mono text-xs tabular-nums">
                      {formatScore(job.matchScore)}
                    </td>
                    <td className="px-4 py-2">
                      {/* TODO(phase-4): link each row to /app/jobs/[id]. */}
                      <Badge variant={STATUS_VARIANT[job.status] ?? 'default'}>{job.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
