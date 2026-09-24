import type { Metadata } from 'next';

import { PublicProfilePanel } from '@/components/settings/public-profile-panel';

export const metadata: Metadata = {
  title: '设置',
  description: '公开页与隐私：逐项可见性、分享链接，以及发布时被自动脱敏的内容。',
};

/**
 * `/app/settings` — currently the public-page panel only.
 *
 * The route is specified in `docs/UI.md` §4 as holding privacy, AI and public-page settings.
 * Only the privacy half exists so far, and the page says so rather than rendering three empty
 * cards; the AI and appearance sections arrive with the phases that own those settings.
 */
export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-primary text-lg font-semibold tracking-tight">设置</h1>
        <p className="text-tertiary text-xs leading-relaxed">
          当前只有「公开页与隐私」。AI 与外观设置随对应阶段加入。
        </p>
      </header>
      <PublicProfilePanel />
    </div>
  );
}
