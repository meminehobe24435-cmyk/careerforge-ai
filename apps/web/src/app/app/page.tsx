import { redirect } from 'next/navigation';

/**
 * `/app` itself has no content — it is the shell entry point.
 *
 * The authoritative hop is the `redirects()` rule in `next.config.ts` (a real 307 for
 * every request, including no-JS clients). This server-side `redirect()` is the in-app
 * fallback for a client-side navigation that reaches the route directly.
 */
export default function AppIndexPage() {
  redirect('/app/dashboard');
}
