import { Badge, Card, CardContent, CardHeader, CardTitle, EmptyState } from '@careerforge/ui';
import type { DashboardRecentJob } from '@careerforge/shared';
import { Inbox } from 'lucide-react';

// `formatInstant`, not the local-time `formatDateTime`: `jobs.created_at` is naive UTC, and
// `new Date('2026-09-26T02:12:51')` in a UTC+8 browser reads it as 02:12 *local* — eight hours of
// drift on a column whose whole job is to say how recent the posting is. It renders the UTC clock,
// which is why the header says so.
import { formatInstant } from '@/lib/observability-format';
import { EMPTY_VALUE, formatScore } from '@/lib/utils';

const STATUS_VARIANT: Record<string, 'default' | 'supported' | 'weak' | 'danger' | 'signal'> = {
  wishlist: 'default',
  applied: 'signal',
  oa: 'signal',
  interview: 'weak',
  final: 'weak',
  offer: 'supported',
  rejected: 'danger',
};

/**
 * Recent jobs from `GET /dashboard` → `recentJobs` (docs/API.md §2.10).
 *
 * Two layouts, the same five facts, and the breakpoint is `sm` for a measured reason. At 375px a
 * four-column table left the role ~90px wide, and a Chinese role name has no spaces to break on:
 * 嵌入式软件工程师（电机控制方向） wrapped **character by character onto four lines** while the match
 * score beside it stayed on one, which reads as a rendering fault rather than as a layout. So below
 * `sm` the row becomes a card — role on its own line, company · match · status beneath it, date
 * last — and from `sm` up the table is kept, because at 640px the four columns genuinely fit.
 */
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
              description="分析一份 JD 之后，匹配结果会出现在这里。"
              hint="GET /dashboard → recentJobs: []"
            />
          </div>
        ) : (
          <>
            <RecentJobsCards jobs={jobs} />
            <RecentJobsTableDesktop jobs={jobs} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

/**
 * Below `sm`: one card per job.
 *
 * The role is a normal-flow line rather than a table cell, so it wraps where the browser chooses
 * instead of being squeezed into a column narrower than one character.
 */
function RecentJobsCards({ jobs }: { jobs: DashboardRecentJob[] }) {
  return (
    <ul className="flex flex-col gap-2 px-4 pb-4 sm:hidden" data-recent-job-list>
      {jobs.map((job) => (
        <li
          key={job.jobId}
          data-recent-job={job.jobId}
          className="border-subtle bg-elevated flex flex-col gap-1.5 rounded-sm border p-2.5"
        >
          <p className="text-primary text-sm leading-snug">{job.role}</p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
            <span className="text-secondary">{job.company || EMPTY_VALUE}</span>
            <span className="text-primary font-mono tabular-nums">
              {formatScore(job.matchScore)}
            </span>
            {/* TODO(phase-4): link each row to /app/jobs/[id]. */}
            <Badge variant={STATUS_VARIANT[job.status] ?? 'default'}>{job.status}</Badge>
          </div>
          <span className="text-tertiary font-mono text-[10px] tabular-nums">
            {formatInstant(job.createdAt ?? null)}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** From `sm` up: the four-column table, which is the layout the columns belong to. */
function RecentJobsTableDesktop({ jobs }: { jobs: DashboardRecentJob[] }) {
  return (
    <div className="hidden overflow-x-auto sm:block">
      <table className="w-full border-collapse text-left text-sm" data-recent-jobs-table>
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
            <th scope="col" className="text-tertiary px-4 py-2 text-[11px] font-medium">
              时间 (UTC)
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
              <td className="text-tertiary px-4 py-2 font-mono text-xs tabular-nums">
                {formatInstant(job.createdAt ?? null)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
