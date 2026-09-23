'use client';

import { useTheme } from 'next-themes';
import { useEffect, useState } from 'react';
import { Toaster } from 'sonner';

/**
 * `sonner` toaster, themed from the design tokens.
 *
 * Colours come from `[data-sonner-toast]` rules in `globals.css` (token variables), never
 * from inline values — see docs/UI.md §2.1.
 */
export function AppToaster() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  // The server render cannot know the resolved theme; "dark" is the documented default,
  // and the switch happens after mount (no hydration mismatch, no visible flash).
  const theme = mounted && resolvedTheme === 'light' ? 'light' : 'dark';

  return (
    <Toaster
      theme={theme}
      position="bottom-right"
      closeButton
      duration={6000}
      gap={10}
      style={{ zIndex: 'var(--z-toast)' }}
      toastOptions={{
        classNames: {
          toast: 'border border-default bg-elevated text-primary',
          title: 'text-sm font-medium text-primary',
          description: 'text-xs text-secondary',
          actionButton: 'bg-brand text-brand-fg',
          cancelButton: 'border border-default bg-elevated text-secondary',
          closeButton: 'border border-default bg-elevated text-tertiary',
        },
      }}
    />
  );
}
