'use client';

import { Badge, Dialog, DialogContent, DialogTitle, Kbd } from '@careerforge/ui';
import { ArrowRight, Search } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';

import { cn } from '@/lib/utils';

import { navGroups, publicNav } from './nav-config';

interface PaletteEntry {
  id: string;
  label: string;
  hint?: string;
  shortcut?: string;
  group: string;
  /** `false` = the underlying feature/route is not shipped yet (docs/UI.md §4). */
  live: boolean;
  phase?: string;
  href?: string;
}

/**
 * The things a user comes here to *do*, each pointing at the page that does it.
 *
 * These were `live: false` PHASE-1 placeholders. Now that the pages exist, an entry that merely
 * navigates to the same route as the sidebar item beside it would be duplicate weight — so this
 * group is reserved for actions that land **with the work already started**: the input focused, the
 * session ready. Everything else moved to the navigation group, which is generated from
 * `nav-config.ts` and therefore cannot go stale.
 */
const quickActions: PaletteEntry[] = [
  {
    id: 'action-analyze-jd',
    label: '分析 JD',
    hint: 'Analyze a job description',
    shortcut: '⌘↵',
    group: '动作',
    live: true,
    href: '/app/jobs?focus=input',
  },
  {
    id: 'action-validate-claim',
    label: '验证一句话',
    hint: 'Validate a resume claim',
    group: '动作',
    live: true,
    href: '/app/validator?focus=input',
  },
  {
    id: 'action-start-interview',
    label: '开始模拟面试',
    hint: 'Start an interview session',
    group: '动作',
    live: true,
    href: '/app/interview',
  },
  {
    id: 'action-evidence-graph',
    label: '查看证据图谱',
    hint: 'Open the Evidence Graph',
    group: '动作',
    live: true,
    href: '/app/evidence-graph',
  },
  {
    id: 'action-ai-runs',
    label: '查看 AI 运行记录',
    hint: 'AI runs, cost and prompts',
    group: '动作',
    live: true,
    href: '/app/ai-runs',
  },
];

const navigationEntries: PaletteEntry[] = [
  ...navGroups.flatMap((group) =>
    group.items.map((item) => ({
      id: item.href,
      label: item.label,
      hint: item.en,
      ...(item.shortcut ? { shortcut: item.shortcut } : {}),
      group: '导航',
      live: item.live,
      ...(item.phase ? { phase: item.phase } : {}),
      href: item.href,
    })),
  ),
  ...publicNav.map((item) => ({
    id: item.href,
    label: item.label,
    hint: item.en,
    group: '导航',
    live: item.live,
    href: item.href,
  })),
];

const allEntries: PaletteEntry[] = [...quickActions, ...navigationEntries];
const GROUP_ORDER = ['动作', '导航'] as const;

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Command palette (`Ctrl/Cmd + K`) — PHASE 1 stub.
 *
 * It lists the real action inventory from docs/UI.md §7 with honest `未上线` badges, is
 * fully keyboard operable (↑ ↓ Enter Esc), and only navigates to routes that exist today.
 * Fuzzy search + recent-history + global search results arrive with PHASE 6.
 */
export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelectedIndex(0);
    }
  }, [open]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return allEntries;
    return allEntries.filter((entry) =>
      [entry.label, entry.hint, entry.shortcut]
        .filter((value): value is string => Boolean(value))
        .some((value) => value.toLowerCase().includes(needle)),
    );
  }, [query]);

  const grouped = useMemo(
    () =>
      GROUP_ORDER.map((group) => ({
        group,
        entries: filtered.filter((entry) => entry.group === group),
      })).filter((bucket) => bucket.entries.length > 0),
    [filtered],
  );

  useEffect(() => {
    if (selectedIndex > filtered.length - 1) setSelectedIndex(0);
  }, [filtered.length, selectedIndex]);

  const select = (entry: PaletteEntry) => {
    if (!entry.live || !entry.href) return;
    onOpenChange(false);
    router.push(entry.href);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setSelectedIndex((index) => (filtered.length === 0 ? 0 : (index + 1) % filtered.length));
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setSelectedIndex((index) =>
        filtered.length === 0 ? 0 : (index - 1 + filtered.length) % filtered.length,
      );
      return;
    }
    if (event.key === 'Enter') {
      const entry = filtered[selectedIndex];
      if (!entry) return;
      event.preventDefault();
      select(entry);
    }
  };

  let flatIndex = -1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-xl gap-0 p-0"
        aria-describedby={undefined}
        // The palette is a layer above the app; docs/UI.md §2.3 puts it at --z-palette.
        style={{ zIndex: 'var(--z-palette)' }}
      >
        <DialogTitle className="sr-only">命令面板</DialogTitle>

        <div className="border-subtle flex items-center gap-2 border-b px-4 py-3">
          <Search className="text-tertiary size-4 shrink-0" aria-hidden="true" />
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入命令或搜索…"
            aria-label="搜索命令或页面"
            role="combobox"
            aria-expanded="true"
            aria-controls="command-palette-list"
            aria-activedescendant={
              filtered[selectedIndex]
                ? `command-palette-item-${filtered[selectedIndex].id}`
                : undefined
            }
            className="text-primary placeholder:text-tertiary min-w-0 flex-1 bg-transparent text-sm outline-none"
          />
          <Kbd>esc</Kbd>
        </div>

        <div
          ref={listRef}
          id="command-palette-list"
          role="listbox"
          aria-label="命令与页面"
          className="max-h-[min(60dvh,420px)] overflow-y-auto p-2"
        >
          {grouped.length === 0 ? (
            <p className="text-secondary px-3 py-6 text-center text-xs">
              没有匹配项 — 全局搜索将在 PHASE 6 提供
            </p>
          ) : (
            grouped.map((bucket) => (
              <div key={bucket.group} className="mb-1 last:mb-0">
                <p className="text-tertiary px-2 py-1.5 font-mono text-[10px] uppercase tracking-wider">
                  {bucket.group}
                </p>
                {bucket.entries.map((entry) => {
                  flatIndex += 1;
                  const isSelected = flatIndex === selectedIndex;
                  return (
                    <button
                      key={entry.id}
                      id={`command-palette-item-${entry.id}`}
                      type="button"
                      role="option"
                      aria-selected={isSelected}
                      aria-disabled={entry.live ? undefined : true}
                      onMouseEnter={() => setSelectedIndex(flatIndex)}
                      onClick={() => select(entry)}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-sm px-2 py-2 text-left text-sm',
                        'ease-forge transition-colors duration-[var(--dur-fast)]',
                        isSelected ? 'bg-hover text-primary' : 'text-secondary',
                        !entry.live && 'cursor-not-allowed opacity-60',
                      )}
                    >
                      <span className="flex-1 truncate">{entry.label}</span>
                      {entry.hint ? (
                        <span className="text-tertiary hidden truncate font-mono text-[11px] sm:block">
                          {entry.hint}
                        </span>
                      ) : null}
                      {entry.shortcut ? <Kbd>{entry.shortcut}</Kbd> : null}
                      {entry.live ? (
                        <ArrowRight
                          className="text-tertiary size-3.5 shrink-0"
                          aria-hidden="true"
                        />
                      ) : (
                        <Badge variant="outline">{entry.phase ?? '未上线'}</Badge>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
