import { API_BASE_URL } from './helpers/api';
import { expect, test } from './helpers/fixtures';
import { SESSION_STORAGE_KEY } from './helpers/session';

/**
 * CORS regression — the two directions that matter, because only one of them is usually tested.
 *
 * The stack must be running before this spec, in this order (the API first: the web bundle inlines
 * the API base URL at build time, and the API has to know the origin the browser will use):
 *
 * ```powershell
 * # 1. API on :8318, with the browser's origin allowed
 * cd apps/api
 * $env:USE_SQLITE='true'; $env:SQLITE_PATH='D:/workspace/epan/data/e2e.db'; $env:ENVIRONMENT='development'
 * $env:JWT_SECRET='local-verification-secret-000000000000'; $env:LLM_PROVIDER='heuristic'
 * $env:CORS_ORIGINS='http://localhost:3318,http://127.0.0.1:3318'
 * & D:\workspace\epan\.venv\Scripts\python.exe -m uvicorn careerforge_api.main:app --host 127.0.0.1 --port 8318
 *
 * # 2. web on :3318, built against that API
 * $env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:8318/api/v1'
 * pnpm --filter @careerforge/web build
 * pnpm --filter @careerforge/web start --port 3318
 * ```
 *
 * What is asserted:
 *
 * (a) **the allowed origin really can read the API from page context** — a plain `fetch` and an
 *     authenticated `fetch` (the `authorization` header makes that one a preflighted request), so a
 *     regression in `allow_headers` fails here rather than in a browser console nobody reads;
 * (b) **a non-allowed origin is not granted** — the same preflight that succeeds for the app origin
 *     comes back without `Access-Control-Allow-Origin` naming `evil.example`, which is the condition
 *     under which the browser blocks the request. The spec also refuses a wildcard: "allow `*`" is
 *     the change that would make (b) pass while breaking the guarantee it exists to protect.
 */
test.describe('CORS', () => {
  test('the app origin can read the API from the browser', async ({ signedInPage: page }) => {
    await page.goto('/app/dashboard');
    const origin = await page.evaluate(() => window.location.origin);

    const anonymous = await page.evaluate(async (url: string) => {
      try {
        const response = await fetch(url, { headers: { Accept: 'application/json' } });
        return { status: response.status, body: await response.text() };
      } catch (error) {
        return { status: 0, body: String(error) };
      }
    }, `${API_BASE_URL}/system/health`);

    expect(
      anonymous.status,
      `a fetch from ${origin} to ${API_BASE_URL}/system/health did not succeed (${anonymous.body}). ` +
        `This is what a browser does when CORS_ORIGINS does not include ${origin}: the request is blocked ` +
        'before any response reaches the page.',
    ).toBe(200);
    const health = JSON.parse(anonymous.body) as {
      success: boolean;
      data: { checks: Record<string, { status: string }> };
    };
    expect(health.success).toBe(true);
    expect(health.data.checks['database']?.status).toBe('ok');

    // The authenticated call the app actually makes: `Authorization` is not a CORS-safelisted
    // request header, so this one is only possible if the preflight grants it.
    const authenticated = await page.evaluate(
      async ({ url, key }: { url: string; key: string }) => {
        const raw = window.localStorage.getItem(key);
        const token = raw ? (JSON.parse(raw) as { accessToken?: string }).accessToken : undefined;
        try {
          const response = await fetch(url, {
            headers: { Accept: 'application/json', Authorization: `Bearer ${token ?? ''}` },
          });
          return { status: response.status, body: await response.text() };
        } catch (error) {
          return { status: 0, body: String(error) };
        }
      },
      { url: `${API_BASE_URL}/dashboard`, key: SESSION_STORAGE_KEY },
    );

    expect(
      authenticated.status,
      `an authenticated fetch from ${origin} failed (${authenticated.body}). The preflight must allow the ` +
        'authorization request header for this origin.',
    ).toBe(200);
    expect((JSON.parse(authenticated.body) as { success: boolean }).success).toBe(true);
  });

  test('a non-allowed origin is not granted, and the allowed one still is', async ({
    request,
    baseURL,
  }) => {
    // Derived from the app URL under test rather than hardcoded: with a literal origin the spec
    // failed on every port except one, for a reason that had nothing to do with CORS. CI runs on
    // 3318; a local run uses whatever port is free.
    const allowedOrigin = new URL(baseURL ?? 'http://127.0.0.1:3318').origin;
    const foreignOrigin = 'http://evil.example';
    const preflight = async (origin: string) =>
      request.fetch(`${API_BASE_URL}/jobs/analyze`, {
        method: 'OPTIONS',
        headers: {
          Origin: origin,
          'Access-Control-Request-Method': 'POST',
          'Access-Control-Request-Headers': 'authorization,content-type',
        },
      });

    // Positive control: the same request from the app origin IS granted, naming that origin. Without
    // this half, the negative assertion below would also pass against an API that never answers.
    const allowed = await (await preflight(allowedOrigin)).headers();
    expect(
      allowed['access-control-allow-origin'],
      'the configured origin must be echoed back',
    ).toBe(allowedOrigin);

    const foreign = await (await preflight(foreignOrigin)).headers();
    const allowOrigin = foreign['access-control-allow-origin'] ?? '';
    expect(
      allowOrigin,
      'a preflight from an origin outside CORS_ORIGINS must not be granted: the browser blocks the request ' +
        'unless Access-Control-Allow-Origin names the caller or is a wildcard',
    ).not.toContain('evil.example');
    expect(
      allowOrigin,
      'allow `*` would make this test pass while disabling the protection it exists to check',
    ).not.toBe('*');
  });
});
