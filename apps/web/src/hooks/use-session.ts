'use client';

import { useEffect, useState } from 'react';

import type { Session } from '@/lib/auth';
import { getSession, subscribeSession } from '@/lib/auth';

export interface SessionState {
  /** `false` until the first client-side read — prevents a hydration mismatch. */
  ready: boolean;
  session: Session | null;
}

/**
 * Reads the persisted session after mount and stays in sync with login/logout.
 *
 * The server render always yields `{ ready: false, session: null }`, so the auth guard
 * never redirects on a stale server snapshot — it waits for `ready`.
 */
export function useSession(): SessionState {
  const [state, setState] = useState<SessionState>({ ready: false, session: null });

  useEffect(() => {
    setState({ ready: true, session: getSession() });
    return subscribeSession(() => setState({ ready: true, session: getSession() }));
  }, []);

  return state;
}
