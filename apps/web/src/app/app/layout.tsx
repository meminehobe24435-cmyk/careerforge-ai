import type { ReactNode } from 'react';

import { AppShell } from '@/components/app-shell/app-shell';

export const metadata = {
  title: '工作台',
};

/**
 * `/app` layout: the authenticated shell (sidebar + top bar + command palette).
 * The client-side auth guard lives inside `AppShell` so every nested route is protected
 * by construction.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
