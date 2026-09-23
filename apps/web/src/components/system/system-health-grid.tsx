'use client';

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CodeBlock,
  ErrorState,
  Separator,
  Skeleton,
} from '@careerforge/ui';
import type { ServiceHealthStatus } from '@careerforge/shared';
import { isApiError, toServiceHealthStatus } from '@careerforge/shared';
import { Check, CircleDot, RefreshCw, TriangleAlert, X } from 'lucide-react';

import { useSystemHealth } from '@/hooks/use-system-health';
import { API_BASE_URL } from '@/lib/api';
import { cn, formatLatency, formatRelativeTime } from '@/lib/utils';

/* ------------------------------------------------------------------ *
 * Normalisation
 * docs/API.md §2.13 does NOT freeze the /system/health body, so the raw payload is
 * accepted in several shapes and anything unrecognised is shown verbatim instead of
 * being guessed at.
 * ------------------------------------------------------------------ */

interface HealthRow {
  key: string;
  label: string;
  status: ServiceHealthStatus;
  detail?: string;
  latencyMs?: number;
  version?: string;
}

const EXPECTED_SERVICES: { key: string; label: string; aliases: string[] }[] = [
  { key: 'api', label: 'API', aliases: ['api', 'fastapi', 'http', 'backend', 'server'] },
  {
    key: 'postgres',
    label: 'PostgreSQL',
    aliases: ['postgres', 'postgresql', 'database', 'db', 'pg'],
  },
  { key: 'redis', label: 'Redis', aliases: ['redis', 'cache', 'queue', 'broker'] },
  {
    key: 'vector',
    label: 'Vector store',
    aliases: ['vector', 'vectorstore', 'pgvector', 'embeddings', 'index'],
  },
  {
    key: 'llm',
    label: 'LLM provider',
    aliases: ['llm', 'llmprovider', 'provider', 'model', 'openai', 'deepseek'],
  },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function pickString(record: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'string' && value) return value;
  }
  return undefined;
}

function pickNumber(record: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === 'number' && Number.isFinite(value)) return value;
  }
  return undefined;
}

function slug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '');
}

function collectEntries(payload: unknown): { name: string; value: unknown }[] {
  if (!isRecord(payload)) return [];
  for (const key of ['services', 'checks', 'components', 'dependencies']) {
    const candidate = payload[key];
    if (Array.isArray(candidate)) {
      return candidate.flatMap<{ name: string; value: unknown }>((entry, index) => {
        if (isRecord(entry)) {
          const name =
            pickString(entry, ['name', 'service', 'key', 'id', 'component']) ??
            `service_${index + 1}`;
          return [{ name, value: entry }];
        }
        return typeof entry === 'string' ? [{ name: entry, value: entry }] : [];
      });
    }
    if (isRecord(candidate)) {
      return Object.entries(candidate).map(([name, value]) => ({ name, value }));
    }
  }
  return [];
}

function toRow(entry: { name: string; value: unknown }): HealthRow {
  if (typeof entry.value === 'string') {
    return { key: slug(entry.name), label: entry.name, status: toServiceHealthStatus(entry.value) };
  }
  if (!isRecord(entry.value)) {
    return { key: slug(entry.name), label: entry.name, status: 'unknown' };
  }

  const record = entry.value;
  const healthyFlag = record['healthy'];
  const status =
    typeof healthyFlag === 'boolean'
      ? healthyFlag
        ? 'ok'
        : 'down'
      : toServiceHealthStatus(pickString(record, ['status', 'state', 'result']));

  const row: HealthRow = {
    key: slug(entry.name),
    label: pickString(record, ['label', 'displayName', 'name']) ?? entry.name,
    status,
  };
  const detail = pickString(record, ['detail', 'message', 'error', 'description']);
  if (detail) row.detail = detail;
  const latency = pickNumber(record, ['latencyMs', 'latency_ms', 'tookMs', 'took_ms']);
  if (latency !== undefined) row.latencyMs = latency;
  const version = pickString(record, ['version']);
  if (version) row.version = version;
  return row;
}

interface NormalisedHealth {
  rows: HealthRow[];
  overall: ServiceHealthStatus;
  /** `true` when the payload carried no per-service detail at all. */
  missingDetail: boolean;
  reportedServices: number;
}

function normalise(payload: unknown): NormalisedHealth {
  const entries = collectEntries(payload);
  const overall = isRecord(payload)
    ? toServiceHealthStatus(pickString(payload, ['status', 'state']))
    : 'unknown';

  const rows: HealthRow[] = EXPECTED_SERVICES.map((expected) => {
    const match = entries.find((entry) =>
      expected.aliases.some((alias) => slug(entry.name).includes(alias)),
    );
    if (match) return toRow(match);
    return {
      key: expected.key,
      label: expected.label,
      status: 'unknown',
      detail: '接口未报告该服务的状态',
    };
  });

  const claimed = new Set(
    EXPECTED_SERVICES.flatMap((expected) => expected.aliases.map((alias) => slug(alias))),
  );
  for (const entry of entries) {
    const key = slug(entry.name);
    if ([...claimed].some((alias) => key.includes(alias))) continue;
    rows.push(toRow(entry));
  }

  return {
    rows,
    overall,
    missingDetail: entries.length === 0,
    reportedServices: entries.filter((entry) =>
      EXPECTED_SERVICES.some((expected) =>
        expected.aliases.some((alias) => slug(entry.name).includes(alias)),
      ),
    ).length,
  };
}

/* ------------------------------------------------------------------ *
 * Presentation
 * ------------------------------------------------------------------ */

const STATUS_STYLES: Record<
  ServiceHealthStatus,
  { label: string; variant: 'supported' | 'weak' | 'danger' | 'outline'; icon: typeof Check }
> = {
  ok: { label: 'ok', variant: 'supported', icon: Check },
  degraded: { label: 'degraded', variant: 'weak', icon: TriangleAlert },
  down: { label: 'down', variant: 'danger', icon: X },
  unknown: { label: 'unknown', variant: 'outline', icon: CircleDot },
};

function StatusCell({ status }: { status: ServiceHealthStatus }) {
  const style = STATUS_STYLES[status];
  const Icon = style.icon;
  return (
    <Badge variant={style.variant} announce className="gap-1.5">
      <Icon className="size-3" aria-hidden="true" />
      {style.label}
    </Badge>
  );
}

function HealthSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-4 w-40" />
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="flex items-center gap-3">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-3 w-20" />
            <Skeleton className="ml-auto h-3 w-24" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

/** Service health grid for `/system` — skeleton / error / honest-unknown states. */
export function SystemHealthGrid() {
  const { data, error, isPending, isError, isFetching, refetch } = useSystemHealth();

  if (isPending) return <HealthSkeleton />;

  if (isError) {
    const apiError = isApiError(error) ? error : null;
    return (
      <ErrorState
        title={apiError?.isNetworkError ? 'Backend not reachable' : '健康检查失败'}
        error={error}
        code={apiError?.code ?? 'UNKNOWN'}
        requestId={apiError?.requestId ?? null}
        onRetry={() => void refetch()}
        retrying={isFetching}
        details={
          <div className="flex flex-col gap-2">
            <CodeBlock filename="API base URL" code={API_BASE_URL} language="txt" maxHeight={64} />
            <p className="text-tertiary text-xs">
              健康检查是只读的公开端点：
              <span className="font-mono text-[11px]">GET /system/health</span>。
            </p>
          </div>
        }
      />
    );
  }

  const normalised = normalise(data);
  const payload = JSON.stringify(data, null, 2);

  return (
    <div className="flex flex-col gap-4">
      <Card className="min-w-0">
        <CardHeader className="flex-row items-center justify-between gap-3">
          <CardTitle>服务健康</CardTitle>
          <div className="flex items-center gap-2">
            <StatusCell status={normalised.overall} />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void refetch()}
              loading={isFetching}
              aria-label="重新检查服务健康"
            >
              <RefreshCw className="size-3.5" aria-hidden="true" />
              重新检查
            </Button>
          </div>
        </CardHeader>
        <CardContent className="px-0 pb-0 sm:px-0 sm:pb-0">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <caption className="sr-only">服务健康状态列表</caption>
              <thead>
                <tr className="border-subtle bg-surface border-y">
                  <th scope="col" className="text-tertiary px-4 py-2 text-[11px] font-medium">
                    Service
                  </th>
                  <th scope="col" className="text-tertiary px-4 py-2 text-[11px] font-medium">
                    Status
                  </th>
                  <th scope="col" className="text-tertiary px-4 py-2 text-[11px] font-medium">
                    Latency
                  </th>
                  <th scope="col" className="text-tertiary px-4 py-2 text-[11px] font-medium">
                    Detail
                  </th>
                </tr>
              </thead>
              <tbody>
                {normalised.rows.map((row) => (
                  <tr key={row.key} className="border-subtle border-b last:border-b-0">
                    <th
                      scope="row"
                      className="text-primary px-4 py-2 align-top text-xs font-medium"
                    >
                      {row.label}
                      {row.version ? (
                        <span className="text-tertiary ml-2 font-mono text-[11px]">
                          v{row.version}
                        </span>
                      ) : null}
                    </th>
                    <td className="px-4 py-2 align-top">
                      <StatusCell status={row.status} />
                    </td>
                    <td
                      className={cn(
                        'px-4 py-2 align-top font-mono text-xs tabular-nums',
                        'text-secondary',
                      )}
                    >
                      {formatLatency(row.latencyMs)}
                    </td>
                    <td className="text-secondary max-w-80 px-4 py-2 align-top text-xs">
                      {row.detail ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {normalised.missingDetail ? (
        <div className="border-weak/30 bg-surface flex flex-col gap-3 rounded-lg border p-4">
          <p className="text-weak text-sm font-medium">响应未包含分服务明细</p>
          <p className="text-secondary text-xs leading-relaxed">
            接口返回了可解析的信封，但没有 <span className="font-mono text-[11px]">services</span> /{' '}
            <span className="font-mono text-[11px]">checks</span> 字段，因此五行状态保持为 unknown。
            下面是原始响应，不做任何推测。
          </p>
          <CodeBlock filename="GET /system/health" code={payload} language="json" maxHeight={260} />
        </div>
      ) : null}

      <div className="text-tertiary flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px]">
        <span>
          services reported: {normalised.reportedServices}/{EXPECTED_SERVICES.length}
        </span>
        <Separator orientation="vertical" className="h-3" />
        <span>checked: {formatRelativeTime(readCheckedAt(data))}</span>
        <Separator orientation="vertical" className="h-3" />
        <span>GET /system/health</span>
      </div>
    </div>
  );
}

function readCheckedAt(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  const value = payload['checkedAt'] ?? payload['checked_at'] ?? payload['timestamp'];
  return typeof value === 'string' ? value : null;
}
