import { Button } from '@careerforge/ui';
import Link from 'next/link';

import { ThemeToggle } from '@/components/app-shell/theme-toggle';

/** Public header for marketing/system pages (no auth surface). */
export function SiteHeader() {
  return (
    <header className="border-subtle bg-base/85 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-6xl items-center gap-3 px-4 sm:px-6">
        <Link
          href="/"
          className="focus-visible:outline-brand flex items-center gap-2 rounded-sm outline-none focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <span
            aria-hidden="true"
            className="border-default bg-brand/10 text-brand flex size-7 items-center justify-center rounded-md border font-mono text-[10px] font-semibold"
          >
            CF
          </span>
          <span className="text-primary font-mono text-xs font-medium tracking-tight">
            CareerForge
          </span>
        </Link>

        <nav aria-label="主导航" className="ml-4 hidden items-center gap-4 sm:flex">
          <a
            href="#capabilities"
            className="text-secondary hover:text-primary focus-visible:outline-brand rounded-sm text-xs underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            能力
          </a>
          <Link
            href="/system"
            className="text-secondary hover:text-primary focus-visible:outline-brand rounded-sm text-xs underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            系统状态
          </Link>
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          <Button asChild size="sm" variant="secondary">
            <Link href="/login?demo=1">View Demo</Link>
          </Button>
          <Button asChild size="sm">
            <Link href="/login">Start Building</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
