import { Badge } from '@careerforge/ui';
import type { Metadata } from 'next';

import { SiteHeader } from '@/components/landing/site-header';
import { SystemHealthGrid } from '@/components/system/system-health-grid';
import { API_BASE_URL } from '@/lib/api';

export const metadata: Metadata = {
  title: '系统状态',
  description: 'API / PostgreSQL / Redis / Vector store / LLM provider 的实时健康状态。',
};

/**
 * `/system` — public, read-only health page (docs/UI.md §5.17, API.md §2.13).
 * Version info (`/system/info`) and migration status arrive in a later phase; the page
 * states that instead of showing placeholder numbers.
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
              。接口不可达时，本页明确显示连接失败与 API 地址，不会伪造绿色状态。
            </p>
            <p className="text-tertiary font-mono text-[11px]">{API_BASE_URL}</p>
          </header>

          {/* The health card title renders as h3; this h2 keeps the outline h1 → h2 → h3. */}
          <h2 id="system-health-heading" className="sr-only">
            服务健康
          </h2>
          <SystemHealthGrid />

          <section className="border-default bg-surface flex flex-col gap-3 rounded-lg border p-4">
            <h2 className="text-primary text-sm font-medium">尚未接入</h2>
            <ul className="text-secondary flex flex-col gap-2 text-xs">
              <li className="flex items-center gap-2">
                <Badge variant="outline">PHASE 11</Badge>
                版本信息（app version / git sha / build time / Python / Node）—{' '}
                <span className="font-mono text-[11px]">GET /system/info</span>
              </li>
              <li className="flex items-center gap-2">
                <Badge variant="outline">PHASE 11</Badge>
                provider 配置（脱敏）与数据库迁移版本
              </li>
            </ul>
          </section>
        </div>
      </main>
    </>
  );
}
