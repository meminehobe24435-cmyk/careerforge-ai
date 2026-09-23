import { Geist, Geist_Mono } from 'next/font/google';
import type { Metadata, Viewport } from 'next';

import { AppToaster } from '@/components/providers/app-toaster';
import { QueryProvider } from '@/components/providers/query-provider';
import { ThemeProvider } from '@/components/providers/theme-provider';

import '@/styles/globals.css';

/**
 * Geist Sans / Geist Mono are available in `next/font/google` for Next 15.5, so the
 * documented fallback (Inter + JetBrains Mono) was not needed. Both are self-hosted by
 * Next at build time; the CSS font stack in `globals.css` still lists JetBrains Mono and
 * CJK system faces as fallbacks.
 */
const geistSans = Geist({
  subsets: ['latin'],
  variable: '--font-geist-sans',
  display: 'swap',
});

const geistMono = Geist_Mono({
  subsets: ['latin'],
  variable: '--font-geist-mono',
  display: 'swap',
});

export const metadata: Metadata = {
  title: {
    default: 'CareerForge AI',
    template: '%s · CareerForge AI',
  },
  // Tagline taken verbatim from the repository README.
  description:
    'Evidence-driven AI career operating system. Turn your experience into verifiable career evidence.',
  applicationName: 'CareerForge AI',
  keywords: [
    'evidence graph',
    'career',
    'resume',
    'claim validation',
    'explainable match score',
    'CareerForge',
  ],
  authors: [{ name: 'CareerForge AI' }],
};

export const viewport: Viewport = {
  colorScheme: 'dark light',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `data-theme="dark"` is server-rendered so the first paint is already the dark
    // theme; `suppressHydrationWarning` covers next-themes' pre-paint attribute swap.
    <html
      lang="zh-CN"
      data-theme="dark"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable}`}
    >
      <body className="bg-base text-primary min-h-dvh font-sans antialiased">
        <ThemeProvider
          attribute="data-theme"
          defaultTheme="dark"
          enableSystem
          disableTransitionOnChange
        >
          <QueryProvider>
            {children}
            <AppToaster />
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
