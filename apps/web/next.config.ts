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
   * `standalone`, because `infra/docker/Dockerfile.web` ships exactly that output: its runner stage
   * copies `.next/standalone`, `.next/static` and `public/` and starts `node apps/web/server.js`. The
   * comment in that Dockerfile said this was enabled here and it was not, so the image build failed
   * with `failed to calculate checksum … "/repo/apps/web/.next/standalone": not found` — the third
   * thing in this repository that was documented more confidently than it was implemented, and one
   * more that only CI could find because nothing here builds a container.
   *
   * The mode is additive: `next build` emits the standalone server *in addition to* the normal build,
   * so `next start` (dev, the E2E stack, CI's `web` job) is unaffected.
   */
  output: 'standalone',
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
