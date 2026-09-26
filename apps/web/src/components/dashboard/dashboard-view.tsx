'use client';

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CodeBlock,
  EmptyState,
  ErrorState,
  Separator,
} from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';
import type { DashboardResponse, DashboardStats } from '@careerforge/shared';
import { Inbox, Network, RefreshCw, ShieldAlert, Sparkles, Target } from 'lucide-react';
import Link from 'next/link';

import { DashboardSkeleton } from '@/components/dashboard/dashboard-skeleton';
import { ProfileStrengthRing } from '@/components/dashboard/profile-strength-ring';
import { RecentJobsTable } from '@/components/dashboard/recent-jobs-table';
import { StatCard } from '@/components/dashboard/stat-card';
import { useDashboard } from '@/hooks/use-dashboard';
import { useSession } from '@/hooks/use-session';
import { API_BASE_URL } from '@/lib/api';
import { formatDateTime } from '@/lib/utils';

interface StatDefinition {
  key: keyof DashboardStats;
  label: string;
  kind: 'fraction' | 'count';
  definition: string;
}

/** The six cards fixed by docs/UI.md §5.3, with the metric definition (`口径`). */
const STAT_DEFINITIONS: StatDefinition[] = [
  {
    key: 'evidenceCoverage',
    label: 'Evidence Coverage',
    kind: 'fraction',
    definition: '已具备证据的技能占全部已声明技能的比例（至少 1 条独立证据才算覆盖）。',
  },
  {
    key: 'skillCoverage',
    label: 'Skill Coverage',
    kind: 'fraction',
    definition: '目标岗位要求技能中，你已具备的比例（required + preferred 加权）。',
  },
  {
    key: 'resumeMatch',
    label: 'Resume Match',
    kind: 'fraction',
    definition: '当前简历与目标岗位的匹配度，取自确定性评分算法 match@1.0.0。',
  },
  {
    key: 'applications',
    label: 'Applications',
    kind: 'count',
    definition: '投递看板中未归档的卡片总数（含 wishlist：想看但还没投的也算在跟）。',
  },
  {
    key: 'interviews',
    label: 'Interviews',
    kind: 'count',
    // The API ships this definition with the number; this copy is the fallback for a backend
    // that omits `meta.definitions`, and it says "snapshot" because a reader who assumed the
    // funnel meaning would read the number as wrong the first time a rejection appeared.
    definition: '当前处于面试阶段的卡片数（interview + final + offer）——看板快照，不是漏斗口径。',
  },
  {
    key: 'offers',
    label: 'Offers',
    kind: 'count',
    definition: '当前状态为 offer 的卡片数。',
  },
];

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return '凌晨好';
  if (hour < 12) return '早上好';
  if (hour < 18) return '下午好';
  return '晚上好';
}

/**
 * Dashboard shell (docs/UI.md §5.3).
 *
 * Three explicit states:
 *  - loading → layout-shaped skeleton;
 *  - error → ErrorState (code + copyable requestId + retry), with a dedicated
 *    "backend not reachable" panel that prints the configured API base URL;
 *  - empty → EmptyState (no fabricated zeros, no fake trend lines).
 */
export function DashboardView() {
  const { session } = useSession();
  const query = useDashboard();
  const { error, isPending, isError, isFetching } = query;

  if (isPending) {
    return <DashboardSkeleton />;
  }

  if (isError) {
    const apiError = isApiError(error) ? error : null;
    const unreachable = apiError?.isNetworkError ?? false;

    return (
      <div className="flex flex-col gap-5">
        <div className="flex flex-col gap-1">
          <h1 className="text-primary text-lg font-semibold tracking-tight">总览</h1>
          <p className="text-tertiary font-mono text-[11px]">GET {API_BASE_URL}/dashboard</p>
        </div>

        <ErrorState
          title={unreachable ? 'Backend not reachable' : 'Dashboard 加载失败'}
          error={error}
          code={apiError?.code ?? 'UNKNOWN'}
          requestId={apiError?.requestId ?? null}
          onRetry={() => void query.refetch()}
          retrying={isFetching}
          statusHref="/system"
          details={
            <div className="flex flex-col gap-2">
              <p className="text-secondary text-xs leading-relaxed">
                {unreachable
                  ? '前端已按 docs/API.md 请求接口，但没有拿到任何响应。这里不会显示任何猜测的数据 —— 请先启动 API 服务后重试。'
                  : '请求已到达服务端，但响应不是合法的接口信封（{ success, data, error, requestId }）。'}
              </p>
              <CodeBlock
                filename="API base URL"
                code={API_BASE_URL}
                language="txt"
                maxHeight={64}
              />
              <p className="text-tertiary text-xs leading-relaxed">
                启动后端：<span className="font-mono text-[11px]">pnpm --filter api dev</span>
                （或 <span className="font-mono text-[11px]">docker compose up api</span>），
                然后点击「重试」。
              </p>
            </div>
          }
        />
      </div>
    );
  }

  // A fresh nullable binding keeps the "empty payload" branch type-safe instead of relying
  // on narrowing a TanStack Query union (which collapses to `never` in the last branch).
  const data: DashboardResponse | null = query.data ?? null;

  if (!data) {
    return (
      <EmptyState
        icon={<Inbox className="size-5" />}
        title="接口返回了空数据"
        description="后端返回 success 但没有 data。请检查 /dashboard 的实现是否遵循 docs/API.md §2.10。"
        action={
          <Button variant="secondary" onClick={() => void query.refetch()} loading={isFetching}>
            <RefreshCw className="size-3.5" aria-hidden="true" />
            重试
          </Button>
        }
      />
    );
  }

  const { stats, profileStrength, recentJobs, nextActions, meta } = data;
  const allZero =
    stats.evidenceCoverage === 0 &&
    stats.skillCoverage === 0 &&
    stats.resumeMatch === 0 &&
    stats.applications === 0 &&
    stats.interviews === 0 &&
    stats.offers === 0;

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <h1 className="text-primary text-lg font-semibold tracking-tight">
            {greeting()}
            {session?.user.displayName ? `，${session.user.displayName}` : ''}
          </h1>
          <p className="text-tertiary font-mono text-[11px]">
            GET {API_BASE_URL}/dashboard
            {typeof meta?.tookMs === 'number' ? ` · ${meta.tookMs}ms` : ''}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {session?.user.isDemo ? <Badge variant="signal">demo account</Badge> : null}
          {meta?.cacheHit ? <Badge variant="outline">cached · 0 成本</Badge> : null}
          {meta?.cacheHit === false ? <Badge variant="outline">live</Badge> : null}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void query.refetch()}
            loading={isFetching}
            aria-label="刷新 Dashboard 数据"
          >
            <RefreshCw className="size-3.5" aria-hidden="true" />
            刷新
          </Button>
        </div>
      </header>

      {/*
        The two things this product is for, above the fold and above the numbers. A dashboard whose
        primary action is "refresh" is a report; this one has to lead somewhere, and the somewhere is
        analyse a job (which fills the graph) or go look at the evidence you already have.
      */}
      <nav aria-label="主要操作" className="flex flex-wrap items-center gap-2">
        <Button asChild>
          <Link href="/app/jobs?focus=input">
            <Target className="size-3.5" aria-hidden="true" />
            分析一个岗位
          </Link>
        </Button>
        <Button variant="secondary" asChild>
          <Link href="/app/evidence-graph">
            <Network className="size-3.5" aria-hidden="true" />
            查看证据图谱
          </Link>
        </Button>
        <span className="text-tertiary text-[11px]">
          匹配分、面试题与简历改写都建立在这张证据图谱之上
        </span>
      </nav>

      {allZero ? (
        <EmptyState
          icon={<Sparkles className="size-5" />}
          title="这个账号还没有任何数据"
          description="Demo 账号（demo@careerforge.ai）预置了完整候选人数据。新账号目前没有「一键载入示例数据」——材料要通过 POST /profile/import 导入，与其放一个按不动的按钮，不如把这件事说清楚。"
          hint="GET /dashboard → stats 全为 0"
        />
      ) : null}

      <section aria-labelledby="dash-strength-heading" className="flex flex-col gap-4">
        {/* Card titles render as h3; this h2 keeps the outline h1 → h2 → h3 (docs/UI.md §9). */}
        <h2 id="dash-strength-heading" className="sr-only">
          Profile Strength 与核心指标
        </h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
          <Card className="min-w-0">
            <CardHeader>
              <CardTitle>Profile Strength</CardTitle>
            </CardHeader>
            <CardContent>
              <ProfileStrengthRing
                score={profileStrength.score}
                delta7d={profileStrength.delta7d ?? null}
                dimensions={profileStrength.dimensions ?? null}
                algorithmVersion={profileStrength.algorithmVersion ?? null}
              />
            </CardContent>
          </Card>

          {/*
            Three columns, not six, and the label wraps instead of being clipped.

            Measured at 1440px: the six-across grid left ~116px per card, of which the label had
            ~84px after padding — five of the six metric names were cut to `EVIDEN…`, `RESUME…`.
            A truncated metric name is a card that cannot say what it measures, so the count came
            down (3 × 2) rather than the type size. At `lg` the right-hand column is beside a 300px
            ring card and only fits two; below `lg` the grid is full width.
          */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3">
            {STAT_DEFINITIONS.map((definition) => (
              <StatCard
                key={definition.key}
                label={definition.label}
                value={stats[definition.key]}
                kind={definition.kind}
                // The API ships the definition it actually computed with; the local copy is
                // only the fallback, so the label and the arithmetic cannot drift apart.
                definition={meta?.definitions?.[definition.key] ?? definition.definition}
                unavailable={meta?.unavailable?.[definition.key] ?? null}
              />
            ))}
          </div>
        </div>
      </section>

      <section
        aria-labelledby="dash-jobs-heading"
        className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,320px)]"
      >
        <h2 id="dash-jobs-heading" className="sr-only">
          最近岗位与下一步行动
        </h2>
        <RecentJobsTable jobs={recentJobs} />

        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>下一步行动</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {nextActions.length === 0 ? (
              <p className="text-secondary text-xs">没有待办事项。</p>
            ) : (
              nextActions.map((action) => (
                <div key={`${action.type}-${action.at}`} className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <Badge variant="weak">{action.type}</Badge>
                    <span className="text-primary truncate text-xs">{action.title}</span>
                  </div>
                  <span className="text-tertiary font-mono text-[11px] tabular-nums">
                    {formatDateTime(action.at)}
                  </span>
                  <Separator className="mt-2" />
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </section>

      {/*
        What this page does *not* show, and where it actually is.

        Until PHASE 14 these three slots were skeleton cards captioned 「尚未接入的面板」 with notes
        naming internal phases — two of them saying that `/analytics/timeline` and `/analytics/funnel`
        were needed, while both endpoints existed and `/app/analytics` charts them. A dashboard that
        tells a visitor the product is missing something it ships is worse than one that says nothing,
        so the slots now name the real destination and link to it. The one panel that genuinely has no
        chart anywhere is named as such instead of rendered as a fake skeleton.
      */}
      <section aria-labelledby="dash-more-heading" className="flex flex-col gap-3">
        <h2 id="dash-more-heading" className="text-primary text-sm font-medium">
          更深入的分析
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {[
            { title: '投递漏斗', where: '/app/analytics', detail: '到达过每一阶段的岗位数' },
            {
              title: '时间趋势与里程碑',
              where: '/app/analytics',
              detail: '按月投递 / 面试 / Offer',
            },
            {
              title: '技能与面试成功率',
              where: '/app/analytics',
              detail: '两组的 Wilson 区间对照',
            },
          ].map((panel) => (
            <Card key={panel.title} className="min-w-0">
              <CardContent className="flex flex-col gap-1.5 pt-4">
                <Link
                  href={panel.where}
                  className="text-primary text-xs font-medium hover:underline"
                >
                  {panel.title} →
                </Link>
                <p className="text-tertiary text-[11px] leading-relaxed">{panel.detail}</p>
              </CardContent>
            </Card>
          ))}
        </div>
        <p className="text-tertiary text-[11px] leading-relaxed">
          技能雷达图（`GET /dashboard` 已返回 `skillsRadar`）目前没有图表组件，因此本页不画它——
          用占位图冒充一张雷达图会让读者以为看到了数据。
        </p>
      </section>

      <p className="text-tertiary flex items-center gap-2 font-mono text-[11px]">
        <ShieldAlert className="size-3.5" aria-hidden="true" />
        本页所有数字均直接来自 GET /dashboard；接口不可用时不会显示任何替代数据。
      </p>
    </div>
  );
}
