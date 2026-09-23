'use client';

import type { AuthTokens, DemoLoginResponse, User } from '@careerforge/shared';

/**
 * Session storage for the browser.
 *
 * PHASE 1 stores the token in `localStorage` **and** mirrors it into a
 * `SameSite=Lax` cookie, because a cookie is what lets a later phase move auth to
 * middleware/SSR without changing call sites. Both are readable by JS, which is an
 * accepted trade-off for a demo-grade single-tenant app and is documented in the
 * README limitations; hardening (httpOnly cookie + refresh rotation) is PHASE 13.
 */

export const SESSION_STORAGE_KEY = 'careerforge.session';
export const ACCESS_TOKEN_COOKIE = 'cf_access_token';

export interface Session extends AuthTokens {
  user: User;
  /** epoch ms — used to decide when a refresh is due (API.md §1.2: 30 min). */
  storedAt: number;
}

type Listener = () => void;

const listeners = new Set<Listener>();
let cached: { session: Session | null } | null = null;

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof document !== 'undefined';
}

function isUser(value: unknown): value is User {
  if (typeof value !== 'object' || value === null) return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record['id'] === 'string' &&
    typeof record['email'] === 'string' &&
    typeof record['displayName'] === 'string'
  );
}

function parseSession(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return null;
    const record = parsed as Record<string, unknown>;
    const accessToken = record['accessToken'];
    const refreshToken = record['refreshToken'];
    const expiresIn = record['expiresIn'];
    const user = record['user'];
    const storedAt = record['storedAt'];
    if (typeof accessToken !== 'string' || !accessToken) return null;
    if (typeof refreshToken !== 'string') return null;
    if (typeof expiresIn !== 'number') return null;
    if (!isUser(user)) return null;
    return {
      accessToken,
      refreshToken,
      expiresIn,
      user,
      storedAt: typeof storedAt === 'number' ? storedAt : Date.now(),
    };
  } catch {
    return null;
  }
}

function readCookie(name: string): string | null {
  if (!isBrowser()) return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  const value = match?.[1];
  return value ? decodeURIComponent(value) : null;
}

function writeCookie(name: string, value: string, maxAgeSeconds: number): void {
  if (!isBrowser()) return;
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=${maxAgeSeconds}; SameSite=Lax`;
}

function deleteCookie(name: string): void {
  if (!isBrowser()) return;
  document.cookie = `${name}=; path=/; max-age=0; SameSite=Lax`;
}

/** Cached session read — safe to call on every request from the API client. */
export function getSession(): Session | null {
  if (cached) return cached.session;
  if (!isBrowser()) {
    cached = { session: null };
    return null;
  }
  let session: Session | null = null;
  try {
    session = parseSession(window.localStorage.getItem(SESSION_STORAGE_KEY));
  } catch {
    session = null;
  }
  cached = { session };
  return session;
}

export function getAccessToken(): string | null {
  const session = getSession();
  if (session?.accessToken) return session.accessToken;
  return readCookie(ACCESS_TOKEN_COOKIE);
}

export function isAuthenticated(): boolean {
  return Boolean(getAccessToken());
}

export function subscribeSession(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function notify(): void {
  cached = null;
  for (const listener of listeners) listener();
}

/** Persist a login/refresh response and notify every subscriber. */
export function saveSession(response: DemoLoginResponse): Session {
  const session: Session = { ...response, storedAt: Date.now() };
  if (isBrowser()) {
    try {
      window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    } catch {
      // Storage full/blocked (private mode): the cookie below still carries the token.
    }
    writeCookie(ACCESS_TOKEN_COOKIE, session.accessToken, Math.max(session.expiresIn, 60));
  }
  notify();
  return session;
}

/** Drop the local session (logout, or a 401 from the API client). */
export function clearSession(): void {
  if (isBrowser()) {
    try {
      window.localStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // nothing to clean up
    }
    deleteCookie(ACCESS_TOKEN_COOKIE);
  }
  notify();
}
