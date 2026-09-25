import { Badge } from '@careerforge/ui';
import type { Metadata } from 'next';

import { SiteHeader } from '@/components/landing/site-header';
import { BuildIdentityPanel } from '@/components/system/build-identity-panel';
import { QualitySnapshotPanel } from '@/components/system/quality-snapshot-panel';
import { SystemHealthGrid } from '@/components/system/system-health-grid';
import { API_BASE_URL } from '@/lib/api';

export const metadata: Metadata = {
  title: '系统状态',
  description: 'API / PostgreSQL / Redis / Vector store / LLM provider 的实时健康状态。',
};

/**
 * `/system` — public, read-only health page (docs/UI.md §5.17, API.md §2.13).
 *
 * Three sections, in the order a reader needs them: *is it up* (health grid), *which build is
 * answering* (build identity, `GET /system/version`), *what do the numbers say*
 * (evaluation snapshot). The last two are adjacent on purpose — a snapshot commit that is not the
 * running commit is a fact of the page, not a footnote.
 */
export default function SystemPage() {
  return (
    <>
      <SiteHeader />
      <main id="main" className="bg-grid">
        <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-10 sm:px-6 sm:py-14">
          <header className="flex flex-col gap-2">
            <h1 className="text-primary text-xl font-semibold tracking-tight sm:text-2xl">
              系统状态
            </h1>
            <p className="text-secondary max-w-2xl text-sm leading-relaxed">
              服务健康数据来自公开只读端点{' '}
              <span className="font-mono text-[11px]">GET /system/health</span>
              ，构建标识来自 <span className="font-mono text-[11px]">GET /system/version</span>
              。接口不可达时，本页明确显示连接失败与 API 地址，不会伪造绿色状态。
            </p>
            <p className="text-tertiary font-mono text-[11px]">{API_BASE_URL}</p>
          </header>

          {/* The health card title renders as h3; this h2 keeps the outline h1 → h2 → h3. */}
          <h2 id="system-health-heading" className="sr-only">
            服务健康
          </h2>
          <SystemHealthGrid />

          <h2 id="build-identity-heading" className="sr-only">
            构建标识
          </h2>
          <BuildIdentityPanel />

          {/* The health card title renders as h3, so the snapshot heading is an h2 too: the
              outline must not jump from h3 back to a sibling h2 without a section boundary. */}
          <h2 id="quality-snapshot-heading" className="sr-only">
            评测快照
          </h2>
          <QualitySnapshotPanel />

          <section className="border-default bg-surface flex flex-col gap-3 rounded-lg border p-4">
            <h2 className="text-primary text-sm font-medium">尚未接入</h2>
            <ul className="text-secondary flex flex-col gap-2 text-xs">
              <li className="flex items-center gap-2">
                <Badge variant="outline">PHASE 11</Badge>
                provider 配置（脱敏）、数据库迁移版本与队列后端 —{' '}
                <span className="font-mono text-[11px]">GET /system/info</span>
              </li>
            </ul>
            <p className="text-tertiary text-[11px] leading-relaxed">
              <span className="font-mono">/system/info</span> 会返回数据库 URL（SQLite
              下就是绝对路径），因此它不在这张公开页面上并排展示；
              页面只读取为此单独设计、不含主机名与路径的{' '}
              <span className="font-mono">/system/version</span>。
            </p>
          </section>
        </div>
      </main>
    </>
  );
}
