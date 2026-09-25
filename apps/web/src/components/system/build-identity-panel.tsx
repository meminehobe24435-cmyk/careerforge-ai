'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle, Skeleton } from '@careerforge/ui';
import { isApiError } from '@careerforge/shared';

import { useSystemVersion } from '@/hooks/use-system-version';
import { API_BASE_URL } from '@/lib/api';
import { qualitySnapshot } from '@/lib/quality-snapshot';

/**
 * Build identity — *which* build is answering, next to *which* commit the evaluation describes.
 *
 * Three rules, the same three the quality panel follows:
 *
 * 1. **Nothing is invented.** Every value comes from `GET /system/version`; a value the API did
 *    not report reads `unavailable` (or "未记录" for a build timestamp that no build stamped),
 *    never a plausible-looking placeholder and never `0`.
 * 2. **The two commits are not the same commit, and the panel says so.** `commit` is the process
 *    serving this request; `qualitySnapshot.commit` is the commit the evaluation numbers below it
 *    were measured on. Showing one and implying the other is exactly the kind of claim this
 *    project removed elsewhere, so they are printed side by side with the difference spelled out.
 * 3. **No host, no path.** The endpoint is deliberately narrower than `GET /system/info`, which
 *    reports the database URL (an absolute path on SQLite). This panel shows what it returns and
 *    adds nothing to it.
 */
export function BuildIdentityPanel() {
  const query = useSystemVersion();
  const data = query.data;
  const apiError = isApiError(query.error) ? query.error : null;

  const unavailable = 'unavailable';

  return (
    <Card className="min-w-0" data-testid="build-identity">
      <CardHeader className="flex-col items-start gap-1.5 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="flex items-center gap-2">
          构建标识
          <Badge variant="outline">Build identity</Badge>
        </CardTitle>
        <p className="text-tertiary font-mono text-[11px]">
          <span className="font-mono">GET /system/version</span>
        </p>
      </CardHeader>

      <CardContent className="flex flex-col gap-4">
        {query.isPending ? (
          <div className="flex flex-col gap-2" aria-busy="true">
            <Skeleton className="h-4 w-56" />
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-4 w-64" />
          </div>
        ) : null}

        {query.isError && !data ? (
          <p role="status" className="text-secondary text-xs leading-relaxed">
            版本接口不可达（
            <span className="font-mono">{API_BASE_URL}/system/version</span>
            {apiError?.status ? ` · HTTP ${apiError.status}` : ''}
            ）：下列字段显示为 <span className="font-mono">{unavailable}</span>
            ，而不是猜一个值。API 地址与错误码就是这里能给出的全部事实。
          </p>
        ) : null}

        {data ? (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <dl
                data-testid="build-identity-live"
                className="border-subtle bg-elevated flex flex-col gap-1.5 rounded-md border px-3 py-2.5"
              >
                <dt className="text-tertiary text-[11px] leading-snug">
                  运行中的 API（本次响应由它给出）
                </dt>
                <dd className="flex flex-col gap-1">
                  <Row label="version" value={data.version} testId="build-version" />
                  <Row
                    label="commit"
                    value={data.commitShort ?? unavailable}
                    title={data.commit ?? undefined}
                    testId="build-commit"
                  />
                  <Row label="environment" value={data.environment} testId="build-environment" />
                  <Row
                    label="buildTime"
                    value={data.buildTimestamp ?? '未记录（没有构建产物时不会伪造时间）'}
                    testId="build-timestamp"
                  />
                </dd>
              </dl>

              <dl
                data-testid="build-identity-snapshot"
                className="border-subtle bg-elevated flex flex-col gap-1.5 rounded-md border px-3 py-2.5"
              >
                <dt className="text-tertiary text-[11px] leading-snug">
                  评测快照（下面那张卡片里的数字所描述的提交）
                </dt>
                <dd className="flex flex-col gap-1">
                  <Row label="commit" value={qualitySnapshot.commit} testId="snapshot-commit" />
                  <Row label="generatedAt" value={qualitySnapshot.generatedAt} />
                  <Row label="provider" value={qualitySnapshot.provider} />
                  <Row
                    label="suites"
                    value={`${qualitySnapshot.suites} suites / ${qualitySnapshot.cases} cases`}
                    testId="snapshot-suites"
                  />
                </dd>
              </dl>
            </div>

            <p className="text-secondary text-xs leading-relaxed">
              两列
              <strong className="text-primary font-medium">不是同一个提交</strong>
              ：左列是刚刚回答这次请求的进程，右列是{' '}
              <span className="font-mono">reports/eval-report.json</span>{' '}
              产生时的工作副本。二者一致时说明页面与评测同源；不一致时说明评测早于（或晚于）当前
              部署，页面不会把它当成同一件事。
            </p>

            <div className="text-tertiary flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] tabular-nums">
              <span>python {data.pythonVersion}</span>
              <span>node {data.nodeVersion ?? unavailable}</span>
              <span>schema {data.schemaVersion}</span>
              <span>taxonomy {data.taxonomyVersion}</span>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Row({
  label,
  value,
  title,
  testId,
}: {
  label: string;
  value: string;
  title?: string;
  testId?: string;
}) {
  return (
    <span className="flex flex-wrap items-baseline gap-x-2 text-[11px] leading-snug">
      <span className="text-tertiary font-mono">{label}</span>
      <span className="text-primary break-all font-mono" data-testid={testId} title={title}>
        {value}
      </span>
    </span>
  );
}
