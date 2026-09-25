'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle } from '@careerforge/ui';
import type { CacheStats, PromptVersion } from '@careerforge/shared';
import { Database, FileCode2 } from 'lucide-react';

import {
  cacheHitReading,
  formatBytes,
  formatCount,
  formatInstant,
  shortDigest,
} from '@/lib/observability-format';

interface CachePanelProps {
  stats: CacheStats | undefined;
}

/**
 * The cache gauge (docs/UI.md §5.15).
 *
 * Two readings, kept apart on purpose — the same distinction the API makes: the **table** answers
 * "has this deployment ever served a cached answer" and survives a restart, the **process** answers
 * "is the cache working right now" and resets with the server. Blending them would produce a hit
 * rate that describes neither, so both are printed with their own denominator.
 *
 * `hitRate: null` renders as "尚未服务" rather than 0%: a cache that has not been consulted has no
 * hit rate, and drawing an empty gauge would report a failure that has not happened.
 */
export function CachePanel({ stats }: CachePanelProps) {
  const reading = cacheHitReading(stats);
  const kinds = stats?.byKind ?? [];

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <Database className="size-3.5" aria-hidden="true" />
          缓存命中率
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline gap-2">
            <span className="text-primary font-mono text-xl tabular-nums">
              {reading.rate === null ? '尚未服务' : `${(reading.rate * 100).toFixed(1)}%`}
            </span>
            <span className="text-tertiary font-mono text-[11px]">{reading.label}</span>
          </div>
          <span
            className="border-subtle bg-elevated relative block h-2 w-full overflow-hidden rounded-sm border"
            role="img"
            aria-label={reading.label}
          >
            <span
              className="bg-signal absolute inset-y-0 left-0"
              style={{ width: `${Math.round((reading.rate ?? 0) * 100)}%` }}
              data-hit-rate={reading.rate === null ? 'null' : reading.rate.toFixed(4)}
            />
          </span>
          <p className="text-tertiary text-[11px] leading-relaxed">
            进程计数自服务启动起累计；下表的条目与命中数来自 ai_caches 表，跨重启保留。 零 Key
            的启发式路径不写缓存（没有可复用的模型响应），因此它是 0，而不是「命中率低」。
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <caption className="sr-only">按类型分组的缓存条目、命中次数与占用体积</caption>
            <thead className="text-tertiary">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">
                  类型
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  条目
                </th>
                <th scope="col" className="py-1 pr-3 font-medium">
                  命中
                </th>
                <th scope="col" className="py-1 font-medium">
                  占用
                </th>
              </tr>
            </thead>
            <tbody>
              {kinds.map((kind) => (
                <tr key={kind.kind} className="border-subtle border-t" data-cache-kind={kind.kind}>
                  <td className="text-primary py-1.5 pr-3 font-mono">{kind.kind}</td>
                  <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                    {formatCount(kind.entries)}
                  </td>
                  <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                    {formatCount(kind.hits)}
                  </td>
                  <td className="text-secondary py-1.5 font-mono tabular-nums">
                    {formatBytes(kind.bytes)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/*
          `stats === undefined` means the read failed, not that the cache served nothing: printing
          `0` here would report a measurement nobody made. An absent counter is an em dash.
        */}
        <p className="text-tertiary text-[11px]" data-cache-footer>
          {stats
            ? `表中累计命中 ${formatCount(stats.persistedHits ?? null)} 次；本次进程已落盘 ${formatCount(stats.process.eventsFlushed ?? null)} 条缓存事件。`
            : '缓存统计没有取到（GET /cache/stats 失败）—— 这里不显示任何替代数字。'}
        </p>
      </CardContent>
    </Card>
  );
}

interface PromptPanelProps {
  prompts: PromptVersion[];
}

/**
 * The prompt registry: which version is active, and what its body hashes to.
 *
 * It is on this page because of the third exit criterion of PHASE 11 — a run says *which prompt
 * produced it*, and that claim is only checkable if the versions and their digests are visible
 * somewhere. Only the active version's digest is shown in full; the table is about attribution, not
 * about diffing prompt bodies (the bodies live in `apps/api/src/careerforge_api/prompts/`).
 */
export function PromptPanel({ prompts }: PromptPanelProps) {
  const active = prompts.filter((prompt) => prompt.isActive).length;

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-1.5">
          <FileCode2 className="size-3.5" aria-hidden="true" />
          提示词注册表
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-tertiary text-[11px] leading-relaxed">
          共 {prompts.length} 个提示词，其中 {active}{' '}
          个为当前版本。改一次提示词正文会写入新版本号并保留 旧版本 ——
          运行记录因此能指回产生它的那一版，而不是「最后一次编辑」。
        </p>
        {prompts.length === 0 ? (
          <p className="text-secondary text-xs">注册表为空：还没有任何提示词被同步到数据库。</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <caption className="sr-only">提示词版本、摘要与更新时间</caption>
              <thead className="text-tertiary">
                <tr>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    名称
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    版本
                  </th>
                  <th scope="col" className="py-1 pr-3 font-medium">
                    SHA-256
                  </th>
                  <th scope="col" className="py-1 font-medium">
                    更新时间 (UTC)
                  </th>
                </tr>
              </thead>
              <tbody>
                {prompts.map((prompt) => (
                  <tr
                    key={`${prompt.name}-${prompt.version}`}
                    className="border-subtle border-t"
                    data-prompt={prompt.name}
                  >
                    <td className="text-primary py-1.5 pr-3 font-mono">
                      <span className="flex items-center gap-1.5">
                        {prompt.name}
                        {prompt.isActive ? <Badge variant="supported">当前</Badge> : null}
                      </span>
                    </td>
                    <td className="text-secondary py-1.5 pr-3 font-mono tabular-nums">
                      v{prompt.version}
                    </td>
                    <td className="text-tertiary py-1.5 pr-3 font-mono">
                      {shortDigest(prompt.sha256)}
                    </td>
                    <td className="text-tertiary py-1.5 font-mono tabular-nums">
                      {formatInstant(prompt.updatedAt)}
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
