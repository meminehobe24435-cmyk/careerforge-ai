'use client';

import { ThemeProvider as NextThemesProvider } from 'next-themes';
import type { ComponentProps } from 'react';

/**
 * Theme provider.
 *
 * `attribute="data-theme"` is what `src/styles/tokens.css` keys the light palette off,
 * and `defaultTheme="dark"` matches the server-rendered `data-theme="dark"` on <html>,
 * so there is no flash and no hydration mismatch (docs/UI.md §1.1).
 */
export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return <NextThemesProvider {...props}>{children}</NextThemesProvider>;
}
