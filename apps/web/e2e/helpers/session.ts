import type { Page } from '@playwright/test';

import { API_BASE_URL, type SessionPayload } from './api';

/**
 * The browser session, installed the way the app itself stores it.
 *
 * The app's auth guard is client-side (`lib/auth.ts` + `hooks/use-session.ts`): it reads
 * `localStorage['careerforge.session']` after mount and renders the shell only once it has. So a
 * real session is established by writing that key **before any page script runs** —
 * `page.addInitScript` — and then navigating. No form is automated, which matters because the
 * demo login is a single button on `/login`, not the product surface these specs are about.
 *
 * This mirrors the approach already used by `apps/web/scripts/capture-pages.mts` (which drives
 * Chrome over CDP for the same reason), so the two cannot drift apart in what they consider a
 * signed-in browser.
 */
export const SESSION_STORAGE_KEY = 'careerforge.session';

export interface BrowserSession extends SessionPayload {
  /** epoch ms — the app stamps this when it stores a session. */
  storedAt: number;
}

export function toBrowserSession(payload: SessionPayload, now = Date.now()): BrowserSession {
  return { ...payload, storedAt: now };
}

export async function installSession(page: Page, session: BrowserSession): Promise<void> {
  const serialized = JSON.stringify(session);
  await page.addInitScript(
    (value: { key: string; payload: string }) => {
      window.localStorage.setItem(value.key, value.payload);
    },
    { key: SESSION_STORAGE_KEY, payload: serialized },
  );
}

/**
 * Call the API **from the page**, with the session the page itself holds.
 *
 * Used for the flows whose UI is not shipped yet (JD analysis, claim validation, the interview)
 * and for the CORS regression: running the call in the browser means the request crosses the
 * origin boundary exactly as the app's own client does, so a CORS or contract mistake fails here
 * instead of passing against a token plumbed in by the test.
 *
 * The returned `status` is not asserted here — the caller asserts, so a 4xx reads as an
 * assertion failure with the body next to it rather than as a networking mystery.
 */
export async function apiFromPage<T>(
  page: Page,
  path: string,
  options: { method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'; body?: unknown } = {},
): Promise<{ status: number; data: T }> {
  return page.evaluate(
    async (request: {
      apiBase: string;
      path: string;
      method: string;
      body: unknown;
      key: string;
    }) => {
      const raw = window.localStorage.getItem(request.key);
      const session = raw ? (JSON.parse(raw) as { accessToken?: string }) : null;
      if (!session?.accessToken) {
        throw new Error(
          `no ${request.key} in localStorage: install the session (page.addInitScript) and navigate before calling the API from the page`,
        );
      }
      const response = await fetch(request.apiBase + request.path, {
        method: request.method,
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${session.accessToken}`,
          ...(request.body === null ? {} : { 'Content-Type': 'application/json' }),
        },
        ...(request.body === null ? {} : { body: JSON.stringify(request.body) }),
      });
      const text = await response.text();
      const parsed: unknown = text ? JSON.parse(text) : null;
      const envelope = parsed as { data?: unknown } | null;
      return { status: response.status, data: (envelope?.data ?? null) as unknown };
    },
    {
      apiBase: API_BASE_URL,
      path,
      method: options.method ?? 'GET',
      body: options.body ?? null,
      key: SESSION_STORAGE_KEY,
    },
  ) as Promise<{ status: number; data: T }>;
}

/** Literal text of the page, for assertions about what a reader can actually see. */
export async function visibleText(page: Page): Promise<string> {
  return page.evaluate(() => document.body.innerText);
}
