'use client';

import { IconButton, Kbd } from '@careerforge/ui';
import type { User } from '@careerforge/shared';
import { Menu, Search } from 'lucide-react';
import { useEffect, useState } from 'react';

import { cn } from '@/lib/utils';

import type { Breadcrumb } from './nav-config';
import { ThemeToggle } from './theme-toggle';
import { UserMenu } from './user-menu';

export interface TopBarProps {
  title: string;
  crumbs: Breadcrumb[];
  user: User | null;
  onOpenNav: () => void;
  onOpenPalette: () => void;
}

/**
 * Top bar: breadcrumb · command-palette trigger · theme toggle · account menu.
 * Below 768px the sidebar becomes a drawer, so a menu button appears here instead.
 */
export function TopBar({ title, crumbs, user, onOpenNav, onOpenPalette }: TopBarProps) {
  const [isMac, setIsMac] = useState(false);

  useEffect(() => {
    const platform =
      (globalThis as { navigator?: { platform?: string } }).navigator?.platform ?? '';
    setIsMac(/Mac|iPod|iPhone|iPad/i.test(platform));
  }, []);

  const modifier = isMac ? '⌘' : 'Ctrl';

  return (
    <header className="border-default bg-base/85 sticky top-0 z-40 flex h-14 shrink-0 items-center gap-3 border-b px-3 backdrop-blur sm:px-4">
      <IconButton aria-label="打开导航菜单" className="md:hidden" onClick={onOpenNav}>
        <Menu className="size-4" />
      </IconButton>

      <nav aria-label="面包屑" className="min-w-0 flex-1">
        <ol className="text-tertiary flex min-w-0 items-center gap-1.5 text-xs">
          {crumbs.map((crumb, index) => (
            <li key={`${crumb.label}-${index}`} className="flex min-w-0 items-center gap-1.5">
              {index > 0 ? (
                <span aria-hidden="true" className="text-tertiary">
                  /
                </span>
              ) : null}
              <span className="truncate font-mono">{crumb.label}</span>
            </li>
          ))}
          {crumbs.length > 0 ? (
            <li aria-hidden="true" className="text-tertiary">
              /
            </li>
          ) : null}
          <li className="text-primary truncate">{title}</li>
        </ol>
      </nav>

      <button
        type="button"
        onClick={onOpenPalette}
        aria-label="打开命令面板"
        className={cn(
          'border-default bg-surface hidden items-center gap-2 rounded-md border px-2.5 py-1.5',
          'text-tertiary text-xs lg:flex',
          'ease-forge hover:border-strong hover:text-secondary transition-colors duration-[var(--dur-fast)]',
          'focus-visible:outline-brand outline-none focus-visible:outline-2 focus-visible:outline-offset-2',
        )}
      >
        <Search className="size-3.5" aria-hidden="true" />
        <span>搜索或跳转</span>
        <Kbd>{modifier} K</Kbd>
      </button>

      <IconButton aria-label="打开命令面板" className="lg:hidden" onClick={onOpenPalette}>
        <Search className="size-4" />
      </IconButton>

      <ThemeToggle />
      <UserMenu user={user} />
    </header>
  );
}
