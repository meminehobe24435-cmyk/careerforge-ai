'use client';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
  IconButton,
} from '@careerforge/ui';
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';

const OPTIONS = [
  { value: 'light', label: '浅色', icon: Sun },
  { value: 'dark', label: '深色', icon: Moon },
  { value: 'system', label: '跟随系统', icon: Monitor },
] as const;

/**
 * Theme toggle. Renders the dark assumption until mounted (matching the server HTML),
 * then reflects the stored theme — no hydration mismatch, no flash.
 */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const active = mounted ? (theme ?? 'dark') : 'dark';
  const ActiveIcon = OPTIONS.find((option) => option.value === active)?.icon ?? Moon;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <IconButton aria-label={`切换主题（当前：${active}）`}>
          <ActiveIcon className="size-4" />
        </IconButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-36">
        <DropdownMenuLabel>Theme</DropdownMenuLabel>
        {OPTIONS.map((option) => (
          <DropdownMenuItem
            key={option.value}
            onSelect={() => setTheme(option.value)}
            aria-checked={active === option.value}
            role="menuitemradio"
          >
            <option.icon className="size-3.5" aria-hidden="true" />
            {option.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
