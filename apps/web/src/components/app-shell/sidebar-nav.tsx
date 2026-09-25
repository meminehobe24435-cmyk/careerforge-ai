'use client';

import { Badge, Dialog, DialogContent, DialogTitle, Tooltip } from '@careerforge/ui';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { cn } from '@/lib/utils';

import type { NavItem } from './nav-config';
import { navGroups, publicNav } from './nav-config';

function isActiveRoute(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Compact brand mark: a forged "CF" monogram, drawn with tokens only. */
function BrandMark() {
  return (
    <span
      aria-hidden="true"
      className="border-default bg-brand/10 text-brand flex size-8 shrink-0 items-center justify-center rounded-md border font-mono text-[11px] font-semibold"
    >
      CF
    </span>
  );
}

interface NavRowProps {
  item: NavItem;
  collapsed: boolean;
  active: boolean;
  onNavigate?: (() => void) | undefined;
}

function NavRow({ item, collapsed, active, onNavigate }: NavRowProps) {
  const Icon = item.icon;

  const baseClasses = cn(
    'relative flex w-full items-center gap-2.5 rounded-md text-sm outline-none',
    'transition-colors duration-[var(--dur-fast)] ease-forge',
    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand',
    collapsed ? 'justify-center px-0 py-2' : 'px-2 py-1.5',
    active ? 'bg-active text-primary' : 'text-secondary hover:bg-hover hover:text-primary',
  );

  const indicator = active ? (
    <span
      aria-hidden="true"
      className="bg-brand absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full"
    />
  ) : null;

  if (!item.live) {
    // A route that does not exist yet: visible, honestly badged, and not clickable.
    const disabled = (
      <span
        aria-disabled="true"
        className={cn(baseClasses, 'cursor-not-allowed opacity-55 hover:bg-transparent')}
      >
        {indicator}
        <Icon className="size-4 shrink-0" aria-hidden="true" />
        {collapsed ? null : (
          <>
            <span className="truncate">{item.label}</span>
            <Badge variant="outline" className="ml-auto">
              {item.phase ?? '未上线'}
            </Badge>
          </>
        )}
      </span>
    );

    return collapsed ? (
      <Tooltip content={`${item.label} · ${item.phase ?? '未上线'}`} side="right">
        <span className="block w-full">{disabled}</span>
      </Tooltip>
    ) : (
      disabled
    );
  }

  const link = (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? 'page' : undefined}
      aria-label={collapsed ? `${item.label}（${item.en}）` : undefined}
      className={baseClasses}
    >
      {indicator}
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {collapsed ? null : <span className="truncate">{item.label}</span>}
    </Link>
  );

  return collapsed ? (
    <Tooltip content={`${item.label} · ${item.en}`} side="right">
      <span className="block w-full">{link}</span>
    </Tooltip>
  ) : (
    link
  );
}

interface NavContentProps {
  collapsed: boolean;
  pathname: string;
  onNavigate?: (() => void) | undefined;
}

function NavContent({ collapsed, pathname, onNavigate }: NavContentProps) {
  return (
    <div className="bg-surface flex h-full min-h-0 flex-col">
      <div
        className={cn(
          'border-subtle flex h-14 shrink-0 items-center gap-2 border-b',
          collapsed ? 'justify-center px-2' : 'px-3',
        )}
      >
        <BrandMark />
        {collapsed ? null : (
          <span className="text-primary truncate font-mono text-xs font-medium tracking-tight">
            CareerForge
          </span>
        )}
      </div>

      <nav aria-label="主导航" className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
        {navGroups.map((group) => (
          <div key={group.id} className="mb-4 last:mb-0">
            {collapsed ? (
              <span className="sr-only">{group.title}</span>
            ) : (
              <p className="text-tertiary px-2 pb-1.5 font-mono text-[10px] uppercase tracking-wider">
                {group.title}
              </p>
            )}
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <li key={item.href}>
                  <NavRow
                    item={item}
                    collapsed={collapsed}
                    active={isActiveRoute(pathname, item.href)}
                    onNavigate={onNavigate}
                  />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-subtle shrink-0 border-t p-2">
        <ul className="flex flex-col gap-0.5">
          {publicNav.map((item) => (
            <li key={item.href}>
              <NavRow
                item={item}
                collapsed={collapsed}
                active={isActiveRoute(pathname, item.href)}
                onNavigate={onNavigate}
              />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export interface SidebarNavProps {
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
}

/**
 * Sidebar navigation (docs/UI.md §3.2, §10).
 *
 * ≥1024px: 240px expanded rail · 768–1023px: 64px icon rail · <768px: off-canvas drawer.
 * Widths come from the `--sidebar-width` tokens (240px / 64px), so nothing is a magic
 * number and the 375px case never overflows.
 */
export function SidebarNav({ mobileOpen, onMobileOpenChange }: SidebarNavProps) {
  const pathname = usePathname() ?? '/app/dashboard';

  return (
    <>
      {/* ≥1024px — expanded 240px rail */}
      <aside className="border-default sticky top-0 hidden h-dvh w-[var(--sidebar-width)] shrink-0 border-r lg:block">
        <NavContent collapsed={false} pathname={pathname} />
      </aside>

      {/* 768–1023px — 64px icon rail (labels move into tooltips) */}
      <aside className="border-default sticky top-0 hidden h-dvh w-[var(--sidebar-width-collapsed)] shrink-0 border-r md:block lg:hidden">
        <NavContent collapsed pathname={pathname} />
      </aside>

      {/* <768px — off-canvas drawer, so no fixed width is ever forced on a 375px screen */}
      <Dialog open={mobileOpen} onOpenChange={onMobileOpenChange}>
        <DialogContent
          hideClose
          className="data-[state=open]:animate-drawer-in left-0 top-0 h-dvh max-h-dvh w-[var(--sidebar-width)] max-w-[85vw] translate-x-0 translate-y-0 rounded-none border-0 p-0 shadow-lg"
          // Both layers move to the drawer's z-index. Moving only the content left the overlay
          // (--z-modal, 60) above the panel (--z-drawer, 50), so the backdrop intercepted every tap
          // on the drawer — found by the mobile end-to-end run at 375px, and invisible to any
          // DOM-level test, because jsdom has no stacking order.
          style={{ zIndex: 'var(--z-drawer)' }}
          overlayStyle={{ zIndex: 'var(--z-drawer)' }}
          aria-describedby={undefined}
        >
          <DialogTitle className="sr-only">导航菜单</DialogTitle>
          <NavContent
            collapsed={false}
            pathname={pathname}
            onNavigate={() => onMobileOpenChange(false)}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
