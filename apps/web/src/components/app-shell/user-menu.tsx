'use client';

import {
  Badge,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@careerforge/ui';
import type { User } from '@careerforge/shared';
import { LogOut, Radar, Settings } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';

import { clearSession } from '@/lib/auth';
import { cn, initialsOf } from '@/lib/utils';

export interface UserMenuProps {
  user: User | null;
}

/** Top-bar account menu: identity, storage scope, sign-out. */
export function UserMenu({ user }: UserMenuProps) {
  const router = useRouter();
  const displayName = user?.displayName ?? '未登录';

  const handleSignOut = () => {
    clearSession();
    toast.success('已退出登录');
    router.replace('/login');
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`账户菜单：${displayName}`}
          className={cn(
            'border-default bg-elevated flex size-8 shrink-0 items-center justify-center rounded-full border',
            'text-secondary font-mono text-[11px] font-medium',
            'ease-forge transition-colors duration-[var(--dur-fast)]',
            'hover:border-strong hover:text-primary',
            'focus-visible:outline-brand outline-none focus-visible:outline-2 focus-visible:outline-offset-2',
          )}
        >
          {user ? initialsOf(user.displayName) : '—'}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>Account</DropdownMenuLabel>
        <div className="px-2 pb-2">
          <p className="text-primary truncate text-sm font-medium">{displayName}</p>
          <p className="text-tertiary truncate font-mono text-[11px]">
            {user?.email ?? '会话未加载'}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1">
            {user?.isDemo ? <Badge variant="signal">demo</Badge> : null}
            {user?.storageScope ? (
              <Badge variant="outline">storage: {user.storageScope}</Badge>
            ) : null}
          </div>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/system">
            <Radar className="size-3.5" aria-hidden="true" />
            系统状态
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem disabled>
          <Settings className="size-3.5" aria-hidden="true" />
          设置
          <span className="text-tertiary ml-auto font-mono text-[10px]">PHASE 11</span>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={handleSignOut}>
          <LogOut className="size-3.5" aria-hidden="true" />
          退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
