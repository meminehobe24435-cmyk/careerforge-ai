import { Button, EmptyState } from '@careerforge/ui';
import { Compass } from 'lucide-react';
import Link from 'next/link';

export default function NotFound() {
  return (
    <main id="main" className="mx-auto flex min-h-dvh w-full max-w-2xl items-center px-4 sm:px-6">
      <div className="w-full">
        <p className="text-tertiary mb-4 font-mono text-[11px] uppercase tracking-[0.18em]">
          404 · NOT_FOUND
        </p>
        <EmptyState
          icon={<Compass className="size-5" />}
          title="这个页面还没有实现"
          description="docs/UI.md §4 里的多数路由会在后续阶段逐个上线。当前 PHASE 1 已实现：Landing、登录、/app/dashboard、/system。"
          action={
            <>
              <Button asChild variant="secondary">
                <Link href="/app/dashboard">回到总览</Link>
              </Button>
              <Button asChild variant="ghost">
                <Link href="/">返回首页</Link>
              </Button>
            </>
          }
          hint="404"
        />
      </div>
    </main>
  );
}
