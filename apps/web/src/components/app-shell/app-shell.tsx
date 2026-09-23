'use client';

import { Skeleton, Spinner } from '@careerforge/ui';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';

import { useSession } from '@/hooks/use-session';

import { CommandPalette } from './command-palette';
import { describeRoute } from './nav-config';
import { SidebarNav } from './sidebar-nav';
import { TopBar } from './top-bar';

/** Shell-shaped skeleton: heading, toolbar and a card grid, mirroring the real layout. */
function ShellSkeleton() {
  return (
    <div className="bg-base flex min-h-dvh" aria-busy="true" aria-live="polite">
      <div className="border-default bg-surface hidden h-dvh w-[var(--sidebar-width)] shrink-0 border-r lg:block" />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-default flex h-14 items-center gap-3 border-b px-4">
          <Skeleton className="h-4 w-40" />
          <div className="ml-auto flex items-center gap-2">
            <Skeleton className="size-8 rounded-full" />
            <Skeleton className="h-8 w-24" />
          </div>
        </div>
        <div className="flex flex-1 flex-col gap-4 p-4 sm:p-6">
          <Skeleton className="h-6 w-48" />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-24" />
            ))}
          </div>
          <Skeleton className="h-64" />
        </div>
      </div>
    </div>
  );
}

/**
 * Authenticated shell (docs/UI.md §3.2).
 *
 * The guard is client-side on purpose: the backend issues the token to the browser, so
 * the client owns the session. `ready` gates every render, which is what keeps the SSR
 * pass and the hydrated pass identical (no redirect races, no hydration mismatch).
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { ready, session } = useSession();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  // Ctrl/Cmd + K — available everywhere inside the shell.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Redirect only once the client session has actually been read.
  useEffect(() => {
    if (ready && !session) router.replace('/login');
  }, [ready, session, router]);

  const { title, crumbs } = describeRoute(pathname ?? '/app/dashboard');

  if (!ready) return <ShellSkeleton />;

  if (!session) {
    return (
      <div className="bg-base flex min-h-dvh items-center justify-center">
        <div className="flex flex-col items-center gap-3 text-center">
          <Spinner size="lg" className="text-brand" label="正在校验登录状态" />
          <p className="text-secondary text-xs">未检测到登录状态，正在跳转到登录页…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-base flex min-h-dvh">
      <SidebarNav mobileOpen={mobileNavOpen} onMobileOpenChange={setMobileNavOpen} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          title={title}
          crumbs={crumbs}
          user={session.user}
          onOpenNav={() => setMobileNavOpen(true)}
          onOpenPalette={() => setPaletteOpen(true)}
        />
        <main id="main" className="min-w-0 flex-1 px-4 py-5 sm:px-6 sm:py-6">
          {children}
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
    </div>
  );
}
