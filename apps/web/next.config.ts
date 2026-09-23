import type { NextConfig } from 'next';

/**
 * CareerForge AI — web client (Next.js 15 App Router).
 *
 * `transpilePackages` is what lets the app consume the workspace packages
 * (`@careerforge/ui`, `@careerforge/shared`) straight from TypeScript source:
 * pnpm symlinks them into `node_modules`, and Next compiles them as part of the
 * app graph — no separate build step, no stale `dist/`.
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ['@careerforge/ui', '@careerforge/shared'],
  /**
   * `/app` is the shell entry point with no content of its own. It is redirected at the
   * HTTP layer (not only via `redirect()` in the page) so the hop also works without
   * JavaScript — `curl -i http://localhost:3000/app` returns 307 + `Location`.
   */
  async redirects() {
    return [{ source: '/app', destination: '/app/dashboard', permanent: false }];
  },
};

export default nextConfig;
